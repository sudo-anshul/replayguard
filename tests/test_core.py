"""Local behavior checks; only a deployed run can prove AWS SQS redelivery."""

import contextlib
import copy
import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import provider
import worker


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class MemoryLedger:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression):
        key = (Item["PK"], Item["SK"])
        if key in self.items:
            raise ConditionalFailure()
        self.items[key] = copy.deepcopy(Item)

    def get_item(self, Key, ConsistentRead):
        if not ConsistentRead:
            raise AssertionError("Duplicate verification must read the committed receipt")
        return {"Item": copy.deepcopy(self.items.get((Key["PK"], Key["SK"])))}


def payload(mode="repaired", fault="crash-after-fulfillment"):
    return {"runId": "run-test", "mode": mode, "order": {"orderId": "order-1", "sku": "BOOK-001", "quantity": 1}, "fault": fault}


def keyed_payload(mode="repaired"):
    body = payload(mode=mode)
    body["idempotencyKey"] = worker.idempotency_key(body["runId"], body["order"]["orderId"])
    return body


def sqs_event(body, count=1):
    return {"Records": [{"messageId": "message-1", "body": json.dumps(body), "attributes": {"ApproximateReceiveCount": str(count)}}]}


class DirectProviderClient:
    """Mock transport only: calls the actual provider implementation."""
    def invoke(self, FunctionName, InvocationType, Payload):
        if InvocationType != "RequestResponse":
            raise AssertionError("Worker must confirm success before fault injection")
        result = provider.handler(json.loads(Payload), SimpleNamespace(aws_request_id="provider-request"))
        return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(result).encode())}


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.table = MemoryLedger()
        self.env = patch.dict(os.environ, {"LAB_EXPIRES_AT": "9999999999", "PROVIDER_FUNCTION_ARN": "provider-test"})
        self.env.start()
        self.provider_patch = patch.object(provider, "_table", self.table)
        self.provider_patch.start()
        self.client_patch = patch.object(worker, "_lambda_client", DirectProviderClient())
        self.client_patch.start()
        self.context = SimpleNamespace(aws_request_id="worker-request")
        self.output = io.StringIO()
        self.print_patch = contextlib.redirect_stdout(self.output)
        self.print_patch.__enter__()

    def tearDown(self):
        self.print_patch.__exit__(None, None, None)
        self.client_patch.stop()
        self.provider_patch.stop()
        self.env.stop()

    def test_repaired_replays_return_one_durable_receipt(self):
        first = provider.handler(keyed_payload(), self.context)
        second = provider.handler(keyed_payload(), self.context)
        self.assertEqual(first["receiptId"], second["receiptId"])
        self.assertTrue(first["accepted"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(self.table.items), 1)

    def test_changed_payload_cannot_reuse_order_key(self):
        provider.handler(keyed_payload(), self.context)
        changed = keyed_payload()
        changed["order"]["quantity"] = 2
        with self.assertRaises(provider.PayloadConflict):
            provider.handler(changed, self.context)
        self.assertEqual(len(self.table.items), 1)
        self.assertEqual(next(iter(self.table.items.values()))["quantity"], 1)

    def test_idempotency_key_scopes_order_to_run(self):
        first = provider.handler(keyed_payload(), self.context)
        other = keyed_payload()
        other["runId"] = "other-run"
        other["idempotencyKey"] = worker.idempotency_key(other["runId"], other["order"]["orderId"])
        second = provider.handler(other, self.context)
        self.assertNotEqual(first["receiptId"], second["receiptId"])
        self.assertNotEqual(provider.idempotency_key("ab", "c"), provider.idempotency_key("a", "bc"))

    def test_same_receiver_honors_key_independently_of_mode_label(self):
        first = provider.handler(keyed_payload(mode="vulnerable"), self.context)
        second = provider.handler(keyed_payload(mode="vulnerable"), self.context)
        self.assertEqual(first["receiptId"], second["receiptId"])
        self.assertTrue(second["reused"])
        third = provider.handler(payload(mode="repaired"), self.context)
        fourth = provider.handler(payload(mode="repaired"), self.context)
        self.assertNotEqual(third["receiptId"], fourth["receiptId"])
        self.assertFalse(fourth["reused"])
        self.assertEqual(len(self.table.items), 3)

    def test_receiver_rejects_arbitrary_idempotency_key(self):
        body = payload()
        body["idempotencyKey"] = "random-attempt-id"
        with self.assertRaisesRegex(ValueError, "idempotencyKey"):
            provider.handler(body, self.context)
        self.assertEqual(len(self.table.items), 0)

    def test_vulnerable_real_handler_crash_then_retry_duplicates(self):
        body = payload(mode="vulnerable")
        with self.assertRaisesRegex(RuntimeError, "Injected crash AFTER"):
            worker.handler(sqs_event(body), self.context)
        self.assertEqual(len(self.table.items), 1, "The fault must occur after the durable side effect")
        worker.handler(sqs_event(body, count=2), self.context)
        self.assertEqual(len(self.table.items), 2)

    def test_repaired_real_handler_crash_then_retry_reuses(self):
        body = payload()
        with self.assertRaisesRegex(RuntimeError, "Injected crash AFTER"):
            worker.handler(sqs_event(body), self.context)
        retry = worker.handler(sqs_event(body, count=2), self.context)
        self.assertTrue(retry["reused"])
        self.assertEqual(len(self.table.items), 1)
        logs = [json.loads(line) for line in self.output.getvalue().splitlines()]
        worker_logs = [log for log in logs if log["component"] == "worker"]
        self.assertEqual([log["stage"] for log in worker_logs], ["received", "fulfillment_succeeded", "fault_injected", "failed", "received", "fulfillment_succeeded", "completed"])
        required = {"runId", "mode", "orderId", "messageId", "receiveCount", "requestId", "stage", "receiptId", "timestamp"}
        self.assertTrue(all(required <= log.keys() for log in worker_logs))

    def test_control_without_fault_completes_first_delivery(self):
        result = worker.handler(sqs_event(payload(fault="none")), self.context)
        self.assertFalse(result["reused"])
        self.assertEqual(len(self.table.items), 1)
        self.assertNotIn('"fault_injected"', self.output.getvalue())

    def test_failed_provider_cannot_be_claimed_as_success_or_injected_fault(self):
        class FailingProvider:
            def invoke(self, **kwargs):
                return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": io.BytesIO(b'{"errorType":"Unavailable","errorMessage":"provider failed"}')}
        with patch.object(worker, "_lambda_client", FailingProvider()):
            with self.assertRaisesRegex(RuntimeError, "Fulfillment provider failed"):
                worker.handler(sqs_event(payload()), self.context)
        self.assertNotIn('"fulfillment_succeeded"', self.output.getvalue())
        self.assertNotIn('"fault_injected"', self.output.getvalue())
        self.assertEqual(len(self.table.items), 0)

    def test_expiry_prevents_side_effects(self):
        with patch.dict(os.environ, {"LAB_EXPIRES_AT": "1"}):
            with self.assertRaisesRegex(RuntimeError, "Lab expired"):
                provider.handler(payload(), self.context)
            with self.assertRaisesRegex(RuntimeError, "Lab expired"):
                worker.handler(sqs_event(payload()), self.context)
        self.assertEqual(len(self.table.items), 0)

    def test_input_validation_rejects_ambiguous_or_excessive_values(self):
        for field, value in [("quantity", True), ("quantity", 0), ("quantity", 101), ("sku", ""), ("orderId", "contains#delimiter")]:
            with self.subTest(field=field, value=value):
                body = payload()
                body["order"][field] = value
                with self.assertRaises(ValueError):
                    provider.handler(body, self.context)
                with self.assertRaises(ValueError):
                    worker.handler(sqs_event(body), self.context)
        self.assertEqual(len(self.table.items), 0)


if __name__ == "__main__":
    unittest.main()
