#!/usr/bin/env python3
"""Generate real local edge reports and check browser-contract parity.

These are explicit integration fixtures, not new held-out cases. Report bytes
come directly from the native runner and are never relabeled by this test.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from repair_lab.plans import default_plan

SCENARIOS = {
    "wrong-payload": ("clean-orders", "violation", 2, 'def build(e):\n def handle(d):\n  order=dict(d["order"],quantity=999)\n  return e.fulfill(order,key=order["orderId"])\n return handle\n'),
    "repeated-reuse": ("clean-orders", "pass", 2, 'def build(e):\n def handle(d):\n  for _ in range(3): r=e.fulfill(d["order"],key=d["order"]["orderId"])\n  return r\n return handle\n'),
    "manual-crash-on-conflict": ("payload-conflict", "incomplete", 1, 'def build(e):\n seen=set()\n def handle(d):\n  oid=d["order"]["orderId"]\n  if oid in seen: raise e.CrashAfterCommit("manual, no harness injection")\n  seen.add(oid)\n  return e.fulfill(d["order"],key=oid)\n return handle\n'),
    "call-exhaustion": ("clean-orders", "violation", 16, 'def build(e):\n def handle(d):\n  for _ in range(10000): e.fulfill(d["order"])\n return handle\n'),
    "timeout": ("clean-orders", "incomplete", 1, 'def build(e):\n def handle(d):\n  e.fulfill(d["order"],key=d["order"]["orderId"])\n  while True: pass\n return handle\n'),
    "caught-protocol-error": ("clean-orders", "incomplete", 2, 'def build(e):\n try:e.fulfill({"orderId":"A","sku":"B","quantity":1})\n except RuntimeError:pass\n return lambda d:e.fulfill(d["order"],key=d["order"]["orderId"])\n'),
    "wide-values-empty-description": ("clean-orders", "pass", 1, 'def build(e):\n return lambda d:e.fulfill(d["order"],key=d["order"]["orderId"])\n'),
    "numeric-equivalence": ("clean-orders", "pass", 1, 'def build(e):\n def handle(d):\n  order=dict(d["order"],attributes={"one":1.0,"zero":-0.0})\n  return e.fulfill(order,key=order["orderId"])\n return handle\n'),
    "numeric-boolean-distinction": ("clean-orders", "violation", 1, 'def build(e):\n def handle(d):\n  order=dict(d["order"],attributes={"one":True,"zero":0})\n  return e.fulfill(order,key=order["orderId"])\n return handle\n'),
}
EXIT_CODES = {"pass": 0, "violation": 1, "incomplete": 2, "unresolved": 3}


def fingerprint():
    paths = [ROOT / "scripts/test_repair.py", ROOT / "local_lab/guard.py", ROOT / "web/repair-contract.js", Path(__file__)]
    paths += sorted((ROOT / "repair_lab").rglob("*.py"))
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=ROOT / "docs/repair-lab/validation/native-parity")
    parser.add_argument("--node", default=shutil.which("node"))
    args = parser.parse_args()
    if not args.node:
        parser.error("Node.js is required to verify the browser contract")
    output = args.output_directory.resolve()
    output.mkdir(parents=True, exist_ok=True)
    before = fingerprint()
    checks = []
    reports = []
    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    for name, (case_id, expected_status, receipt_count, source) in SCENARIOS.items():
        folder = output / name
        folder.mkdir(exist_ok=True)
        adapter = folder / "adapter.py"
        adapter.write_text(source)
        plan = default_plan()
        plan["cases"] = [copy.deepcopy(c) for c in plan["cases"] if c["id"] == case_id]
        case = plan["cases"][0]
        if name in ("timeout", "wide-values-empty-description", "numeric-equivalence", "numeric-boolean-distinction"):
            case["deliveries"] = case["deliveries"][:1]
            case["expectedOrders"] = case["expectedOrders"][:1]
        if name == "wide-values-empty-description":
            case["description"] = ""
            case["deliveries"][0]["receiveCount"] = 1000000
            case["deliveries"][0]["order"]["quantity"] = 1000000
            case["expectedOrders"][0]["order"]["quantity"] = 1000000
        if name.startswith("numeric-"):
            case["deliveries"][0]["order"]["attributes"] = {"one": 1, "zero": 0}
            case["expectedOrders"][0]["order"]["attributes"] = {"one": 1, "zero": 0}
        plan_path = folder / "plan.json"
        plan_path.write_text(json.dumps(plan, indent=2) + "\n")
        report_path = folder / "report.json"
        completed = subprocess.run([sys.executable, "-I", "-S", str(ROOT / "scripts/test_repair.py"), "--adapter", str(adapter), "--case-file", str(plan_path), "--output", str(report_path)], capture_output=True, text=True, timeout=12)
        raw = report_path.read_bytes()
        report = json.loads(raw)
        result = report["results"][0]
        check(name + ":exit", completed.returncode == EXIT_CODES[expected_status], {"expected": EXIT_CODES[expected_status], "observed": completed.returncode})
        check(name + ":native-status", result["status"] == expected_status, {"expected": expected_status, "observed": result["status"]})
        check(name + ":receipt-count", len(result["receipts"]) == receipt_count, {"expected": receipt_count, "observed": len(result["receipts"])})
        check(name + ":guard", report["guard"]["passed"] and not result["blockedOperationCount"], report["guard"]["passed"])
        check(name + ":source", report["candidates"][0]["sourceSha256"].get("adapter.py") == hashlib.sha256(adapter.read_bytes()).hexdigest() and result["execution"]["sourceUnchanged"], report["candidates"][0]["sourceSha256"])
        if name == "wrong-payload":
            check(name + ":actual-wrong-payload", all(r["order"]["quantity"] == 999 for r in result["receipts"]), "Receiver actually accepted changed quantities.")
        if name == "repeated-reuse":
            check(name + ":actual-repeated-references", all(len(d["reusedReceiptIds"]) == 2 and len(set(d["reusedReceiptIds"])) == 1 for d in result["deliveries"]), "Each delivery reused the same receipt twice.")
        if name == "manual-crash-on-conflict":
            delivery = result["deliveries"][1]
            check(name + ":no-injection", delivery["outcome"] == "crashed" and not delivery["faultInjected"] and not delivery["acceptedReceiptIds"], delivery["outcome"])
        if name == "call-exhaustion":
            check(name + ":bounded-calls", all(d["effectCalls"] == 9 and d["error"]["type"] == "EffectLimitExceeded" for d in result["deliveries"]), "Eight accepted calls per delivery; ninth denied.")
        if name == "timeout":
            check(name + ":actual-timeout", result["deliveries"][0]["outcome"] == "timeout", result["deliveries"][0]["outcome"])
        if name == "caught-protocol-error":
            check(name + ":actual-protocol-error", any(e["phase"] == "protocol" for e in result["errors"]), result["errors"])
        verifier = 'const fs=require("fs"),contract=require(process.argv[1]);const report=JSON.parse(fs.readFileSync(process.argv[2],"utf8"));const model=contract.validate(report);console.log(JSON.stringify([...model.results.values()].map(r=>r.status)));'
        browser = subprocess.run([args.node, "-e", verifier, str(ROOT / "web/repair-contract.js"), str(report_path)], capture_output=True, text=True, timeout=10)
        statuses = json.loads(browser.stdout) if browser.returncode == 0 else []
        check(name + ":viewer-parity", browser.returncode == 0 and statuses == [expected_status], {"statuses": statuses, "stderr": browser.stderr[-2000:]})
        check(name + ":untouched-report", raw == report_path.read_bytes(), "The test never changes native status fields or report bytes.")
        reports.append({"scenario": name, "caseId": case_id, "candidateId": "external-1", "expectedStatus": expected_status, "report": report_path.relative_to(output).as_posix(), "reportSha256": hashlib.sha256(raw).hexdigest()})
    after = fingerprint()
    check("runtime-and-viewer-stable", before == after, "Runtime, integration driver, and browser contract source hashes match before and after.")
    summary = {"kind": "replayguard-native-viewer-parity", "recordedAt": datetime.now(timezone.utc).isoformat(), "claim": "Repeatable explicit integration fixtures; not a new held-out transfer claim.", "passed": all(c["passed"] for c in checks), "passedChecks": sum(c["passed"] for c in checks), "totalChecks": len(checks), "reports": reports, "checks": checks, "sourceSha256Before": before, "sourceSha256After": after}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"passed": summary["passed"], "passedChecks": summary["passedChecks"], "totalChecks": summary["totalChecks"], "summary": str(output / "summary.json")}))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
