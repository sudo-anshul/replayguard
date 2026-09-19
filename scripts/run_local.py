#!/usr/bin/env python3
"""Execute the existing ReplayGuard handlers locally, without dependencies or AWS.

Use: python3 -I -S scripts/run_local.py --output local-results.json
Single handler: --case crash-after-fulfillment --mode vulnerable (exits 1).
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True

from local_lab.cases import CASE_IDS, ITERATION
from local_lab.guard import LocalExecutionGuard
from local_lab.runner import run, utc_now, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASE_IDS, help="Execute one of the five frozen scenarios")
    parser.add_argument("--mode", choices=("vulnerable", "repaired"), help="Select one handler mode; with --case, the exit code is that handler's outcome")
    parser.add_argument("--output", type=Path, default=Path("local-results.json"))
    parser.add_argument("--source-dir", type=Path, default=ROOT / "src", help="Explicit handler directory for local mutation-sensitivity checks; fingerprints are recorded")
    args = parser.parse_args()
    guard = LocalExecutionGuard().install()
    try:
        if not sys.flags.isolated or not sys.flags.no_site:
            raise ValueError("Run with python3 -I -S so user paths, site packages and startup hooks are disabled")
        guard.self_test()
        report = run(ROOT, args.source_dir.resolve(), guard, args.case, args.mode)
    except Exception as error:
        report = {"schemaVersion": 1, "provenance": "local-execution", "supervisorIteration": ITERATION, "recordedAt": utc_now(), "results": [], "noNetworkGuard": guard.snapshot(), "error": {"type": type(error).__name__, "message": str(error)[:1000]}, "suite": {"status": "failed", "exitCode": 3, "expectationsMatched": False, "allHandlersSafe": False}, "command": {"kind": "preflight-failure", "exitCode": 3}}
    write_report(report, args.output)
    for result in report["results"]:
        count = "withheld" if result["ledgerSnapshot"] is None else str(len(result["ledgerSnapshot"]))
        print(f"{result['caseId']:26} {result['mode']:10} {result['observedStatus']:10} expected={result['expectedStatus']:10} receipts={count} exit={result['exitCode']}")
    print(f"Suite expectations: {report['suite']['status'].upper()}. This does not mean every handler is safe.")
    if report.get("error"):
        print(report["error"]["message"], file=sys.stderr)
    print(f"Local execution report: {args.output}")
    return report["command"]["exitCode"]


if __name__ == "__main__":
    raise SystemExit(main())
