#!/usr/bin/env python3
"""Record actual local CLI output and receipt counts for a demo; no video.

Every command executes in a new archive extraction. Displayed status/counts are
read from that command's report, not generated example terminal output.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import zipfile


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    archive_path = args.archive.resolve()
    work = args.work_dir.resolve()
    output = args.output_dir.resolve()
    if work.exists() or output.exists():
        parser.error("Use new work and output directories; recordings are never overwritten")
    work.mkdir(parents=True)
    output.mkdir(parents=True)
    extraction = work / "extracted"
    extraction.mkdir()
    transcript = ["REPLAYGUARD — RECORDED LOCAL CLI EXECUTION", f"Recorded: {now()}", "Actual subprocess output; summaries below are read from the generated JSON.", "Local simulated receipts. No AWS execution or shipment.", ""]
    manifest = {"schemaVersion": 1, "kind": "recorded-local-cli-output", "startedAt": now(), "archiveSha256": digest(archive_path), "archive": str(archive_path), "python": sys.version, "newAwsEvidence": False, "simulatedTyping": False, "commands": [], "fileOperations": [], "status": "incomplete"}
    original = None
    candidate = extraction / "candidate/adapter.py"

    def execute(label, options, expected_exit, expected_results):
        report_name = label + ".json"
        argv = [sys.executable, "-I", "-S", "scripts/test_repair.py", *options, "--output", report_name]
        wrapper = []
        if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
            wrapper = ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
        started = now()
        result = subprocess.run(wrapper + argv, cwd=extraction, env={"LANG": "C.UTF-8"}, text=True, capture_output=True, timeout=90)
        completed = now()
        (output / (label + ".stdout.txt")).write_text(result.stdout)
        (output / (label + ".stderr.txt")).write_text(result.stderr)
        source_report = extraction / report_name
        entry = {"label": label, "startedAt": started, "completedAt": completed, "argv": argv, "networkWrapper": wrapper, "cwd": str(extraction), "exitCode": result.returncode, "expectedExitCode": expected_exit, "stdout": label + ".stdout.txt", "stderr": label + ".stderr.txt", "report": report_name}
        manifest["commands"].append(entry)
        transcript.extend([f"[{started}]", "$ " + shlex.join(argv), result.stdout.rstrip(), f"Process exit: {result.returncode}"])
        if result.stderr:
            transcript.extend(["stderr:", result.stderr.rstrip()])
        assert source_report.is_file(), "CLI did not produce its report"
        (output / report_name).write_bytes(source_report.read_bytes())
        report = json.loads(source_report.read_text())
        entry["reportSha256"] = digest(source_report)
        entry["sourceSha256"] = report["candidates"][0]["sourceSha256"]
        entry["status"] = report["summary"]["status"]
        assert result.returncode == expected_exit
        assert report["kind"] == "replayguard-repair-report" and report["provenance"] == "local-execution"
        assert report["summary"]["exitCode"] == result.returncode
        assert report["guard"]["passed"] and len(report["results"]) == expected_results
        adapter = extraction / options[options.index("--adapter") + 1]
        actual_sources = {path.relative_to(adapter.parent).as_posix(): digest(path) for path in adapter.parent.rglob("*.py")}
        assert entry["sourceSha256"] == actual_sources
        transcript.append(f"Report status: {entry['status']}")
        cases = []
        for case in report["results"]:
            assert isinstance(case["receipts"], list)
            observed = Counter(receipt["order"]["orderId"] for receipt in case["receipts"])
            expected = {item["order"]["orderId"]: item["count"] for item in case["expectedOrders"]}
            rows = [{"orderId": identity, "observedReceipts": observed[identity], "expectedReceipts": expected.get(identity, 0)} for identity in sorted(set(observed) | set(expected))]
            cases.append({"caseId": case["caseId"], "status": case["status"], "orders": rows})
            transcript.append(f"  {case['caseId']}: {case['status']}")
            for row in rows:
                transcript.append(f"    {row['orderId']}: {row['observedReceipts']} receipt(s), expected {row['expectedReceipts']}")
        entry["observedCases"] = cases
        if expected_exit == 0:
            assert all(case["status"] == "pass" for case in cases)
            assert all(row["observedReceipts"] == row["expectedReceipts"] for case in cases for row in case["orders"])
        else:
            assert any(row["observedReceipts"] > row["expectedReceipts"] for case in cases for row in case["orders"])
        transcript.extend(["Captured source SHA-256:", *[f"  {name}: {value}" for name, value in sorted(actual_sources.items())], ""])

    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names))
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                assert not path.is_absolute() and ".." not in path.parts and not item.is_dir()
                assert ((item.external_attr >> 16) & 0o170000) != 0o120000
                target = extraction / item.filename
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
        sums = dict(line.split("  ", 1)[::-1] for line in (extraction / "SHA256SUMS").read_text().splitlines())
        assert set(sums) == set(names) - {"SHA256SUMS"}
        assert all(digest(extraction / name) == expected for name, expected in sums.items())
        original = (extraction / "repair_lab/adapters/business_key.py").read_bytes()
        candidate.parent.mkdir()
        candidate.write_bytes(original)
        baseline_sha = digest(candidate)
        manifest["fileOperations"].append({"recordedAt": now(), "operation": "copy reference to disposable candidate", "path": "candidate/adapter.py", "sha256": baseline_sha})
        transcript.extend(["Copied the packaged business-key reference to disposable candidate/adapter.py.", ""])
        options = ["--adapter", "candidate/adapter.py", "--case", "crash-retry"]
        execute("01-correct", options, 0, 1)
        source = original.decode()
        expression = 'key=order["orderId"]'
        assert source.count(expression) == 1
        candidate.write_text(source.replace(expression, "key=None", 1))
        manifest["fileOperations"].append({"recordedAt": now(), "operation": "deliberate key mutation in disposable candidate", "from": expression, "to": "key=None", "sha256": digest(candidate)})
        transcript.extend([f"Applied deliberate mutation to disposable candidate: {expression} -> key=None", ""])
        execute("02-broken-key", options, 1, 1)
        candidate.write_bytes(original)
        assert digest(candidate) == baseline_sha
        manifest["fileOperations"].append({"recordedAt": now(), "operation": "restore exact original candidate bytes", "sha256": digest(candidate)})
        transcript.extend(["Restored the exact packaged business-key bytes to the disposable candidate.", ""])
        execute("03-restored", options, 0, 1)
        execute("04-dispatchdesk", ["--adapter", "examples/dispatchdesk/adapter.py", "--case-file", "examples/dispatchdesk/cases.json"], 0, 5)
        manifest["status"] = "passed"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = {"type": type(error).__name__, "message": str(error)}
        transcript.append(f"Recording failed: {type(error).__name__}: {error}")
    finally:
        if original is not None and candidate.exists():
            candidate.write_bytes(original)
        manifest["completedAt"] = now()
        (output / "transcript.txt").write_text("\n".join(transcript) + "\n")
        manifest["transcriptSha256"] = digest(output / "transcript.txt")
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"status": manifest["status"], "commands": len(manifest["commands"]), "manifest": str(output / "manifest.json"), "transcript": str(output / "transcript.txt")}, indent=2))
    return 0 if manifest["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
