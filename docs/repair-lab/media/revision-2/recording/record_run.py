#!/usr/bin/env python3
"""Execute one real tutorial command and retain its unmodified evidence.

This helper never changes an adapter, a report, a receipt, or an exit status.
Run it during the screen recording, after making the relevant source edit.
"""
import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("baseline", "broken", "repaired"))
    args = parser.parse_args()
    stage = args.stage
    report_path = ROOT / f"{stage}.json"
    evidence = ROOT / ".recording" / "runs" / stage
    if report_path.exists() or evidence.exists():
        parser.error(f"{stage} already has evidence; preserve it and prepare a new take directory")
    preparation = json.loads((ROOT / ".recording/preparation.json").read_text())
    for name, expected in preparation["extractedFileSha256"].items():
        if digest((ROOT / name).read_bytes()) != expected:
            parser.error(f"Original kit file changed: {name}")
    adapter = ROOT / "candidate/adapter.py"
    source_before = adapter.read_bytes()
    baseline = (ROOT / ".recording/baseline-adapter.py").read_bytes()
    broken = baseline.replace(b'key=order["orderId"]', b"key=None")
    expected_source = broken if stage == "broken" else baseline
    if source_before != expected_source:
        parser.error(f"The actual adapter is not the intended {stage} source. Edit and save it first.")
    evidence.mkdir(parents=True)
    (evidence / "adapter.before.py").write_bytes(source_before)
    argv = [sys.executable, "-I", "-S", "scripts/test_repair.py", "--adapter", "candidate/adapter.py", "--case", "crash-retry", "--output", f"{stage}.json"]
    network_wrapper = []
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        network_wrapper = [shutil.which("sandbox-exec"), "-p", "(version 1)(allow default)(deny network*)"]
    display_command = shlex.join(["python3", *argv[1:]])
    print(display_command, flush=True)
    started = now()
    result = subprocess.run(network_wrapper + argv, cwd=ROOT, capture_output=True)
    finished = now()
    (evidence / "stdout.txt").write_bytes(result.stdout)
    (evidence / "stderr.txt").write_bytes(result.stderr)
    sys.stdout.write(result.stdout.decode(errors="replace"))
    sys.stderr.write(result.stderr.decode(errors="replace"))
    source_after = adapter.read_bytes()
    (evidence / "adapter.after.py").write_bytes(source_after)
    record = {
        "kind": "actual-local-tutorial-execution", "stage": stage,
        "startedAt": started, "completedAt": finished,
        "argv": argv, "displayCommand": display_command,
        "workingDirectory": ".", "networkWrapper": network_wrapper,
        "processExitCode": result.returncode,
        "sourceBeforeSha256": digest(source_before),
        "sourceAfterSha256": digest(source_after),
        "sourceUnchangedDuringCommand": source_before == source_after,
        "stdoutSha256": digest(result.stdout), "stderrSha256": digest(result.stderr),
        "sourceArchiveSha256": preparation["sourceArchiveSha256"],
        "newAwsExecution": False, "simulatedTyping": False,
        "report": f"{stage}.json", "reportSha256": None,
    }
    if report_path.exists():
        report_bytes = report_path.read_bytes()
        (evidence / "report.json").write_bytes(report_bytes)
        record["reportSha256"] = digest(report_bytes)
        try:
            report = json.loads(report_bytes)
            record["reportedStatus"] = report.get("summary", {}).get("status")
            observed = report.get("results", [{}])[0].get("receipts")
            record["observedReceipts"] = None if observed is None else len(observed)
            print(f"Observed receipts: {record['observedReceipts']}")
        except (ValueError, KeyError, IndexError, AttributeError) as exc:
            record["reportReadError"] = type(exc).__name__ + ": " + str(exc)
    print(f"Process exit: {result.returncode}", flush=True)
    (evidence / "execution.json").write_text(json.dumps(record, indent=2) + "\n")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
