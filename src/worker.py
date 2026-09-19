"""SQS worker for the real receive -> fulfillment -> crash -> redelivery loop.

This worker deliberately has no DynamoDB permission. Receipts are owned by the
independently invoked fulfillment provider, so worker claims are not evidence of
a successful fulfillment.
"""

import datetime
import hashlib
import json
import os
import re
import time

_lambda_client = None
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("message body must be an object")
    for field in ("runId",):
        if not isinstance(payload.get(field), str) or not _IDENTIFIER.fullmatch(payload[field]):
            raise ValueError(f"{field} must be 1-64 letters, digits, underscores or hyphens")
    if payload.get("mode") not in ("vulnerable", "repaired"):
        raise ValueError("mode must be vulnerable or repaired")
    if payload.get("fault") not in ("crash-after-fulfillment", "none"):
        raise ValueError("fault must be crash-after-fulfillment or none")
    order = payload.get("order")
    if not isinstance(order, dict):
        raise ValueError("order must be an object")
    if not isinstance(order.get("orderId"), str) or not _IDENTIFIER.fullmatch(order["orderId"]):
        raise ValueError("orderId must be 1-64 letters, digits, underscores or hyphens")
    if not isinstance(order.get("sku"), str) or not _SKU.fullmatch(order["sku"]):
        raise ValueError("sku must be 1-128 supported identifier characters")
    if type(order.get("quantity")) is not int or not 1 <= order["quantity"] <= 100:
        raise ValueError("quantity must be an integer between 1 and 100")
    return payload


def require_active_lab():
    try:
        expires_at = int(os.environ["LAB_EXPIRES_AT"])
    except (KeyError, ValueError) as error:
        raise RuntimeError("LAB_EXPIRES_AT must be configured; refusing fulfillment") from error
    if time.time() >= expires_at:
        raise RuntimeError("Lab expired; refusing fulfillment. Delete the stack to remove resources.")


def lambda_client():
    global _lambda_client
    if _lambda_client is None:
        import boto3
        from botocore.config import Config
        # SQS owns retries. Avoid hidden SDK retries after an ambiguous response.
        _lambda_client = boto3.client("lambda", config=Config(connect_timeout=2, read_timeout=8, retries={"total_max_attempts": 1}))
    return _lambda_client


def idempotency_key(run_id, order_id):
    identity = json.dumps([run_id, order_id], separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def emit(stage, metadata, **fields):
    print(json.dumps({**metadata, "stage": stage, "timestamp": utc_now(), **fields}, separators=(",", ":"), sort_keys=True))


def handler(event, context):
    records = event.get("Records", []) if isinstance(event, dict) else []
    if len(records) != 1:
        raise ValueError("ReplayGuard requires exactly one SQS record (BatchSize=1)")
    record = records[0]
    payload = validate_payload(json.loads(record["body"]))
    receive_count = int(record.get("attributes", {}).get("ApproximateReceiveCount", "0"))
    if receive_count < 1:
        raise ValueError("SQS ApproximateReceiveCount must be positive")
    metadata = {
        "component": "worker",
        "runId": payload["runId"],
        "mode": payload["mode"],
        "orderId": payload["order"]["orderId"],
        "messageId": record["messageId"],
        "receiveCount": receive_count,
        "requestId": getattr(context, "aws_request_id", "local"),
        "receiptId": None,
    }
    emit("received", metadata)
    try:
        require_active_lab()
        invocation_payload = {
            "runId": payload["runId"],
            "mode": payload["mode"],
            "order": payload["order"],
            "fault": payload["fault"],
            "messageId": record["messageId"],
            "receiveCount": receive_count,
            "workerRequestId": metadata["requestId"],
        }
        if payload["mode"] == "repaired":
            # The repair is a stable key supplied by the caller to an idempotent
            # receiver. An attempt UUID would create another fulfillment.
            invocation_payload["idempotencyKey"] = idempotency_key(payload["runId"], payload["order"]["orderId"])
        response = lambda_client().invoke(
            FunctionName=os.environ["PROVIDER_FUNCTION_ARN"],
            InvocationType="RequestResponse",
            Payload=json.dumps(invocation_payload, separators=(",", ":")).encode("utf-8"),
        )
        result = json.loads(response["Payload"].read())
        if response.get("FunctionError"):
            raise RuntimeError(f"Fulfillment provider failed: {result.get('errorType', 'UnknownError')}: {result.get('errorMessage', 'no details')}")
        if response.get("StatusCode") != 200 or not isinstance(result, dict) or not result.get("receiptId"):
            raise RuntimeError("Fulfillment provider returned no successful durable receipt")
        metadata["receiptId"] = result["receiptId"]
        emit("fulfillment_succeeded", metadata, accepted=result["accepted"], reused=result["reused"], idempotencyKey=result["idempotencyKey"])
        if payload["fault"] == "crash-after-fulfillment" and receive_count == 1:
            emit("fault_injected", metadata, fault=payload["fault"])
            raise RuntimeError("Injected crash AFTER successful simulated fulfillment; SQS must redeliver")
        emit("completed", metadata)
        return {"receiptId": result["receiptId"], "reused": result["reused"]}
    except Exception as error:
        emit("failed", metadata, errorType=type(error).__name__, error=str(error))
        raise
