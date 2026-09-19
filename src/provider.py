"""Simulated fulfillment receiver and its durable, independently queried ledger.

A receipt *is* the simulated side effect. A caller-supplied idempotency key lets
the receiver atomically store that side effect under a stable key. This models
receiver-side idempotency; it does not
claim exactly-once behavior for a separate payment or fulfillment service.
"""

import datetime
import hashlib
import json
import os
import re
import time
import uuid

_table = None
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SKU = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class PayloadConflict(ValueError):
    """The same logical order was retried with a different fulfillment payload."""


def validate_payload(payload):
    if not isinstance(payload, dict):
        raise ValueError("provider event must be an object")
    if not isinstance(payload.get("runId"), str) or not _IDENTIFIER.fullmatch(payload["runId"]):
        raise ValueError("runId must be 1-64 letters, digits, underscores or hyphens")
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
    if "idempotencyKey" in payload and payload["idempotencyKey"] != idempotency_key(payload["runId"], order["orderId"]):
        raise ValueError("idempotencyKey must be the SHA-256 of the compact JSON [runId,orderId] tuple")
    return payload


def require_active_lab():
    try:
        expires_at = int(os.environ["LAB_EXPIRES_AT"])
    except (KeyError, ValueError) as error:
        raise RuntimeError("LAB_EXPIRES_AT must be configured; refusing fulfillment") from error
    if time.time() >= expires_at:
        raise RuntimeError("Lab expired; refusing fulfillment. Delete the stack to remove resources.")


def ledger():
    global _table
    if _table is None:
        import boto3
        from botocore.config import Config
        _table = boto3.resource("dynamodb", config=Config(connect_timeout=1, read_timeout=2, retries={"total_max_attempts": 1})).Table(os.environ["LEDGER_TABLE"])
    return _table


def idempotency_key(run_id, order_id):
    # A JSON tuple prevents ambiguous concatenations such as (ab,c) vs (a,bc).
    identity = json.dumps([run_id, order_id], separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def emit(stage, payload, context, receipt, **fields):
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    print(json.dumps({
        "component": "provider", "stage": stage, "timestamp": timestamp,
        "runId": payload["runId"], "mode": payload["mode"],
        "orderId": payload["order"]["orderId"],
        "requestId": getattr(context, "aws_request_id", "local"),
        "workerRequestId": payload.get("workerRequestId"),
        "messageId": payload.get("messageId"), "receiveCount": payload.get("receiveCount"),
        "receiptId": receipt["receiptId"], "idempotencyKey": receipt["idempotencyKey"], **fields,
    }, sort_keys=True, separators=(",", ":")))


def handler(event, context):
    payload = validate_payload(event)
    require_active_lab()
    order = payload["order"]
    stable_key = idempotency_key(payload["runId"], order["orderId"])
    # Mode separates the comparison's ledgers; only the receiver contract's
    # optional key controls idempotency. Both handlers use the same provider.
    keyed = "idempotencyKey" in payload
    receipt_id = stable_key if keyed else uuid.uuid4().hex
    now = time.time()
    receipt = {
        "PK": f"RUN#{payload['runId']}#MODE#{payload['mode']}",
        "SK": f"RECEIPT#{receipt_id}",
        "receiptId": receipt_id,
        "runId": payload["runId"], "mode": payload["mode"],
        "orderId": order["orderId"], "sku": order["sku"], "quantity": order["quantity"],
        "idempotencyKey": stable_key if keyed else None,
        "createdAt": datetime.datetime.fromtimestamp(now, datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "invocationId": getattr(context, "aws_request_id", "local"),
        "messageId": payload.get("messageId"),
        "receiveCount": payload.get("receiveCount"),
        "expiresAt": int(now) + 172800,
    }
    accepted = True
    try:
        ledger().put_item(Item=receipt, ConditionExpression="attribute_not_exists(PK) AND attribute_not_exists(SK)")
    except Exception as error:
        code = getattr(error, "response", {}).get("Error", {}).get("Code")
        if not keyed or code != "ConditionalCheckFailedException":
            raise
        existing = ledger().get_item(Key={"PK": receipt["PK"], "SK": receipt["SK"]}, ConsistentRead=True).get("Item")
        if not existing:
            raise RuntimeError("Conditional write conflicted but no durable receipt was found") from error
        expected = {"runId": payload["runId"], "mode": payload["mode"], "orderId": order["orderId"], "sku": order["sku"], "quantity": order["quantity"], "idempotencyKey": stable_key}
        if any(existing.get(key) != value for key, value in expected.items()):
            emit("payload_conflict", payload, context, existing)
            raise PayloadConflict("Idempotency key already used with different fulfillment inputs") from error
        receipt = existing
        accepted = False
    emit("accepted" if accepted else "reused", payload, context, receipt, accepted=accepted, reused=not accepted)
    return {
        "receiptId": receipt["receiptId"], "accepted": accepted, "reused": not accepted,
        "idempotencyKey": receipt["idempotencyKey"], "createdAt": receipt["createdAt"],
    }
