#!/usr/bin/env python3
"""Local boto3 serialization regression; no AWS credentials or calls required.

Executes trusted source from the preserved first-attempt archive and this repo.
Requires the optional boto3 dependency from requirements.txt in a virtualenv.
"""
import argparse
import contextlib
import copy
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[3]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(data, name, origin):
    module = ModuleType(name)
    module.__file__ = origin
    exec(compile(data, origin, "exec"), module.__dict__)
    return module


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


def scenario(provider, worker, serializer, deserializer):
    class Ledger:
        def __init__(self):
            self.items = {}

        def put_item(self, Item, ConditionExpression):
            assert ConditionExpression == "attribute_not_exists(PK) AND attribute_not_exists(SK)"
            identity = (Item["PK"], Item["SK"])
            if identity in self.items:
                raise ConditionalFailure()
            self.items[identity] = copy.deepcopy(Item)

        def get_item(self, Key, ConsistentRead):
            assert ConsistentRead is True
            item = self.items[(Key["PK"], Key["SK"])]
            result = deserializer.deserialize(serializer.serialize(item))
            assert isinstance(result["order"]["quantity"], Decimal)
            return {"Item": result}

    class Transport:
        def __init__(self):
            self.errors, self.sequence = [], 0

        def invoke(self, **kwargs):
            assert kwargs["InvocationType"] == "RequestResponse"
            self.sequence += 1
            try:
                result = provider.handler(json.loads(kwargs["Payload"]), SimpleNamespace(aws_request_id="provider-" + str(self.sequence)))
                return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(result).encode())}
            except Exception as error:
                self.errors.append(type(error).__name__)
                return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": io.BytesIO(json.dumps({"errorType": type(error).__name__, "errorMessage": str(error)}).encode())}

    def event(order_id, count):
        body = {"schemaVersion": 2, "runId": "decimal-regression", "candidate": "sku-key", "order": {"orderId": order_id, "sku": "SAME-SKU", "quantity": 1}, "fault": "after-commit-first-receive"}
        return {"Records": [{"messageId": "message-" + order_id, "body": json.dumps(body), "attributes": {"ApproximateReceiveCount": str(count)}}]}

    ledger, transport, output = Ledger(), Transport(), io.StringIO()
    with patch.dict(os.environ, {"LAB_EXPIRES_AT": "9999999999", "PROVIDER_FUNCTION_ARN": "local-mock"}), patch.object(provider, "_table", ledger), patch.object(worker, "_lambda_client", transport), contextlib.redirect_stdout(output):
        try:
            worker.handler(event("A", 1), SimpleNamespace(aws_request_id="worker-A-first"))
            raise AssertionError("Required first-commit failure was absent")
        except RuntimeError as error:
            assert "InjectedAfterCommit" in str(error)
        retry = worker.handler(event("A", 2), SimpleNamespace(aws_request_id="worker-A-retry"))
        assert retry["reused"] is True
        try:
            result = worker.handler(event("B", 1), SimpleNamespace(aws_request_id="worker-B"))
            outcome = result["outcome"]
            error_type = None
        except RuntimeError as error:
            outcome, error_type = "raised", type(error).__name__
    events = [json.loads(line) for line in output.getvalue().splitlines()]
    conflicts = [event for event in events if event["stage"] == "payload_conflict"]
    return {"workerOutcomeForB": outcome, "workerErrorType": error_type, "providerErrors": transport.errors,
        "aRetryReused": retry["reused"], "receiptCount": len(ledger.items), "payloadConflictLogCount": len(conflicts),
        "conflictExistingOrder": conflicts[0]["existingOrder"] if conflicts else None,
        "conflictQuantityType": type(conflicts[0]["existingOrder"]["quantity"]).__name__ if conflicts else None}


def normalization_checks(provider):
    invalid = (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("1.5"), Decimal("0"), Decimal("101"), Decimal("1e10000"), True, "1", 1.0)
    for quantity in invalid:
        try:
            provider.stored_order({"orderId": "A", "sku": "X", "quantity": quantity})
            raise AssertionError("Malformed stored quantity was accepted: " + str(quantity))
        except RuntimeError:
            pass
    valid = (Decimal("1"), Decimal("1.0"), Decimal("100"))
    for quantity in valid:
        source = {"orderId": "A", "sku": "X", "quantity": quantity}
        normalized = provider.stored_order(source)
        assert type(normalized["quantity"]) is int
        assert isinstance(source["quantity"], Decimal)
    malformed = (None, {"orderId": "A", "sku": "X"}, {"orderId": "bad#id", "sku": "X", "quantity": Decimal(1)}, {"orderId": "A", "sku": "X", "quantity": Decimal(1), "extra": "not-supported"})
    for order in malformed:
        try:
            provider.stored_order(order)
            raise AssertionError("Malformed stored order was accepted")
        except RuntimeError:
            pass
    return {"invalidQuantitiesRejected": len(invalid), "invalidOrderShapesRejected": len(malformed), "validQuantitiesNormalizedWithoutMutation": len(valid)}


def run(root):
    import boto3
    from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
    from botocore.client import BaseClient
    archive_path = root / "web/aws-key-scope-attempt-1.zip"
    archive_bytes = archive_path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        historical = json.loads(archive.read("evidence.json"))
        originals = {name: archive.read("src/" + name) for name in ("key_provider.py", "key_worker.py")}
    for name, data in originals.items():
        assert sha(data) == historical["artifacts"]["sourceFiles"]["src/" + name], "Archived source hash differs"
    current = {name: (root / "src" / name).read_bytes() for name in originals}
    providers = [load(data["key_provider.py"], label + "_provider", label + "/src/key_provider.py") for label, data in (("archived", originals), ("current", current))]
    workers = [load(data["key_worker.py"], label + "_worker", label + "/src/key_worker.py") for label, data in (("archived", originals), ("current", current))]
    attempts = {"awsApi": 0, "socketConnect": 0}
    def blocked_api(*args, **kwargs):
        attempts["awsApi"] += 1
        raise AssertionError("AWS calls are forbidden in this local regression")
    def blocked_socket(*args, **kwargs):
        attempts["socketConnect"] += 1
        raise AssertionError("Network connection forbidden in this local regression")
    with patch.object(BaseClient, "_make_api_call", blocked_api), patch.object(socket.socket, "connect", blocked_socket), patch.object(socket.socket, "connect_ex", blocked_socket):
        original = scenario(providers[0], workers[0], TypeSerializer(), TypeDeserializer())
        repaired = scenario(providers[1], workers[1], TypeSerializer(), TypeDeserializer())
        bounded = normalization_checks(providers[1])
    assert original["workerOutcomeForB"] == "raised" and original["providerErrors"] == ["InjectedAfterCommit", "TypeError"] and original["payloadConflictLogCount"] == 0
    assert repaired["workerOutcomeForB"] == "rejected" and repaired["providerErrors"] == ["InjectedAfterCommit", "PayloadConflict"] and repaired["receiptCount"] == 1
    assert repaired["payloadConflictLogCount"] == 1 and repaired["conflictQuantityType"] == "int" and repaired["conflictExistingOrder"] == {"orderId": "A", "sku": "SAME-SKU", "quantity": 1}
    assert attempts == {"awsApi": 0, "socketConnect": 0}
    assert all((root / "src" / name).read_bytes() == data for name, data in current.items()), "Source changed during validation"
    assert archive_path.read_bytes() == archive_bytes, "Historical archive changed"
    return {"schemaVersion": 1, "kind": "replayguard-local-sdk-serialization-regression", "status": "passed",
        "recordedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "execution": "Local source with mocked Lambda/DynamoDB transport and actual boto3 value serialization; not AWS execution",
        "runtime": {"python": sys.version.split()[0], "boto3": boto3.__version__}, "blockedOperationAttempts": attempts,
        "historicalRunId": historical["runId"], "historicalArchiveSha256": sha(archive_bytes),
        "sourceSha256": {"archived": {name: sha(data) for name, data in originals.items()}, "current": {name: sha(data) for name, data in current.items()}},
        "validatorSha256": sha(Path(__file__).read_bytes()), "groupsPassed": 3,
        "originalSource": original, "repairedSource": repaired, "normalization": bounded,
        "limits": ["These are three local regression groups, not three AWS experiments.", "The original AWS observation and its cleanup follow-up remain separate, immutable records.", "AWS SQS scheduling, service behavior and current cloud state are not tested here."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        result = run(args.repo.resolve())
    except ImportError:
        print("This optional SDK integration check requires boto3 in a virtualenv; see requirements.txt. The normal -I -S unit suite needs no SDK.", file=sys.stderr)
        return 2
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("Output exists; use a fresh path to preserve prior validation")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
