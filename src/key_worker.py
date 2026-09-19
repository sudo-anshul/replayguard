"""Three fixed caller key choices; no receipt-store permission or public API."""
import datetime
import hashlib
import json
import os
import re
import time

_lambda_client = None
CANDIDATES = ("no-key", "sku-key", "order-key")
FAULT = "after-commit-first-receive"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def validate(body):
    if not isinstance(body, dict) or set(body) != {"schemaVersion", "runId", "candidate", "order", "fault"}:
        raise ValueError("Invalid message fields")
    if type(body["schemaVersion"]) is not int or body["schemaVersion"] != 2 or body["candidate"] not in CANDIDATES:
        raise ValueError("Unknown schema or candidate")
    if not isinstance(body["runId"], str) or not IDENTIFIER.fullmatch(body["runId"]):
        raise ValueError("Invalid runId")
    order = body["order"]
    if not isinstance(order, dict) or set(order) != {"orderId", "sku", "quantity"}:
        raise ValueError("Invalid order fields")
    if not isinstance(order["orderId"], str) or not IDENTIFIER.fullmatch(order["orderId"]):
        raise ValueError("Invalid orderId")
    if not isinstance(order["sku"], str) or not SKU.fullmatch(order["sku"]):
        raise ValueError("Invalid sku")
    if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 100:
        raise ValueError("Invalid quantity")
    if body["fault"] not in (FAULT, "none"):
        raise ValueError("Unknown fault")
    return body


def chosen_key(run_id, candidate, order):
    if candidate == "no-key":
        return None
    field = "sku" if candidate == "sku-key" else "orderId"
    return hashlib.sha256(json.dumps([run_id, field, order[field]], separators=(",", ":")).encode()).hexdigest()


def client():
    global _lambda_client
    if _lambda_client is None:
        import boto3
        from botocore.config import Config
        _lambda_client = boto3.client("lambda", config=Config(connect_timeout=2, read_timeout=8, retries={"total_max_attempts": 1}))
    return _lambda_client


def emit(stage, metadata, **fields):
    print(json.dumps({**metadata, "stage": stage,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        **fields}, sort_keys=True, separators=(",", ":")))


def conflict_detail(result, payload):
    if result.get("errorType") != "PayloadConflict":
        return None
    try:
        detail = json.loads(result.get("errorMessage", ""))
    except (ValueError, TypeError):
        return None
    expected = {"schemaVersion": 2, "kind": "replayguard-key-conflict", "runId": payload["runId"],
        "candidate": payload["candidate"], "orderId": payload["order"]["orderId"], "key": payload.get("key"),
        "messageId": payload["messageId"], "workerRequestId": payload["workerRequestId"], "receiveCount": payload["receiveCount"]}
    if not isinstance(detail, dict) or set(detail) != set(expected) | {"receiptId"}:
        return None
    key = payload.get("key")
    if (type(detail.get("schemaVersion")) is not int or type(detail.get("receiveCount")) is not int
            or not isinstance(key, str) or detail.get("receiptId") != hashlib.sha256(key.encode()).hexdigest()
            or any(detail.get(k) != v for k, v in expected.items())):
        return None
    return detail


def handler(event, context):
    records = event.get("Records", []) if isinstance(event, dict) else []
    if len(records) != 1:
        raise ValueError("BatchSize=1 required")
    record = records[0]
    body = validate(json.loads(record["body"]))
    count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "0"))
    if count < 1 or count > 1000000:
        raise ValueError("Invalid receive count")
    metadata = {"schemaVersion": 2, "component": "worker", "runId": body["runId"], "candidate": body["candidate"],
        "order": body["order"], "orderId": body["order"]["orderId"], "messageId": record["messageId"],
        "receiveCount": count, "requestId": context.aws_request_id, "receiptId": None}
    emit("received", metadata)
    try:
        if time.time() >= int(os.environ.get("LAB_EXPIRES_AT", "0")):
            raise RuntimeError("Lab expired or not configured")
        payload = {**body, "messageId": record["messageId"], "receiveCount": count, "workerRequestId": context.aws_request_id}
        key = chosen_key(body["runId"], body["candidate"], body["order"])
        if key is not None:
            payload["key"] = key
        response = client().invoke(FunctionName=os.environ["PROVIDER_FUNCTION_ARN"], InvocationType="RequestResponse", Payload=json.dumps(payload, separators=(",", ":")).encode())
        result = json.loads(response["Payload"].read())
        if response.get("StatusCode") != 200 or not isinstance(result, dict):
            raise RuntimeError("Provider returned an invalid invocation response")
        if response.get("FunctionError"):
            detail = conflict_detail(result, payload)
            if detail is not None:
                metadata["receiptId"] = detail["receiptId"]
                emit("business_rejected", metadata, reason="payload-conflict", key=key)
                emit("completed", metadata, outcome="rejected", key=key)
                return {"outcome": "rejected", "reason": "payload-conflict"}
            emit("provider_failed", metadata, errorType=str(result.get("errorType", "UnknownError"))[:120])
            raise RuntimeError("Provider failed: " + str(result.get("errorType", "UnknownError"))[:120])
        if (result.get("schemaVersion") != 2 or result.get("key") != key or result.get("order") != body["order"]
                or type(result.get("accepted")) is not bool or type(result.get("reused")) is not bool
                or result["accepted"] == result["reused"] or not re.fullmatch(r"[a-f0-9]{32}|[a-f0-9]{64}", str(result.get("receiptId", "")))):
            raise RuntimeError("Provider returned no valid receipt response")
        metadata["receiptId"] = result["receiptId"]
        emit("fulfillment_succeeded", metadata, key=key, accepted=result["accepted"], reused=result["reused"])
        emit("completed", metadata, outcome="fulfilled", key=key)
        return {"outcome": "fulfilled", "receiptId": result["receiptId"], "reused": result["reused"]}
    except Exception as error:
        emit("failed", metadata, errorType=type(error).__name__, error=str(error)[:300])
        raise
