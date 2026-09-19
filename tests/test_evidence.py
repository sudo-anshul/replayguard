"""Adversarial offline evidence tests. Fixtures here are synthetic, never demo data."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_case import canonical_hash, strict_json, validate_case, verify
from run_case import Collector, CollectionStopped, sanitized_error


CASE = {
    "schemaVersion": 1, "name": "crash-after-fulfillment",
    "orders": [{"orderId": "ORDER-1042", "sku": "FIELD-NOTES-3PACK", "quantity": 1}],
    "fault": {"type": "crash-after-fulfillment"},
    "bounds": {"maxWaitSeconds": 180, "maxMessages": 2, "drainGraceSeconds": 15},
}


def fixture():
    """Synthetic raw evidence with the shape of a successful AWS observation."""
    run = "test-only-run-0001"
    order = CASE["orders"][0]
    stable = hashlib.sha256(json.dumps([run, order["orderId"]], separators=(",", ":")).encode()).hexdigest()
    evidence = {"schemaVersion": 1, "provenance": "aws", "runId": run, "region": "us-east-1", "case": copy.deepcopy(CASE), "inputs": {"orders": copy.deepcopy(CASE["orders"])}, "fault": copy.deepcopy(CASE["fault"]), "messages": [], "receipts": {"vulnerable": [], "repaired": []}, "events": [], "apiErrors": [], "collection": {"lastLedgerReadAt": {"vulnerable": 140.1, "repaired": 140.2}, "unparsedLogEvents": 0}, "artifacts": {"canonicalCaseSha256": canonical_hash(CASE)}, "queueObservations": [], "status": "unresolved", "assertions": [], "attempts": {"vulnerable": [], "repaired": []}}
    for mode in ("vulnerable", "repaired"):
        message_id = f"sqs-message-{mode}"
        body = {"runId": run, "mode": mode, "order": order, "fault": "crash-after-fulfillment"}
        evidence["messages"].append({"mode": mode, "orderId": order["orderId"], "messageId": message_id, "sentAt": 90, "bodySha256": hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()})
        receipt_ids = ("receipt-v1", "receipt-v2") if mode == "vulnerable" else (stable, stable)
        for i, receipt_id in enumerate(dict.fromkeys(receipt_ids)):
            evidence["receipts"][mode].append({"PK": f"RUN#{run}#MODE#{mode}", "SK": f"RECEIPT#{receipt_id}", "receiptId": receipt_id, "runId": run, "mode": mode, **order, "createdAt": 101 + i * 10, "invocationId": f"provider-{mode}-{i}", "expiresAt": 100000, "messageId": message_id, "receiveCount": i + 1, "idempotencyKey": stable if mode == "repaired" else None})
        for stage, count, timestamp in (("received", 1, 100), ("fulfillment_succeeded", 1, 101), ("fault_injected", 1, 102), ("failed", 1, 103), ("received", 2, 110), ("fulfillment_succeeded", 2, 111), ("completed", 2, 112)):
            evidence["events"].append({"source": "worker", "component": "worker", "runId": run, "mode": mode, "orderId": order["orderId"], "messageId": message_id, "receiveCount": count, "requestId": f"worker-{mode}-{count}", "stage": stage, "receiptId": receipt_ids[count - 1] if stage != "received" else None, "fault": "crash-after-fulfillment" if stage == "fault_injected" else None, "eventTimestamp": timestamp * 1000, "accepted": not (mode == "repaired" and count == 2), "reused": mode == "repaired" and count == 2})
    for timestamp in (115, 120, 125, 130, 135, 140):
        evidence["queueObservations"].append({"observedAt": timestamp, "queue": {"visible": 0, "notVisible": 0, "delayed": 0}, "dlq": {"visible": 0, "notVisible": 0, "delayed": 0}})
    return evidence


class CaseValidationTests(unittest.TestCase):
    def test_valid_case(self):
        self.assertEqual(validate_case(copy.deepcopy(CASE)), CASE)

    def test_over_budget_orders_rejected(self):
        case = copy.deepcopy(CASE)
        case["orders"] *= 4
        with self.assertRaises(ValueError):
            validate_case(case)

    def test_duplicate_order_ids_rejected(self):
        case = copy.deepcopy(CASE)
        case["orders"] *= 2
        case["bounds"]["maxMessages"] = 4
        with self.assertRaisesRegex(ValueError, "unique"):
            validate_case(case)

    def test_unknown_fields_rejected(self):
        for target, key in ((None, "queueUrl"), ("bounds", "unlimited"), ("fault", "afterSeconds")):
            with self.subTest(target=target):
                case = copy.deepcopy(CASE)
                (case if target is None else case[target])[key] = 1
                with self.assertRaises(ValueError):
                    validate_case(case)

    def test_booleans_are_not_numbers(self):
        case = copy.deepcopy(CASE)
        case["orders"][0]["quantity"] = True
        with self.assertRaises(ValueError):
            validate_case(case)

    def test_long_observation_rejected(self):
        case = copy.deepcopy(CASE)
        case["bounds"]["maxWaitSeconds"] = 181
        with self.assertRaises(ValueError):
            validate_case(case)

    def test_message_limit_cannot_be_lower_than_inputs(self):
        case = copy.deepcopy(CASE)
        case["orders"].append({"orderId": "ORDER-2", "sku": "SKU", "quantity": 1})
        with self.assertRaisesRegex(ValueError, "maxMessages"):
            validate_case(case)

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        for raw in ('{"schemaVersion":1,"schemaVersion":1}', '{"n": NaN}', '{"n": Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_json(raw)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.evidence = fixture()

    def status(self):
        return verify(self.evidence)["status"]

    def test_complete_raw_evidence_passes(self):
        self.assertEqual(self.status(), "passed")

    def test_stored_status_and_attempts_are_not_trusted(self):
        self.evidence["status"] = "passed"
        self.evidence["assertions"] = [{"status": "passed"}]
        self.evidence["attempts"]["repaired"] = [{"receiveCount": 2}]
        self.evidence["events"] = []
        self.assertEqual(self.status(), "incomplete")

    def test_missing_receipts_remains_incomplete(self):
        self.evidence["receipts"]["repaired"] = []
        self.assertEqual(self.status(), "incomplete")

    def test_repaired_duplicate_is_unresolved(self):
        duplicate = copy.deepcopy(self.evidence["receipts"]["repaired"][0])
        duplicate.update(receiptId="second-repaired-receipt", SK="RECEIPT#second-repaired-receipt")
        self.evidence["receipts"]["repaired"].append(duplicate)
        self.assertEqual(self.status(), "unresolved")

    def test_first_success_does_not_prove_retry(self):
        self.evidence["events"] = [e for e in self.evidence["events"] if not (e["mode"] == "repaired" and e["receiveCount"] == 2)]
        self.assertEqual(self.status(), "incomplete")

    def test_wrong_sqs_message_cannot_prove_redelivery(self):
        for event in self.evidence["events"]:
            if event["mode"] == "repaired" and event["receiveCount"] == 2:
                event["messageId"] = "a-different-message"
        self.assertEqual(self.status(), "incomplete")

    def test_same_lambda_request_is_not_independent_redelivery(self):
        for event in self.evidence["events"]:
            if event["mode"] == "repaired":
                event["requestId"] = "same-request"
        self.assertEqual(self.status(), "incomplete")

    def test_retry_before_first_delivery_is_not_proof(self):
        for event in self.evidence["events"]:
            if event["mode"] == "repaired" and event["receiveCount"] == 2:
                event["eventTimestamp"] -= 20000
        self.assertEqual(self.status(), "unresolved")

    def test_fault_must_reference_independent_ledger_receipt(self):
        for event in self.evidence["events"]:
            if event["stage"] == "fault_injected":
                event["receiptId"] = "not-in-ledger"
        self.assertEqual(self.status(), "incomplete")

    def test_fault_must_follow_success_then_failure(self):
        self.evidence["events"] = [e for e in self.evidence["events"] if e["stage"] != "failed"]
        self.assertEqual(self.status(), "incomplete")

    def test_completed_stage_requires_matching_success(self):
        self.evidence["events"] = [e for e in self.evidence["events"] if not (e["stage"] == "fulfillment_succeeded" and e["receiveCount"] == 2)]
        self.assertEqual(self.status(), "incomplete")

    def test_fault_on_retry_contradicts_defined_fault(self):
        for event in self.evidence["events"]:
            if event["stage"] == "fault_injected":
                event["receiveCount"] = 2
        self.assertEqual(self.status(), "unresolved")

    def test_receipt_payload_conflict_is_unresolved(self):
        self.evidence["receipts"]["repaired"][0]["quantity"] = 2
        self.assertEqual(self.status(), "unresolved")

    def test_receipt_partition_conflict_is_unresolved(self):
        self.evidence["receipts"]["vulnerable"][0]["PK"] = "OTHER-RUN"
        self.assertEqual(self.status(), "unresolved")

    def test_duplicate_ledger_row_cannot_inflate_fulfillment_count(self):
        one = self.evidence["receipts"]["vulnerable"][0]
        self.evidence["receipts"]["vulnerable"] = [one, copy.deepcopy(one)]
        self.assertEqual(self.status(), "unresolved")

    def test_order_inputs_cannot_be_changed_after_run(self):
        self.evidence["inputs"]["orders"][0]["sku"] = "OTHER-SKU"
        self.assertEqual(self.status(), "unresolved")

    def test_sent_body_hash_must_match_case(self):
        self.evidence["messages"][0]["bodySha256"] = "0" * 64
        self.assertEqual(self.status(), "unresolved")

    def test_grace_observation_is_required(self):
        self.evidence["queueObservations"] = self.evidence["queueObservations"][:2]
        self.assertEqual(self.status(), "incomplete")

    def test_nonempty_queue_resets_grace(self):
        self.evidence["queueObservations"][-2]["queue"]["notVisible"] = 1
        self.assertEqual(self.status(), "incomplete")

    def test_final_nonempty_queue_cannot_pass(self):
        self.evidence["queueObservations"][-1]["queue"]["visible"] = 1
        self.assertEqual(self.status(), "incomplete")

    def test_dlq_receipt_is_unresolved(self):
        self.evidence["queueObservations"][-1]["dlq"]["visible"] = 1
        self.assertEqual(self.status(), "unresolved")

    def test_ledger_must_be_read_after_final_queue_observation(self):
        self.evidence["collection"]["lastLedgerReadAt"]["repaired"] = 120
        self.assertEqual(self.status(), "incomplete")

    def test_api_errors_and_log_parse_errors_remain_incomplete(self):
        self.evidence["apiErrors"] = [{"code": "AccessDeniedException"}]
        self.assertEqual(self.status(), "incomplete")
        self.evidence["apiErrors"] = []
        self.evidence["collection"]["unparsedLogEvents"] = 1
        self.assertEqual(self.status(), "incomplete")

    def test_receipts_created_after_fault_cannot_pass(self):
        for mode in ("vulnerable", "repaired"):
            for receipt in self.evidence["receipts"][mode]:
                receipt["createdAt"] = 999
        self.assertEqual(self.status(), "unresolved")

    def test_receipt_must_bind_to_original_sqs_message(self):
        for mode in ("vulnerable", "repaired"):
            for receipt in self.evidence["receipts"][mode]:
                receipt["messageId"] = "unrelated-message"
        self.assertEqual(self.status(), "unresolved")

    def test_retry_received_after_completion_cannot_pass(self):
        for event in self.evidence["events"]:
            if event["mode"] == "repaired" and event["stage"] == "received" and event["receiveCount"] == 2:
                event["eventTimestamp"] = 200000
        self.assertEqual(self.status(), "incomplete")

    def test_receiver_claiming_new_repaired_effect_is_unresolved(self):
        for event in self.evidence["events"]:
            if event["mode"] == "repaired" and event["receiveCount"] == 2 and event["stage"] == "fulfillment_succeeded":
                event["accepted"] = True
                event["reused"] = False
        self.assertEqual(self.status(), "unresolved")

    def test_non_aws_provenance_cannot_pass(self):
        self.evidence["provenance"] = "illustrative"
        self.assertEqual(self.status(), "incomplete")

    def test_malformed_evidence_is_not_a_crash_or_pass(self):
        for item in (None, [], {}, {"case": {}}, {**self.evidence, "artifacts": []}, {**self.evidence, "messages": [{"messageId": {}}]}):
            with self.subTest(item=type(item).__name__):
                self.assertNotEqual(verify(item)["status"], "passed")


class CollectorBoundTests(unittest.TestCase):
    def test_deadline_prevents_next_aws_call(self):
        collector = Collector.__new__(Collector)
        collector.deadline = 10
        collector.clock = lambda: 4
        collector.calls = 0
        with self.assertRaises(CollectionStopped):
            collector.call("test", lambda: self.fail("AWS must not be called"))

    def test_api_budget_prevents_next_aws_call(self):
        collector = Collector.__new__(Collector)
        collector.deadline = 100
        collector.clock = lambda: 1
        collector.calls = 300
        with self.assertRaises(CollectionStopped):
            collector.call("test", lambda: self.fail("AWS must not be called"))

    def test_aws_error_preserves_code_without_secrets(self):
        class AwsError(Exception):
            response = {"Error": {"Code": "AccessDenied", "Message": "Authorization=secret AWS_SESSION_TOKEN=token ASIA1234567890123456 denied"}}
        error = sanitized_error(AwsError(), "sqs.SendMessage")
        self.assertEqual(error["code"], "AccessDenied")
        for secret in ("=secret", "=token", "ASIA1234567890123456"):
            self.assertNotIn(secret, error["message"])


if __name__ == "__main__":
    unittest.main()
