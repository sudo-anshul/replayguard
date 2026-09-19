"""Offline controls only. These mocks do not establish real SQS/AWS execution."""
import contextlib
import copy
import datetime as dt
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "scripts"), str(ROOT / "infra")]
import key_provider as provider
import key_worker as worker
import run_key_case as runner
import verify_key_case as verifier
import export_key_case as exporter
from build_template import build_template


class ConditionalFailure(Exception):
    response = {"Error": {"Code": "ConditionalCheckFailedException"}}


class MemoryLedger:
    def __init__(self):
        self.items = {}

    def put_item(self, Item, ConditionExpression):
        if ConditionExpression != "attribute_not_exists(PK) AND attribute_not_exists(SK)":
            raise AssertionError("Atomic conditional creation required")
        key = (Item["PK"], Item["SK"])
        if key in self.items:
            raise ConditionalFailure()
        self.items[key] = copy.deepcopy(Item)

    def get_item(self, Key, ConsistentRead):
        if ConsistentRead is not True:
            raise AssertionError("Conflict resolution must use a consistent read")
        # boto3's DynamoDB resource deserializes even integral numbers as Decimal.
        # The same shape is checked separately with its real TypeDeserializer.
        def deserialize(value):
            if type(value) is int:
                return Decimal(value)
            if isinstance(value, dict):
                return {k: deserialize(v) for k, v in value.items()}
            if isinstance(value, list):
                return [deserialize(v) for v in value]
            return copy.deepcopy(value)
        return {"Item": deserialize(self.items.get((Key["PK"], Key["SK"])))}


class DirectTransport:
    """Actual receiver source with a mock Lambda wire response, including errors."""
    def __init__(self):
        self.sequence = 0

    def invoke(self, FunctionName, InvocationType, Payload):
        if InvocationType != "RequestResponse":
            raise AssertionError("Synchronous response required")
        self.sequence += 1
        try:
            result = provider.handler(json.loads(Payload), SimpleNamespace(aws_request_id="provider-" + str(self.sequence)))
            return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(result).encode())}
        except Exception as error:
            return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": io.BytesIO(json.dumps({"errorType": type(error).__name__, "errorMessage": str(error)}).encode())}


def case_bytes():
    return (ROOT / "cases/aws-key-scope.json").read_bytes()


def provider_input(candidate="order-key", order=None, fault="none", key="opaque-business-key", count=1):
    order = order or {"orderId": "A", "sku": "SAME-SKU", "quantity": 1}
    body = {"schemaVersion": 2, "runId": "run-test", "candidate": candidate, "order": order,
            "fault": fault, "messageId": "message-A", "workerRequestId": "worker-A", "receiveCount": count}
    if key is not None:
        body["key"] = key
    return body


class ReceiverWorkerTests(unittest.TestCase):
    def setUp(self):
        self.table = MemoryLedger()
        self.stack = contextlib.ExitStack()
        self.stack.enter_context(patch.dict(os.environ, {"LAB_EXPIRES_AT": "9999999999", "PROVIDER_FUNCTION_ARN": "test-provider"}))
        self.stack.enter_context(patch.object(provider, "_table", self.table))
        self.stack.enter_context(patch.object(worker, "_lambda_client", DirectTransport()))
        self.logs = self.stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        self.context = SimpleNamespace(aws_request_id="worker-A")

    def tearDown(self):
        self.stack.close()

    def test_opaque_key_reuse_and_namespace_independence(self):
        first = provider.handler(provider_input(candidate="arbitrary-namespace"), self.context)
        second = provider.handler(provider_input(candidate="arbitrary-namespace"), self.context)
        self.assertEqual(first["receiptId"], second["receiptId"])
        self.assertTrue(second["reused"])
        self.assertEqual(len(self.table.items), 1)

    def test_same_key_cannot_suppress_payload_conflict_silently(self):
        provider.handler(provider_input(), self.context)
        for change in ({"orderId": "B"}, {"quantity": 2}, {"sku": "OTHER"}):
            body = provider_input()
            body["order"].update(change)
            with self.assertRaises(provider.PayloadConflict):
                provider.handler(body, self.context)
        self.assertEqual(len(self.table.items), 1)

    def test_different_keys_allow_same_sku_and_no_key_duplicates(self):
        provider.handler(provider_input(key="A"), self.context)
        provider.handler(provider_input(key="B", order={"orderId": "B", "sku": "SAME-SKU", "quantity": 1}), self.context)
        provider.handler(provider_input(key=None), self.context)
        provider.handler(provider_input(key=None), self.context)
        self.assertEqual(len(self.table.items), 4)

    def test_fault_after_commit_only_and_reuse_does_not_reinject(self):
        body = provider_input(fault=provider.FAULT)
        with self.assertRaises(provider.InjectedAfterCommit):
            provider.handler(body, self.context)
        self.assertEqual(len(self.table.items), 1)
        result = provider.handler(body, self.context)
        self.assertTrue(result["reused"])
        stages = [json.loads(line)["stage"] for line in self.logs.getvalue().splitlines()]
        self.assertEqual(stages, ["accepted", "fault_injected", "reused"])

    def test_late_acceptance_does_not_claim_first_receive_fault(self):
        result = provider.handler(provider_input(fault=provider.FAULT, count=2), self.context)
        self.assertTrue(result["accepted"])
        self.assertNotIn("fault_injected", self.logs.getvalue())

    def test_worker_propagates_post_commit_failure_and_retry_reuses(self):
        body = verifier.message_body("run-test", "order-key", {"orderId": "A", "sku": "X", "quantity": 1})
        event = {"Records": [{"messageId": "message-A", "body": json.dumps(body), "attributes": {"ApproximateReceiveCount": "1"}}]}
        with self.assertRaisesRegex(RuntimeError, "InjectedAfterCommit"):
            worker.handler(event, self.context)
        self.assertNotIn("fulfillment_succeeded", self.logs.getvalue())
        self.assertEqual(len(self.table.items), 1)
        event["Records"][0]["attributes"]["ApproximateReceiveCount"] = "2"
        result = worker.handler(event, SimpleNamespace(aws_request_id="worker-retry"))
        self.assertTrue(result["reused"])

    def test_recognized_conflict_is_terminal_but_unknown_error_propagates(self):
        body = verifier.message_body("run-test", "sku-key", {"orderId": "A", "sku": "X", "quantity": 1})
        body["fault"] = "none"
        event = {"Records": [{"messageId": "message-A", "body": json.dumps(body), "attributes": {"ApproximateReceiveCount": "1"}}]}
        worker.handler(event, self.context)
        body["order"]["orderId"] = "B"
        event["Records"][0].update(messageId="message-B", body=json.dumps(body))
        result = worker.handler(event, SimpleNamespace(aws_request_id="worker-B"))
        self.assertEqual(result["outcome"], "rejected")
        self.assertEqual(len(self.table.items), 1)
        class Failure:
            def invoke(self, **kwargs):
                return {"StatusCode": 200, "FunctionError": "Unhandled", "Payload": io.BytesIO(b'{"errorType":"PayloadConflict","errorMessage":"not the expected contract"}')}
        with patch.object(worker, "_lambda_client", Failure()), self.assertRaises(RuntimeError):
            worker.handler(event, self.context)

    def test_input_and_expiry_rejection_precede_effect(self):
        for invalid in (True, 0, 101):
            body = provider_input()
            body["order"]["quantity"] = invalid
            with self.assertRaises(ValueError):
                provider.handler(body, self.context)
        with patch.dict(os.environ, {"LAB_EXPIRES_AT": "1"}), self.assertRaises(RuntimeError):
            provider.handler(provider_input(), self.context)
        self.assertEqual(self.table.items, {})

    def test_decimal_stored_order_is_normalized_without_mutating_observation(self):
        provider.handler(provider_input(), self.context)
        item = next(iter(self.table.items.values()))
        loaded = self.table.get_item(Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True)["Item"]
        self.assertIsInstance(loaded["order"]["quantity"], Decimal)
        normalized = provider.stored_order(loaded["order"])
        self.assertIs(type(normalized["quantity"]), int)
        self.assertIsInstance(loaded["order"]["quantity"], Decimal)
        changed = provider_input(order={"orderId": "B", "sku": "SAME-SKU", "quantity": 1})
        with self.assertRaises(provider.PayloadConflict):
            provider.handler(changed, self.context)
        conflicts = [json.loads(line) for line in self.logs.getvalue().splitlines() if '"payload_conflict"' in line]
        self.assertEqual(len(conflicts), 1)
        self.assertIs(type(conflicts[0]["existingOrder"]["quantity"]), int)

    def test_malformed_stored_values_fail_closed(self):
        for quantity in (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"), Decimal("1.5"), Decimal("0"), Decimal("101"), Decimal("1e10000"), True, "1", 1.0):
            with self.subTest(quantity=str(quantity)), self.assertRaises(RuntimeError):
                provider.stored_order({"orderId": "A", "sku": "X", "quantity": quantity})
        for value in (None, {"orderId": "A", "sku": "X"}, {"orderId": "bad#id", "sku": "X", "quantity": Decimal(1)}, {"orderId": "A", "sku": "X", "quantity": Decimal(1), "extra": "not-supported"}):
            with self.assertRaises(RuntimeError):
                provider.stored_order(value)


def executed_fixture(extra_no_key=False):
    """Generate linked mock observations using real source; never write as AWS evidence."""
    raw = case_bytes()
    case = verifier.validate_case(verifier.strict_json(raw))
    evidence = runner.blank_evidence(case, raw, "us-east-1", "fixture-only", ROOT)
    evidence["runId"] = "fixture-run"
    evidence["deployment"] = {"stackArn": "arn:aws:cloudformation:us-east-1:123:stack/fixture-only/unique", "templateSourceSha256": {name: evidence["artifacts"]["sourceFiles"][name] for name in ("src/key_worker.py", "src/key_provider.py")}}
    ledger, transport = MemoryLedger(), DirectTransport()
    base = dt.datetime(2026, 9, 20, tzinfo=dt.timezone.utc).timestamp()
    tick = [0]
    def stamp(advance=1):
        tick[0] += advance
        return dt.datetime.fromtimestamp(base + tick[0], dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    def send(candidate, order, phase):
        evidence["messages"].append({"candidate": candidate, "orderId": order["orderId"], "phase": phase,
            "messageId": "m-" + candidate + "-" + order["orderId"], "sentAt": stamp(),
            "bodySha256": verifier.digest(verifier.message_body(evidence["runId"], candidate, order))})
    def execute(candidate, order, count):
        message = next(m for m in evidence["messages"] if m["candidate"] == candidate and m["orderId"] == order["orderId"])
        event = {"Records": [{"messageId": message["messageId"], "body": verifier.canonical(verifier.message_body(evidence["runId"], candidate, order)), "attributes": {"ApproximateReceiveCount": str(count)}}]}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            try:
                worker.handler(event, SimpleNamespace(aws_request_id="w-" + str(tick[0])))
            except RuntimeError:
                pass
        logs = [json.loads(line) for line in output.getvalue().splitlines()]
        for log in logs:
            at = stamp()
            log.update(timestamp=at, eventTimestamp=int(verifier.timestamp(at) * 1000), collectedAt=at,
                       source=log["component"], eventId="e-" + str(tick[0]))
            evidence["events"].append(log)
    def snapshot():
        for candidate in verifier.CANDIDATES:
            items = [copy.deepcopy(item) for item in ledger.items.values() if item["candidate"] == candidate]
            at = stamp()
            evidence["receipts"][candidate] = items
            evidence["ledgerObservations"].append({"candidate": candidate, "observedAt": at, "consistent": True, "items": items})
            evidence["collection"]["lastLedgerReadAt"][candidate] = at
    with patch.dict(os.environ, {"LAB_EXPIRES_AT": "9999999999", "PROVIDER_FUNCTION_ARN": "test"}), patch.object(provider, "_table", ledger), patch.object(worker, "_lambda_client", transport), patch.object(provider.time, "time", lambda: base + tick[0]):
        a, b = case["orders"]
        for candidate in verifier.CANDIDATES:
            send(candidate, a, 1)
            execute(candidate, a, 1)
        snapshot()
        evidence["phaseGate"] = verifier.first_order_gate(evidence, stamp())
        if evidence["phaseGate"] is None:
            raise AssertionError("Fixture A gate not established")
        for candidate in verifier.CANDIDATES:
            send(candidate, b, 2)
        for candidate in verifier.CANDIDATES:
            execute(candidate, a, 2)
            execute(candidate, b, 1)
            if candidate != "sku-key":
                execute(candidate, b, 2)
        if extra_no_key:
            execute("no-key", a, 3)
            execute("no-key", b, 3)
        empty = {"visible": 0, "notVisible": 0, "delayed": 0}
        evidence["queueObservations"] = [{"observedAt": stamp(), "queue": empty, "dlq": empty},
                                         {"observedAt": stamp(21), "queue": empty, "dlq": empty}]
        snapshot()
        evidence["collection"]["lastLogReadAt"] = stamp()
    evidence["cleanup"] = {"status": "deleted", "verified": True, "stackArn": evidence["deployment"]["stackArn"], "lastStackStatus": "DELETE_COMPLETE"}
    return evidence


class VerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = executed_fixture()

    def test_executed_mock_matrix_has_separate_business_and_experiment_states(self):
        result = verifier.verify(self.fixture)
        self.assertEqual(result["experimentStatus"], "passed", [a for a in result["assertions"] if a["status"] != "passed"])
        self.assertEqual([r["status"] for r in result["candidateResults"]], ["violation", "violation", "passed"])
        self.assertEqual([r["receiptCounts"] for r in result["candidateResults"]], [{"ORDER-A": 2, "ORDER-B": 2}, {"ORDER-A": 1, "ORDER-B": 0}, {"ORDER-A": 1, "ORDER-B": 1}])

    def test_extra_sqs_deliveries_are_kept(self):
        result = verifier.verify(executed_fixture(extra_no_key=True))
        self.assertEqual(result["experimentStatus"], "passed")
        self.assertEqual(result["candidateResults"][0]["receiptCounts"], {"ORDER-A": 3, "ORDER-B": 3})

    def test_tampering_and_missing_evidence_cannot_pass(self):
        mutations = {
            "missing gate": lambda e: e.update(phaseGate=None),
            "unknown receipt payload": lambda e: e["receipts"]["order-key"][0]["order"].update(quantity=99),
            "missing snapshot": lambda e: e["receipts"].update({"order-key": None}),
            "wrong message": lambda e: e["events"][0].update(messageId="unknown-message"),
            "missing provider fault": lambda e: e.update(events=[x for x in e["events"] if x["stage"] != "fault_injected"]),
            "missing conflict": lambda e: e.update(events=[x for x in e["events"] if x["stage"] != "payload_conflict"]),
            "unknown completed worker": lambda e: e["events"][-1].update(requestId="unknown-worker"),
            "premature B send": lambda e: e["messages"][3].update(sentAt=e["messages"][0]["sentAt"]),
            "false consistent read": lambda e: e.update(ledgerObservations=[]),
            "incomplete collection": lambda e: e["apiErrors"].append({"code": "Timeout"}),
            "missing drain": lambda e: e.update(queueObservations=[]),
            "bad source binding": lambda e: e["deployment"]["templateSourceSha256"].update({"src/key_worker.py": "0" * 64}),
            "boolean receipt quantity": lambda e: e["receipts"]["order-key"][0]["order"].update(quantity=True),
            "boolean event quantity": lambda e: e["events"][0]["order"].update(quantity=True),
            "orphan provider invocation": lambda e: next(x for x in e["events"] if x["source"] == "provider").update(workerRequestId="not-a-worker"),
            "fabricated final read time": lambda e: e["collection"]["lastLedgerReadAt"].update({"order-key": "2026-09-21T00:00:00Z"}),
            "receipt written after claimed fault": lambda e: e["receipts"]["order-key"][0].update(createdAt="2026-09-21T00:00:00Z"),
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                evidence = copy.deepcopy(self.fixture)
                mutate(evidence)
                self.assertNotEqual(verifier.verify(evidence)["experimentStatus"], "passed")

    def test_stored_verdict_is_recomputed_and_false_claim_rejected(self):
        evidence = copy.deepcopy(self.fixture)
        evidence["result"] = verifier.verify(evidence)
        self.assertEqual(verifier.verify(evidence)["experimentStatus"], "passed")
        evidence["result"]["candidateResults"][0]["status"] = "passed"
        self.assertEqual(verifier.verify(evidence)["experimentStatus"], "unresolved")

    def test_required_source_hashes_cannot_pass_when_absent_or_malformed(self):
        mutations = (
            lambda e: (e["deployment"].update(templateSourceSha256={"unrelated": "anything"}), e["artifacts"].update(sourceFiles={})),
            lambda e: e["artifacts"]["sourceFiles"].pop("src/key_provider.py"),
            lambda e: e["deployment"]["templateSourceSha256"].pop("src/key_worker.py"),
            lambda e: (e["deployment"]["templateSourceSha256"].update({"src/key_worker.py": None}), e["artifacts"]["sourceFiles"].update({"src/key_worker.py": None})),
            lambda e: (e["deployment"]["templateSourceSha256"].update({"src/key_worker.py": "same-but-not-a-hash"}), e["artifacts"]["sourceFiles"].update({"src/key_worker.py": "same-but-not-a-hash"})),
        )
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                evidence = copy.deepcopy(self.fixture)
                evidence["result"] = verifier.verify(evidence)
                mutate(evidence)
                self.assertNotEqual(verifier.verify(evidence)["experimentStatus"], "passed")
                self.assertNotEqual(verifier.verify(evidence, check_claims=False)["experimentStatus"], "passed")

    def test_opposite_worker_terminal_cannot_hide_behind_a_completion(self):
        evidence = copy.deepcopy(self.fixture)
        evidence["result"] = verifier.verify(evidence)
        event = copy.deepcopy(next(e for e in evidence["events"] if e.get("source") == "worker" and e.get("stage") == "completed" and e.get("candidate") == "order-key"))
        event.pop("outcome", None)
        event.pop("key", None)
        event.update(stage="failed", errorType="RuntimeError", error="execution failed", eventId="opposite-terminal")
        evidence["events"].append(event)
        self.assertEqual(verifier.verify(evidence)["experimentStatus"], "unresolved")
        direct = verifier.verify(evidence, check_claims=False)
        self.assertEqual(next(a["status"] for a in direct["assertions"] if a["id"] == "invocation-consistency"), "unresolved")

    def test_opposite_provider_outcomes_cannot_share_one_invocation(self):
        evidence = copy.deepcopy(self.fixture)
        event = copy.deepcopy(next(e for e in evidence["events"] if e.get("source") == "provider" and e.get("stage") == "reused" and e.get("candidate") == "order-key"))
        event.update(stage="accepted", accepted=True, reused=False, eventId="opposite-provider-outcome")
        evidence["events"].append(event)
        self.assertEqual(verifier.verify(evidence, check_claims=False)["experimentStatus"], "unresolved")

    def test_different_invocation_failure_and_retry_remain_valid(self):
        # Each expected first failure and retry has its own request ID. The
        # contradiction guard must not merge all deliveries of an order.
        self.assertEqual(verifier.conflicting_invocations(self.fixture["events"]), [])
        self.assertEqual(verifier.verify(self.fixture)["experimentStatus"], "passed")

    def test_unconfirmed_cleanup_is_separate_unresolved_operation(self):
        evidence = copy.deepcopy(self.fixture)
        evidence["cleanup"] = {"status": "unconfirmed", "verified": False}
        result = verifier.verify(evidence)
        self.assertEqual(result["experimentStatus"], "passed")
        self.assertEqual(result["operationalStatus"], "unresolved")

    def test_case_rejects_weakened_bounds_or_non_counterexample(self):
        for field, value in (("maxMessages", 7), ("maxWaitSeconds", 421), ("drainGraceSeconds", 1)):
            case = copy.deepcopy(self.fixture["case"])
            case["bounds"][field] = value
            with self.assertRaises(ValueError):
                verifier.validate_case(case)
        case = copy.deepcopy(self.fixture["case"])
        case["orders"][1]["sku"] = "OTHER"
        with self.assertRaises(ValueError):
            verifier.validate_case(case)


class CollectorCleanupExportTests(unittest.TestCase):
    def setUp(self):
        # Unit tests work with -I -S and never need an installed SDK or network.
        # Actual SDK deserialization is a separate explicitly labelled check.
        names = ("boto3", "boto3.dynamodb", "boto3.dynamodb.conditions", "botocore", "botocore.config")
        modules = {name: ModuleType(name) for name in names}
        for module in modules.values():
            module.__path__ = []
        class Key:
            def __init__(self, name): pass
            def eq(self, value): return self
            def begins_with(self, value): return self
            def __and__(self, other): return self
        modules["boto3"].Session = lambda **kwargs: None
        modules["boto3.dynamodb.conditions"].Key = Key
        modules["botocore.config"].Config = lambda **kwargs: kwargs
        self.sdk_patch = patch.dict(sys.modules, modules)
        self.sdk_patch.start()
        self.addCleanup(self.sdk_patch.stop)

    def collector(self):
        c = runner.Collector.__new__(runner.Collector)
        c.evidence = runner.blank_evidence(verifier.strict_json(case_bytes()), case_bytes(), "us-east-1", "test", ROOT)
        c.outputs = {"Expiry": "9999999999", "QueueUrl": "q"}
        c.calls, c.deadline, c.clock = 0, 100, lambda: 0
        return c

    def test_call_budget_and_deadline_prevent_next_request(self):
        c = self.collector()
        called = []
        c.calls = runner.MAX_API_CALLS
        with self.assertRaises(runner.Stopped):
            c.call("test", lambda: called.append(True))
        c.calls, c.deadline = 0, 5
        with self.assertRaises(runner.Stopped):
            c.call("test", lambda: called.append(True))
        self.assertEqual(called, [])

    def test_phase_gate_expiry_and_ambiguous_send_do_not_resubmit(self):
        c = self.collector()
        calls = []
        c.sqs = SimpleNamespace(send_message=lambda **kwargs: calls.append(kwargs) or {})
        order = c.evidence["case"]["orders"][1]
        with self.assertRaises(runner.Stopped):
            c.send("no-key", order, 2)
        self.assertEqual(calls, [])
        with self.assertRaises(runner.Stopped):
            c.send("no-key", c.evidence["case"]["orders"][0], 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(c.evidence["messages"], [])
        c.outputs["Expiry"] = "1"
        with self.assertRaises(runner.Stopped):
            c.send("no-key", order, 1)
        self.assertEqual(len(calls), 1)

    def test_partial_receipt_pagination_never_replaces_snapshot(self):
        c = self.collector()
        c.table = SimpleNamespace(query=lambda **kwargs: {"Items": [{"receiptId": "partial"}], "LastEvaluatedKey": {"PK": "more"}})
        with self.assertRaises(runner.Stopped):
            c.receipts()
        self.assertIsNone(c.evidence["receipts"]["no-key"])
        self.assertEqual(c.evidence["ledgerObservations"], [])

    def test_cleanup_does_not_select_hosting_or_an_untagged_stack(self):
        stack = {"StackId": "arn:aws:cloudformation:us-east-1:123:stack/replayguard-hosting/id", "Tags": [{"Key": "Project", "Value": "ReplayGuard"}]}
        with self.assertRaises(ValueError):
            runner.verified_target(stack, {"Experiment": "key-scope"})

    def test_mapping_failure_cannot_prevent_exact_stack_deletion(self):
        calls = []
        class Session:
            def client(self, service, **kwargs):
                if service == "lambda":
                    def disable(**kwargs):
                        raise RuntimeError("mapping unavailable")
                    return SimpleNamespace(update_event_source_mapping=disable)
                return SimpleNamespace(delete_stack=lambda **kwargs: calls.append(kwargs), describe_stacks=lambda **kwargs: {"Stacks": [{"StackStatus": "DELETE_COMPLETE"}]})
        record = {"errors": []}
        target = {"stackArn": "arn:aws:cloudformation:us-east-1:123:stack/test/unique", "mappingId": "mapping"}
        runner.cleanup_stack(Session(), target, record)
        self.assertEqual(calls, [{"StackName": target["stackArn"]}])
        self.assertTrue(record["verified"])
        self.assertEqual(record["status"], "deleted")
        self.assertEqual(len(record["errors"]), 1)

    def test_null_or_malformed_sdk_error_metadata_does_not_abort_cleanup(self):
        for response in (None, {"Error": None}, {"Error": "unexpected"}, "unexpected"):
            with self.subTest(response=response):
                class TransportFailure(Exception):
                    pass
                failure = TransportFailure("read timeout")
                failure.response = response
                calls = []
                def describe(**kwargs):
                    calls.append(kwargs)
                    if len(calls) == 1:
                        raise failure
                    return {"Stacks": [{"StackStatus": "DELETE_COMPLETE"}]}
                cf = SimpleNamespace(delete_stack=lambda **kwargs: None, describe_stacks=describe)
                session = SimpleNamespace(client=lambda *args, **kwargs: cf)
                record = {"errors": []}
                runner.cleanup_stack(session, {"stackArn": "arn:aws:cloudformation:us-east-1:123:stack/test/unique"}, record, sleep=lambda seconds: None)
                self.assertTrue(record["verified"])
                self.assertEqual(record["status"], "deleted")
                self.assertEqual(len(calls), 2)
                self.assertEqual(record["errors"][0]["code"], "TransportFailure")

    def test_failed_evidence_write_still_runs_cleanup(self):
        arn = "arn:aws:cloudformation:us-east-1:123:stack/test/unique"
        outputs = {name: "test" for name in runner.REQUIRED_OUTPUTS}
        outputs.update(Experiment="key-scope", Region="us-east-1", Expiry="9999999999")
        stack = {"StackId": arn, "StackStatus": "CREATE_COMPLETE", "Tags": [{"Key": "Project", "Value": "ReplayGuard"}, {"Key": "Experiment", "Value": "key-scope"}], "Outputs": [{"OutputKey": k, "OutputValue": v} for k, v in outputs.items()]}
        cf = SimpleNamespace(describe_stacks=lambda **kwargs: {"Stacks": [stack]}, get_template=lambda **kwargs: {"TemplateBody": build_template("key-scope")})
        session = SimpleNamespace(client=lambda *args, **kwargs: cf)
        def cleaned(session, target, record):
            record.update(status="deleted", verified=True)
        with tempfile.TemporaryDirectory() as folder, patch("boto3.Session", return_value=session), patch.object(runner, "Collector", return_value=SimpleNamespace(calls=0)), patch.object(runner, "collect_run", side_effect=OSError("disk full")), patch.object(runner, "write_evidence", side_effect=OSError("disk full")), patch.object(runner, "cleanup_stack", side_effect=cleaned) as cleanup, patch.object(sys, "argv", ["run_key_case.py", "--case", str(ROOT / "cases/aws-key-scope.json"), "--output", str(Path(folder) / "result.json")]), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(runner.main(), 2)
            cleanup.assert_called_once()
            self.assertEqual(cleanup.call_args.args[1]["stackArn"], arn)

    def test_clean_archive_verifies_offline_and_reexport_is_deterministic(self):
        fixture = executed_fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "fixture.json"
            evidence.write_text(json.dumps(fixture))
            one, two = root / "one.zip", root / "two.zip"
            exporter.export(ROOT / "cases/aws-key-scope.json", evidence, one, ROOT)
            exporter.export(ROOT / "cases/aws-key-scope.json", evidence, two, ROOT)
            self.assertEqual(one.read_bytes(), two.read_bytes())
            extracted = root / "extracted"
            with zipfile.ZipFile(one) as archive:
                archive.extractall(extracted)
            for line in (extracted / "SHA256SUMS").read_text().splitlines():
                expected, name = line.split("  ", 1)
                self.assertEqual(hashlib.sha256((extracted / name).read_bytes()).hexdigest(), expected)
            result = subprocess.run([sys.executable, "-I", "-S", str(extracted / "scripts/verify_key_case.py"), str(extracted / "evidence.json"), "--case", str(extracted / "case.json")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with self.assertRaises(ValueError):
                exporter.export(ROOT / "cases/aws-key-scope.json", evidence, one, ROOT)

    def test_template_selector_preserves_baseline_and_bounds(self):
        baseline = build_template()
        self.assertEqual(baseline, json.loads((ROOT / "infra/template.json").read_text()))
        versioned = build_template("key-scope")
        self.assertEqual(versioned["Outputs"]["Experiment"]["Value"], "key-scope")
        self.assertEqual(versioned["Resources"]["WorkerQueueMapping"]["Properties"]["ScalingConfig"], {"MaximumConcurrency": 2})
        self.assertEqual(versioned["Resources"]["WorkerFunction"]["Properties"]["Code"]["ZipFile"], (ROOT / "src/key_worker.py").read_text())


if __name__ == "__main__":
    unittest.main()
