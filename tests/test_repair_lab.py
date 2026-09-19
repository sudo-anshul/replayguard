"""Business-effect and bounded-execution checks for the repair adapter runner."""
import copy
import json
import os
from pathlib import Path
import py_compile
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repair_lab.plans import PlanError, canonical, default_plan, load_plan, validate_plan


class RepairRunnerTests(unittest.TestCase):
    def run_cli(self, *args, source=None, plan=None, siblings=None):
        with tempfile.TemporaryDirectory(prefix="repair-tests-") as temporary:
            folder = Path(temporary)
            command = [sys.executable, "-I", "-S", str(ROOT / "scripts/test_repair.py")]
            if source is not None:
                app = folder / "app"
                app.mkdir()
                (app / "adapter.py").write_text(source, encoding="utf-8")
                for name, data in (siblings or {}).items():
                    target = app / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(data, encoding="utf-8")
                command += ["--adapter", str(app / "adapter.py")]
            if plan is not None:
                plan_path = folder / "plan.json"
                plan_path.write_text(json.dumps(plan), encoding="utf-8")
                command += ["--case-file", str(plan_path)]
            output = folder / "report.json"
            completed = subprocess.run(command + list(args) + ["--output", str(output)], cwd=ROOT, capture_output=True, text=True, timeout=15)
            self.assertTrue(output.exists(), completed.stderr)
            return completed.returncode, json.loads(output.read_text())

    def test_reference_matrix_receipts_not_only_labels(self):
        code, report = self.run_cli()
        self.assertEqual(code, 3)
        self.assertEqual(report["summary"]["counts"], {"pass": 12, "violation": 6, "incomplete": 3, "unresolved": 3})
        results = {(r["candidateId"], r["caseId"]): r for r in report["results"]}
        for case in ("clean-orders", "crash-retry", "different-message", "two-orders-same-sku", "interleaved-retries", "payload-conflict"):
            self.assertEqual(results["business-key", case]["status"], "pass")
        unsafe = results["no-key", "crash-retry"]
        self.assertEqual(len(unsafe["receipts"]), 2)
        self.assertEqual({r["order"]["orderId"] for r in unsafe["receipts"]}, {"ORDER-A"})
        overbroad = results["overbroad-key", "two-orders-same-sku"]
        self.assertEqual(len(overbroad["receipts"]), 1)
        self.assertEqual(overbroad["deliveries"][1]["outcome"], "conflict")
        self.assertTrue(report["guard"]["passed"])

    def test_business_key_preserves_two_orders_and_conflict_payload(self):
        code, report = self.run_cli("--candidate", "business-key", "--case", "two-orders-same-sku", "--case", "payload-conflict")
        self.assertEqual(code, 0)
        two, conflict = report["results"]
        self.assertEqual({r["order"]["orderId"] for r in two["receipts"]}, {"ORDER-A", "ORDER-B"})
        self.assertEqual(conflict["receipts"][0]["order"]["quantity"], 1)
        self.assertEqual(conflict["deliveries"][1]["acceptedReceiptIds"], [])
        self.assertEqual(conflict["deliveries"][1]["outcome"], "conflict")

    def test_fulfillment_return_mutation_does_not_change_observer(self):
        source = 'def build(effects):\n def handle(d):\n  r=effects.fulfill(d["order"],key=d["order"]["orderId"])\n  r["order"]["quantity"]=999\n  return r\n return handle\n'
        code, report = self.run_cli("--case", "clean-orders", source=source)
        self.assertEqual(code, 0)
        self.assertEqual(report["results"][0]["receipts"][0]["order"]["quantity"], 1)
        self.assertEqual(report["results"][0]["deliveries"][0]["returned"]["order"]["quantity"], 999)

    def test_noop_cannot_pass_even_with_fabricated_return(self):
        code, report = self.run_cli("--case", "clean-orders", source='def build(effects):\n return lambda d: {"status":"pass","receiptId":"pretend"}\n')
        self.assertEqual(code, 1)
        self.assertEqual(report["results"][0]["receipts"], [])

    def test_public_delivery_does_not_leak_faults_or_expectations(self):
        source = 'def build(effects):\n def handle(d):\n  assert set(d)=={"deliveryId","messageId","receiveCount","order"}\n  return effects.fulfill(d["order"],key=d["order"]["orderId"])\n return handle\n'
        code, report = self.run_cli("--case", "crash-retry", source=source)
        self.assertEqual(code, 0, report)
        first, second = report["results"][0]["deliveries"]
        self.assertEqual(first["outcome"], "crashed")
        self.assertTrue(first["faultInjected"])
        self.assertEqual(second["reusedReceiptIds"], first["acceptedReceiptIds"])

    def test_faked_crash_cannot_prove_injection(self):
        source = 'def build(effects):\n def handle(d):\n  if d["receiveCount"]==1: raise effects.CrashAfterCommit("fake")\n  return effects.fulfill(d["order"],key=d["order"]["orderId"])\n return handle\n'
        code, report = self.run_cli("--case", "crash-retry", source=source)
        self.assertEqual(code, 2)
        self.assertFalse(report["results"][0]["deliveries"][0]["faultInjected"])
        self.assertEqual(len(report["results"][0]["receipts"]), 1)

    def test_reused_receipt_does_not_fire_after_new_commit_fault(self):
        plan = default_plan()
        case = copy.deepcopy(plan["cases"][1])
        case["deliveries"][0]["fault"] = "none"
        case["deliveries"][0]["expect"] = "complete"
        case["deliveries"][1]["fault"] = "after-commit"
        case["deliveries"][1]["expect"] = "crash"
        plan["cases"] = [case]
        code, report = self.run_cli("--candidate", "business-key", plan=plan)
        self.assertEqual(code, 2)
        second = report["results"][0]["deliveries"][1]
        self.assertFalse(second["faultInjected"])
        self.assertEqual(second["outcome"], "completed")

    def test_missing_observation_and_unsupported_no_import(self):
        source = 'raise AssertionError("must not import")\n'
        code, report = self.run_cli("--case", "unsupported-effect", source=source)
        self.assertEqual(code, 3)
        self.assertEqual(report["results"][0]["errors"], [])
        self.assertFalse(report["results"][0]["execution"]["imported"])
        code, report = self.run_cli("--candidate", "business-key", "--case", "missing-snapshot")
        self.assertEqual(code, 2)
        self.assertIsNone(report["results"][0]["receipts"])

    def test_import_failure_does_not_infer_missing_receipts(self):
        code, report = self.run_cli("--case", "clean-orders", source='raise ValueError("broken import")\n')
        self.assertEqual(code, 2)
        self.assertIsNone(report["results"][0]["receipts"])
        self.assertEqual(report["results"][0]["errors"][0]["phase"], "import")

    def test_caught_blocked_operation_still_unresolved(self):
        source = 'def build(effects):\n def handle(d):\n  try: __import__("subprocess")\n  except PermissionError: pass\n  return effects.fulfill(d["order"],key=d["order"]["orderId"])\n return handle\n'
        code, report = self.run_cli("--case", "clean-orders", source=source)
        self.assertEqual(code, 3)
        self.assertEqual(report["results"][0]["blockedOperationCount"], 2)
        self.assertEqual(len(report["results"][0]["receipts"]), 2)

    def test_effect_call_limit_bounds_receipts(self):
        source = 'def build(effects):\n def handle(d):\n  for _ in range(100000): effects.fulfill(d["order"])\n return handle\n'
        code, report = self.run_cli("--case", "clean-orders", source=source)
        self.assertEqual(code, 1)
        result = report["results"][0]
        self.assertEqual(len(result["receipts"]), 16)
        self.assertTrue(all(d["error"]["type"] == "EffectLimitExceeded" for d in result["deliveries"]))
        self.assertLessEqual(len(result["events"]), 128)

    def test_timeout_after_correct_effect_is_incomplete(self):
        source = 'def build(effects):\n def handle(d):\n  effects.fulfill(d["order"],key=d["order"]["orderId"])\n  while True: pass\n return handle\n'
        plan = default_plan()
        plan["cases"] = [copy.deepcopy(plan["cases"][0])]
        plan["cases"][0]["deliveries"] = plan["cases"][0]["deliveries"][:1]
        plan["cases"][0]["expectedOrders"] = plan["cases"][0]["expectedOrders"][:1]
        code, report = self.run_cli(source=source, plan=plan)
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["deliveries"][0]["outcome"], "timeout")
        self.assertEqual(len(report["results"][0]["receipts"]), 1)

    def test_fresh_sibling_source_loaded_and_fingerprinted(self):
        source = 'import importlib.util\nfrom pathlib import Path\ns=importlib.util.spec_from_file_location("fixture_worker",Path(__file__).with_name("worker.py"))\nw=importlib.util.module_from_spec(s)\ns.loader.exec_module(w)\ndef build(effects):\n return lambda d: w.work(effects,d)\n'
        worker = 'def work(e,d):\n return e.fulfill(d["order"],key=d["order"]["orderId"])\n'
        code, report = self.run_cli("--case", "clean-orders", source=source, siblings={"worker.py": worker, "__pycache__/worker.py": 'raise ValueError("bad cache")'})
        self.assertEqual(code, 0)
        self.assertEqual(set(report["candidates"][0]["sourceSha256"]), {"adapter.py", "worker.py"})

    def test_preexisting_stale_bytecode_cannot_replace_captured_source(self):
        with tempfile.TemporaryDirectory(prefix="repair-bytecode-") as temporary:
            app = Path(temporary) / "app"
            app.mkdir()
            adapter = app / "adapter.py"
            adapter.write_text('import importlib.util\nfrom pathlib import Path\ns=importlib.util.spec_from_file_location("fixture_worker",Path(__file__).with_name("worker.py"))\nw=importlib.util.module_from_spec(s)\ns.loader.exec_module(w)\ndef build(e):\n return lambda d:e.fulfill(d["order"],key=w.key(d))\n')
            worker = app / "worker.py"
            old = 'def key(d): return d["order"]["sku"]    \n'
            new = 'def key(d): return d["order"]["orderId"]\n'
            self.assertEqual(len(old), len(new))
            worker.write_text(old)
            metadata = worker.stat()
            py_compile.compile(str(worker), doraise=True)
            worker.write_text(new)
            os.utime(worker, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            report_path = Path(temporary) / "report.json"
            completed = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "scripts/test_repair.py"), "--adapter", str(adapter), "--case", "two-orders-same-sku", "--output", str(report_path)], capture_output=True, text=True, timeout=10)
            report = json.loads(report_path.read_text())
            self.assertEqual(completed.returncode, 0, report)
            self.assertEqual(len(report["results"][0]["receipts"]), 2)

    def test_mutating_copied_source_invalidates_source_stability(self):
        source = 'from pathlib import Path\ndef build(e):\n Path(__file__).write_text("# changed after capture")\n return lambda d:e.fulfill(d["order"],key=d["order"]["orderId"])\n'
        code, report = self.run_cli("--case", "clean-orders", source=source)
        self.assertEqual(code, 2)
        self.assertFalse(report["results"][0]["execution"]["sourceUnchanged"])
        self.assertEqual(len(report["results"][0]["receipts"]), 2)

    def test_business_key_formula_is_adapter_owned(self):
        source = 'def build(e):\n return lambda d:e.fulfill(d["order"],key="dispatch/v2/"+d["order"]["orderId"])\n'
        code, report = self.run_cli("--case", "crash-retry", "--case", "two-orders-same-sku", source=source)
        self.assertEqual(code, 0, report)

    def test_attributes_are_part_of_payload_conflict(self):
        plan = default_plan()
        case = copy.deepcopy(plan["cases"][5])
        case["expectedOrders"][0]["order"]["attributes"] = {"zone": "east"}
        case["deliveries"][0]["order"]["attributes"] = {"zone": "east"}
        case["deliveries"][1]["order"]["quantity"] = 1
        case["deliveries"][1]["order"]["attributes"] = {"zone": "west"}
        plan["cases"] = [case]
        code, report = self.run_cli("--candidate", "business-key", plan=plan)
        self.assertEqual(code, 0, report)
        self.assertEqual(report["results"][0]["receipts"][0]["order"]["attributes"], {"zone": "east"})

    def test_ordinary_return_does_not_prove_payload_rejection(self):
        source = 'def build(effects):\n def handle(d):\n  try: return effects.fulfill(d["order"],key=d["order"]["orderId"])\n  except effects.Conflict: return {"rejected":True}\n return handle\n'
        code, report = self.run_cli("--case", "payload-conflict", source=source)
        self.assertEqual(code, 1)
        self.assertEqual(len(report["results"][0]["receipts"]), 1)
        self.assertEqual(report["results"][0]["deliveries"][1]["outcome"], "completed")

    def test_caught_out_of_delivery_call_remains_incomplete(self):
        source = 'def build(effects):\n try: effects.fulfill({"orderId":"A","sku":"B","quantity":1})\n except RuntimeError: pass\n return lambda d: effects.fulfill(d["order"],key=d["order"]["orderId"])\n'
        code, report = self.run_cli("--case", "clean-orders", source=source)
        self.assertEqual(code, 2)
        self.assertEqual(report["results"][0]["errors"][0]["phase"], "protocol")

    def test_unknown_case_preflight_is_incomplete_report(self):
        code, report = self.run_cli("--case", "does-not-exist")
        self.assertEqual(code, 2)
        self.assertEqual(report["results"], [])
        self.assertEqual(report["errors"][0]["phase"], "preflight")


class PlanValidationTests(unittest.TestCase):
    def test_json_numeric_equality_and_boolean_distinction(self):
        self.assertEqual(canonical({"number": 1}), canonical({"number": 1.0}))
        self.assertEqual(canonical({"number": 0}), canonical({"number": -0.0}))
        self.assertNotEqual(canonical({"number": True}), canonical({"number": 1}))
        self.assertNotEqual(canonical({"number": 1.5}), canonical({"number": 1}))

    def test_unsafe_and_nonfinite_attributes_are_rejected(self):
        for value in (9007199254740992, -9007199254740992, 9007199254740992.0, float("inf"), float("nan")):
            plan = default_plan()
            plan["cases"][0]["expectedOrders"][0]["order"]["attributes"] = {"number": value}
            with self.assertRaises(PlanError):
                validate_plan(plan)
    def test_first_public_draft_aliases_normalize_generically(self):
        plan = default_plan()
        for case in plan["cases"]:
            case["effectModel"] = "atomic-receipt" if case["effectModel"] == "receiver-owned-receipt" else case["effectModel"]
            case["observation"] = "complete" if case["observation"] == "independent-ledger" else "withheld"
            for delivery in case["deliveries"]:
                delivery["id"] = delivery.pop("deliveryId")
                if delivery["fault"] == "after-commit":
                    delivery["fault"] = "after-commit-before-response"
        actual = validate_plan(plan)
        self.assertEqual(actual["cases"][1], default_plan()["cases"][1])

    def test_rejects_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "plan.json"
            path.write_text('{"schemaVersion":2,"schemaVersion":2,"kind":"replayguard-repair-plan","cases":[]}')
            with self.assertRaises(PlanError):
                load_plan(path)

    def test_delivery_and_business_order_bounds(self):
        plan = default_plan()
        plan["cases"][0]["deliveries"] *= 5
        with self.assertRaises(PlanError):
            validate_plan(plan)
        plan = default_plan()
        plan["cases"][0]["expectedOrders"].append(plan["cases"][0]["expectedOrders"][0])
        with self.assertRaises(PlanError):
            validate_plan(plan)

    def test_rejects_boolean_quantities_and_ambiguous_alias(self):
        plan = default_plan()
        plan["cases"][0]["deliveries"][0]["order"]["quantity"] = True
        with self.assertRaises(PlanError):
            validate_plan(plan)
        plan = default_plan()
        plan["cases"][0]["deliveries"][0]["id"] = "another-id"
        with self.assertRaises(PlanError):
            validate_plan(plan)


if __name__ == "__main__":
    unittest.main()
