"""V2 receiver: an opaque caller key controls an atomic simulated receipt.

The candidate field is only a ledger namespace. This receiver does not know
which key strategy is intended to pass. A receipt is the entire modeled effect.
"""
import datetime
from decimal import Decimal
import hashlib
import json
import os
import re
import time
import uuid

_table = None
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
FAULT = "after-commit-first-receive"


class PayloadConflict(ValueError):
    pass


class InjectedAfterCommit(RuntimeError):
    pass


def validate_order(order):
    if not isinstance(order, dict) or set(order) != {"orderId", "sku", "quantity"}:
        raise ValueError("Invalid order fields")
    if not isinstance(order["orderId"], str) or not IDENTIFIER.fullmatch(order["orderId"]):
        raise ValueError("Invalid orderId")
    if not isinstance(order["sku"], str) or not SKU.fullmatch(order["sku"]):
        raise ValueError("Invalid sku")
    if type(order["quantity"]) is not int or not 1 <= order["quantity"] <= 100:
        raise ValueError("Invalid quantity")
    return order


def stored_order(value):
    """DynamoDB returns numbers as Decimal; normalize only our integer contract."""
    if not isinstance(value, dict):
        raise RuntimeError("Stored receipt has an invalid order")
    order = dict(value)
    quantity = order.get("quantity")
    if isinstance(quantity, Decimal):
        if not quantity.is_finite() or quantity != quantity.to_integral_value() or not 1 <= quantity <= 100:
            raise RuntimeError("Stored receipt has an invalid quantity")
        order["quantity"] = int(quantity)
    try:
        return validate_order(order)
    except ValueError as error:
        raise RuntimeError("Stored receipt has an invalid order") from error


def validate(event):
    required = {"schemaVersion", "runId", "candidate", "order", "fault", "messageId", "receiveCount", "workerRequestId"}
    if not isinstance(event, dict) or not required <= set(event) or set(event) - required - {"key"}:
        raise ValueError("Invalid receiver fields")
    if type(event["schemaVersion"]) is not int or event["schemaVersion"] != 2:
        raise ValueError("Receiver requires schemaVersion 2")
    for name in ("runId", "candidate", "messageId", "workerRequestId"):
        if not isinstance(event[name], str) or not IDENTIFIER.fullmatch(event[name]):
            raise ValueError("Invalid " + name)
    validate_order(event["order"])
    if type(event["receiveCount"]) is not int or not 1 <= event["receiveCount"] <= 1000000:
        raise ValueError("Invalid receiveCount")
    if event["fault"] not in (FAULT, "none"):
        raise ValueError("Unknown fault")
    if "key" in event and (not isinstance(event["key"], str) or not event["key"].strip() or len(event["key"].encode("utf-8")) > 256):
        raise ValueError("key must be a nonempty string of at most 256 UTF-8 bytes")
    return event


def active():
    if time.time() >= int(os.environ.get("LAB_EXPIRES_AT", "0")):
        raise RuntimeError("Lab expired or not configured; refusing fulfillment")


def ledger():
    global _table
    if _table is None:
        import boto3
        from botocore.config import Config
        _table = boto3.resource("dynamodb", config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1})).Table(os.environ["LEDGER_TABLE"])
    return _table


def emit(stage, event, context, receipt, **fields):
    print(json.dumps({"schemaVersion": 2, "component": "provider", "stage": stage,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "runId": event["runId"], "candidate": event["candidate"], "order": event["order"],
        "orderId": event["order"]["orderId"], "messageId": event["messageId"], "receiveCount": event["receiveCount"],
        "workerRequestId": event["workerRequestId"], "requestId": context.aws_request_id,
        "receiptId": receipt["receiptId"], "key": event.get("key"), **fields}, sort_keys=True, separators=(",", ":")))


def handler(event, context):
    event = validate(event)
    active()
    key = event.get("key")
    receipt_id = hashlib.sha256(key.encode("utf-8")).hexdigest() if key is not None else uuid.uuid4().hex
    created = time.time()
    receipt = {"PK": f"RUN#{event['runId']}#CANDIDATE#{event['candidate']}", "SK": "RECEIPT#" + receipt_id,
        "receiptId": receipt_id, "runId": event["runId"], "candidate": event["candidate"],
        "order": dict(event["order"]), "key": key, "messageId": event["messageId"],
        "receiveCount": event["receiveCount"], "workerRequestId": event["workerRequestId"],
        "invocationId": context.aws_request_id,
        "createdAt": datetime.datetime.fromtimestamp(created, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "expiresAt": int(created) + 172800}
    accepted = True
    try:
        ledger().put_item(Item=receipt, ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)")
    except Exception as error:
        response = getattr(error, "response", None)
        details = response.get("Error") if isinstance(response, dict) else None
        code = details.get("Code") if isinstance(details, dict) else None
        if key is None or code != "ConditionalCheckFailedException":
            raise
        existing = ledger().get_item(Key={"PK": receipt["PK"], "SK": receipt["SK"]}, ConsistentRead=True).get("Item")
        if not existing:
            raise RuntimeError("Conditional collision without an observable receipt") from error
        identity = (existing.get("runId"), existing.get("candidate"), existing.get("key"))
        if identity != (event["runId"], event["candidate"], key):
            raise RuntimeError("Receipt namespace or key corruption") from error
        existing_order = stored_order(existing.get("order"))
        if existing_order != event["order"]:
            emit("payload_conflict", event, context, existing, existingOrder=existing_order)
            detail = {"schemaVersion": 2, "kind": "replayguard-key-conflict", "runId": event["runId"],
                "candidate": event["candidate"], "orderId": event["order"]["orderId"], "key": key,
                "messageId": event["messageId"], "workerRequestId": event["workerRequestId"],
                "receiveCount": event["receiveCount"], "receiptId": existing["receiptId"]}
            raise PayloadConflict(json.dumps(detail, sort_keys=True, separators=(",", ":"))) from error
        receipt, accepted = existing, False
    emit("accepted" if accepted else "reused", event, context, receipt, accepted=accepted, reused=not accepted)
    if accepted and event["receiveCount"] == 1 and event["fault"] == FAULT:
        emit("fault_injected", event, context, receipt, fault=FAULT)
        raise InjectedAfterCommit("Receipt committed; successful provider response intentionally withheld")
    return {"schemaVersion": 2, "receiptId": receipt["receiptId"], "key": key, "order": dict(event["order"]), "accepted": accepted, "reused": not accepted}
