#!/usr/bin/env python3
"""Read-only check of actual tutorial runs; no candidate or regression execution."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", nargs="?", choices=("baseline", "broken", "repaired"))
    args = parser.parse_args()
    stages = [args.stage] if args.stage else ["baseline", "broken", "repaired"]
    preparation = json.loads((ROOT / ".recording/preparation.json").read_text())
    failures = []
    checks = []

    def check(name, value):
        checks.append({"check": name, "passed": bool(value)})
        if not value:
            failures.append(name)

    for name, expected in preparation["extractedFileSha256"].items():
        check("original-kit:" + name, sha((ROOT / name).read_bytes()) == expected)
    check("archive-identity", sha((ROOT / ".recording/source-kit.zip").read_bytes()) == preparation["sourceArchiveSha256"])
    baseline = (ROOT / ".recording/baseline-adapter.py").read_bytes()
    plans = []
    for stage in stages:
        folder = ROOT / ".recording/runs" / stage
        if not (folder / "execution.json").is_file():
            check(stage + ":executed", False)
            continue
        record = json.loads((folder / "execution.json").read_text())
        report_bytes = (ROOT / f"{stage}.json").read_bytes()
        report = json.loads(report_bytes)
        expected_exit, expected_count, expected_status = (1, 2, "violation") if stage == "broken" else (0, 1, "pass")
        expected_source = baseline.replace(b'key=order["orderId"]', b"key=None") if stage == "broken" else baseline
        check(stage + ":process-exit", record["processExitCode"] == expected_exit)
        check(stage + ":stdout-integrity", sha((folder / "stdout.txt").read_bytes()) == record["stdoutSha256"])
        check(stage + ":stderr-integrity", sha((folder / "stderr.txt").read_bytes()) == record["stderrSha256"])
        check(stage + ":report-integrity", sha(report_bytes) == record["reportSha256"] and report_bytes == (folder / "report.json").read_bytes())
        check(stage + ":source-before", (folder / "adapter.before.py").read_bytes() == expected_source and record["sourceBeforeSha256"] == sha(expected_source))
        check(stage + ":source-after", (folder / "adapter.after.py").read_bytes() == expected_source and record["sourceAfterSha256"] == sha(expected_source))
        check(stage + ":single-selected-case", len(report["cases"]) == 1 and report["cases"][0]["id"] == "crash-retry" and len(report["results"]) == 1)
        check(stage + ":reported-status", report["summary"]["status"] == expected_status and report["summary"]["exitCode"] == expected_exit)
        result = report["results"][0]
        check(stage + ":source-actually-loaded", report["candidates"][0]["sourceSha256"] == {"adapter.py": sha(expected_source)})
        receipts = result["receipts"]
        expected_order = report["cases"][0]["expectedOrders"][0]["order"]
        check(stage + ":independent-receipt-count", len(receipts) == expected_count)
        check(stage + ":receipt-payloads", all(r["order"] == expected_order for r in receipts))
        check(stage + ":distinct-accepted-receipts", len({r["receiptId"] for r in receipts}) == expected_count and len([e for e in result["events"] if e["type"] == "receipt-accepted"]) == expected_count)
        check(stage + ":committed-crash-observed", result["deliveries"][0]["outcome"] == "crashed" and result["deliveries"][0]["faultInjected"] is True)
        check(stage + ":retry-completed", result["deliveries"][1]["outcome"] == "completed" and result["deliveries"][1]["faultInjected"] is False)
        check(stage + ":complete-runtime-evidence", all(result["execution"][key] is True for key in ("imported", "built", "sourceUnchanged", "snapshotComplete", "completedSchedule")))
        check(stage + ":source-stable", record["sourceUnchangedDuringCommand"] is True)
        plans.append(report["cases"])
        print(f"{stage}: actual exit {record['processExitCode']}; {len(receipts)} receipts; {report['summary']['status']}")
    if len(stages) == 3:
        check("identical-inputs-and-faults-across-three-runs", len(plans) == 3 and plans[0] == plans[1] == plans[2])
        check("final-adapter-restored", (ROOT / "candidate/adapter.py").read_bytes() == baseline)
    print(json.dumps({"status": "passed" if not failures else "incomplete-or-failed", "passed": len(checks) - len(failures), "total": len(checks), "failures": failures}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
