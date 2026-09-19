"""Run the real local CLI in isolated interpreters, including temporary mutations."""
import copy
import hashlib
import json
import os
import py_compile
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from local_lab.adapters import ConditionalCheckFailed, MemoryLedger
from local_lab.cases import load_case


class LocalExecutionTests(unittest.TestCase):
    def run_cli(self, *arguments, source=None):
        with tempfile.TemporaryDirectory(prefix="replayguard-local-test-") as directory:
            output = Path(directory) / "result.json"
            command = [sys.executable, "-I", "-S", str(ROOT / "scripts/run_local.py"), "--output", str(output), *arguments]
            if source:
                command += ["--source-dir", str(source)]
            env = {key: value for key, value in os.environ.items() if not key.startswith("AWS_") and key not in ("BOTO_CONFIG", "PYTHONPATH", "PYTHONSTARTUP")}
            process = subprocess.run(command, capture_output=True, text=True, env=env, timeout=15)
            self.assertTrue(output.exists(), process.stdout + process.stderr)
            return process, json.loads(output.read_text())

    def mutate_source(self, destination, target, transform):
        source = Path(destination) / "src"
        source.mkdir()
        for name in ("worker.py", "provider.py"):
            shutil.copyfile(ROOT / "src" / name, source / name)
        path = source / target
        original = path.read_text()
        mutated = transform(original)
        self.assertNotEqual(mutated, original, "Mutation must actually change source")
        path.write_text(mutated)
        return source

    def test_complete_suite_runs_existing_code_and_matches_frozen_expectations(self):
        process, report = self.run_cli()
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        self.assertEqual(report["provenance"], "local-execution")
        self.assertEqual(report["suite"]["totalCount"], 10)
        self.assertEqual(report["suite"]["matchedCount"], 10)
        self.assertFalse(report["suite"]["allHandlersSafe"])
        self.assertEqual(report["sourceSha256"]["src/worker.py"], hashlib.sha256((ROOT / "src/worker.py").read_bytes()).hexdigest())
        for result in report["results"]:
            self.assertEqual(result["observedStatus"], result["expectedStatus"])
        guard = report["noNetworkGuard"]
        self.assertTrue(guard["installedBeforeHandlerImport"])
        self.assertTrue(guard["passed"])
        self.assertEqual(guard["blockedOperationCount"], 4)
        self.assertEqual(guard["handlerBlockedOperationCount"], 0)
        self.assertTrue(all(item["blocked"] for item in guard["selfTests"]))
        self.assertTrue(report["runtime"]["isolated"])
        self.assertTrue(report["runtime"]["noSitePackages"])
        self.assertFalse(report["runtime"]["sdkImported"])

    def test_individual_exit_codes_are_handler_outcomes_not_expected_suite_success(self):
        for case_id, mode, exit_code in (("no-fault", "vulnerable", 0), ("crash-after-fulfillment", "vulnerable", 1), ("missing-observation", "repaired", 2), ("ambiguous-side-effect", "repaired", 3)):
            with self.subTest(case=case_id):
                process, report = self.run_cli("--case", case_id, "--mode", mode)
                self.assertEqual(process.returncode, exit_code, process.stdout + process.stderr)
                self.assertEqual(report["command"]["exitCode"], exit_code)
                self.assertEqual(report["suite"]["exitCode"], 0)
                self.assertTrue(report["results"][0]["expectationMatched"])

    def test_real_crash_then_retry_uses_same_message_and_distinct_invocations(self):
        process, report = self.run_cli("--case", "crash-after-fulfillment", "--mode", "repaired")
        self.assertEqual(process.returncode, 0)
        result = report["results"][0]
        first, second = result["deliveries"]
        self.assertEqual(first["messageId"], second["messageId"])
        self.assertEqual([first["receiveCount"], second["receiveCount"]], [1, 2])
        self.assertNotEqual(first["requestId"], second["requestId"])
        self.assertIsNotNone(first["error"])
        self.assertFalse(first["returnedNormally"])
        self.assertTrue(second["returnedNormally"])
        self.assertEqual(len(result["ledgerSnapshot"]), 1)
        self.assertEqual(result["execution"]["providerInvocations"], 2)
        self.assertEqual([invocation["returned"]["reused"] for invocation in result["providerInvocations"]], [False, True])

    def test_declared_different_messages_share_one_business_identity(self):
        process, report = self.run_cli("--case", "different-message-ids")
        self.assertEqual(process.returncode, 0)
        for result in report["results"]:
            first, second = result["deliveries"]
            self.assertNotEqual(first["messageId"], second["messageId"])
            self.assertEqual([first["receiveCount"], second["receiveCount"]], [1, 1])
            payloads = [json.loads(d["input"]["Records"][0]["body"]) for d in result["deliveries"]]
            self.assertEqual(payloads[0], payloads[1])
            self.assertTrue(all(d["returnedNormally"] for d in result["deliveries"]))
            self.assertEqual(len(result["ledgerSnapshot"]), 2 if result["mode"] == "vulnerable" else 1)

    def test_withheld_observation_never_substitutes_success_return(self):
        process, report = self.run_cli("--case", "missing-observation", "--mode", "repaired")
        self.assertEqual(process.returncode, 2)
        result = report["results"][0]
        self.assertTrue(result["execution"]["performed"])
        self.assertTrue(result["deliveries"][0]["returnedNormally"])
        self.assertTrue(result["deliveries"][0]["returned"]["receiptId"])
        self.assertIsNone(result["ledgerSnapshot"])
        self.assertEqual(result["observedStatus"], "incomplete")

    def test_unsupported_external_model_does_not_invent_execution(self):
        process, report = self.run_cli("--case", "ambiguous-side-effect", "--mode", "repaired")
        self.assertEqual(process.returncode, 3)
        result = report["results"][0]
        self.assertFalse(result["execution"]["performed"])
        self.assertFalse(result["execution"]["sourcesLoaded"])
        self.assertEqual(result["execution"]["handlerInvocations"], 0)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["deliveries"], [])
        self.assertIsNone(result["ledgerSnapshot"])

    def test_removing_repaired_key_is_killed_by_both_fixed_failure_cases(self):
        line = '            invocation_payload["idempotencyKey"] = idempotency_key(payload["runId"], payload["order"]["orderId"])'
        with tempfile.TemporaryDirectory(prefix="replayguard-key-mutation-") as directory:
            source = self.mutate_source(directory, "worker.py", lambda text: text.replace(line, "            pass  # sensitivity mutation: omit the stable key"))
            for case_id in ("crash-after-fulfillment", "different-message-ids"):
                with self.subTest(case=case_id):
                    process, report = self.run_cli("--case", case_id, "--mode", "repaired", source=source)
                    self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
                    result = report["results"][0]
                    self.assertEqual(result["observedStatus"], "violation")
                    self.assertFalse(result["expectationMatched"])
                    self.assertEqual(len(result["ledgerSnapshot"]), 2)
                    self.assertEqual(report["suite"]["status"], "failed")

    def test_stale_bytecode_cannot_replace_the_fingerprinted_source(self):
        line = '            invocation_payload["idempotencyKey"] = idempotency_key(payload["runId"], payload["order"]["orderId"])'
        with tempfile.TemporaryDirectory(prefix="replayguard-pyc-mutation-") as directory:
            source = Path(directory) / "src"
            source.mkdir()
            for name in ("worker.py", "provider.py"):
                shutil.copyfile(ROOT / "src" / name, source / name)
            path = source / "worker.py"
            original = path.read_text()
            self.assertIn(line, original)
            metadata = path.stat()
            py_compile.compile(str(path), doraise=True)
            changed = original.replace(line, "            pass".ljust(len(line)))
            self.assertEqual(len(changed.encode()), len(original.encode()))
            path.write_text(changed)
            os.utime(path, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            process, report = self.run_cli("--case", "crash-after-fulfillment", "--mode", "repaired", source=source)
            self.assertEqual(process.returncode, 1, process.stdout + process.stderr)
            self.assertEqual(report["results"][0]["observedStatus"], "violation")
            self.assertEqual(len(report["results"][0]["ledgerSnapshot"]), 2)
            self.assertEqual(report["sourceSha256"]["src/worker.py"], hashlib.sha256(changed.encode()).hexdigest())

    def test_immediately_throwing_handler_cannot_pass_no_fault_control(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-throw-mutation-") as directory:
            source = self.mutate_source(directory, "worker.py", lambda text: text + '\n\ndef handler(event, context):\n    raise RuntimeError("immediate failure mutation")\n')
            process, report = self.run_cli("--case", "no-fault", "--mode", "repaired", source=source)
            self.assertNotEqual(process.returncode, 0)
            result = report["results"][0]
            self.assertEqual(result["observedStatus"], "incomplete")
            self.assertEqual(result["ledgerSnapshot"], [])
            self.assertFalse(result["deliveries"][0]["returnedNormally"])
            self.assertFalse(result["expectationMatched"])

    def test_successful_worker_return_alone_is_not_a_fulfillment(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-return-mutation-") as directory:
            source = self.mutate_source(directory, "worker.py", lambda text: text + '\n\ndef handler(event, context):\n    return {"receiptId": "invented-return", "reused": False}\n')
            process, report = self.run_cli("--case", "no-fault", "--mode", "repaired", source=source)
            self.assertNotEqual(process.returncode, 0)
            result = report["results"][0]
            self.assertTrue(result["deliveries"][0]["returnedNormally"])
            self.assertEqual(result["ledgerSnapshot"], [])
            self.assertNotEqual(result["observedStatus"], "pass")

    def test_provider_exception_uses_function_error_transport_semantics(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-provider-mutation-") as directory:
            source = self.mutate_source(directory, "provider.py", lambda text: text + '\n\ndef handler(event, context):\n    raise ValueError("provider failed locally")\n')
            process, report = self.run_cli("--case", "no-fault", "--mode", "repaired", source=source)
            self.assertEqual(process.returncode, 2)
            result = report["results"][0]
            self.assertEqual(result["providerInvocations"][0]["functionError"], "Unhandled")
            self.assertIn("Fulfillment provider failed: ValueError", result["deliveries"][0]["error"]["message"])
            self.assertEqual(result["ledgerSnapshot"], [])

    def test_network_attempt_is_blocked_before_handler_module_finishes_importing(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-network-guard-") as directory:
            source = self.mutate_source(directory, "worker.py", lambda text: "import socket\nsocket.socket()\n" + text)
            process, report = self.run_cli("--case", "no-fault", "--mode", "repaired", source=source)
            self.assertEqual(process.returncode, 3)
            self.assertEqual(report["noNetworkGuard"]["handlerBlockedOperationCount"], 1)
            self.assertEqual(report["results"][0]["observedStatus"], "unresolved")
            self.assertFalse(report["results"][0]["execution"]["performed"])

    def test_child_process_escape_is_blocked(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-process-guard-") as directory:
            marker = Path(directory) / "must-not-exist"
            source = self.mutate_source(directory, "worker.py", lambda text: text + '\n\ndef handler(event, context):\n    os.system(' + repr("touch " + str(marker)) + ')\n')
            process, report = self.run_cli("--case", "no-fault", "--mode", "repaired", source=source)
            self.assertEqual(process.returncode, 3)
            self.assertFalse(marker.exists())
            self.assertEqual(report["noNetworkGuard"]["handlerBlockedOperationCount"], 1)

    def test_case_expectations_cannot_be_tuned_to_hide_vulnerable_violation(self):
        with tempfile.TemporaryDirectory(prefix="replayguard-case-mutation-") as directory:
            data = json.loads((ROOT / "cases/local/crash-after-fulfillment.json").read_text())
            data["expectedStatus"]["vulnerable"] = "pass"
            path = Path(directory) / "crash-after-fulfillment.json"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, "frozen"):
                load_case(path)


class MemoryLedgerTests(unittest.TestCase):
    def test_conditional_create_and_independent_snapshot_are_not_worker_returns(self):
        ledger = MemoryLedger()
        receipt = {"PK": "RUN#local#MODE#repaired", "SK": "RECEIPT#stable", "receiptId": "stable"}
        ledger.put_item(Item=receipt, ConditionExpression=ledger.CONDITION)
        with self.assertRaises(ConditionalCheckFailed):
            ledger.put_item(Item=copy.deepcopy(receipt), ConditionExpression=ledger.CONDITION)
        snapshot = ledger.independent_snapshot()
        snapshot[0]["receiptId"] = "changed-outside-ledger"
        self.assertEqual(ledger.independent_snapshot()[0]["receiptId"], "stable")
        self.assertEqual(len(ledger.independent_snapshot()), 1)

    def test_unsupported_condition_fails_instead_of_pretending_atomicity(self):
        with self.assertRaises(ValueError):
            MemoryLedger().put_item(Item={"PK": "p", "SK": "s"}, ConditionExpression="anything-goes")


if __name__ == "__main__":
    unittest.main()
