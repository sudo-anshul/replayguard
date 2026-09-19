#!/usr/bin/env python3
"""Validate a fresh repair archive: checksums, actual mutations, and re-export.

Uses the installed Python standard library only. No AWS or network is needed.
This development validation script is intentionally outside the portable ZIP.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import zipfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--protected-manifest", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    archive_path = args.archive.resolve()
    work = args.work_dir.resolve()
    if work.exists():
        parser.error("Use a new work directory; validation never overwrites an extraction")
    work.mkdir(parents=True)
    extracted = work / "extracted"
    extracted.mkdir()
    args.output.mkdir(parents=True, exist_ok=True)
    output = args.output.resolve()
    checks = []
    runs = []
    report = {
        "schemaVersion": 1,
        "recordedAt": datetime.now(timezone.utc).isoformat(),
        "status": "incomplete",
        "archive": str(archive_path),
        "archiveSha256": digest(archive_path),
        "python": sys.version,
        "platform": sys.platform,
        "checks": checks,
        "runs": runs,
        "newAwsEvidence": False,
        "historicalAwsEvidenceIncluded": False,
    }

    def run_case(label, options, expected_exit):
        json_output = output / f"{label}.json"
        command = [sys.executable, "-I", "-S", "scripts/test_repair.py", *options, "--output", str(json_output)]
        # Deny OS networking where the already-installed macOS mechanism exists.
        # The candidate guard remains required on every platform.
        prefix = []
        if sys.platform == "darwin" and Path("/usr/bin/sandbox-exec").is_file():
            prefix = ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"]
        result = subprocess.run(prefix + command, cwd=extracted, env={"LANG": "C.UTF-8"}, text=True, capture_output=True, timeout=90)
        (output / f"{label}.stdout.txt").write_text(result.stdout)
        (output / f"{label}.stderr.txt").write_text(result.stderr)
        item = {"label": label, "command": command, "networkDenialPrefix": prefix, "exitCode": result.returncode, "expectedExitCode": expected_exit, "report": json_output.name}
        runs.append(item)
        if result.returncode != expected_exit:
            raise AssertionError(f"{label}: expected exit {expected_exit}, got {result.returncode}: {result.stderr}")
        data = json.loads(json_output.read_text())
        assert data["kind"] == "replayguard-repair-report" and data["schemaVersion"] == 2
        assert data["provenance"] == "local-execution", "Local execution must not claim AWS provenance"
        expected_status = {0: "pass", 1: "violation", 2: "incomplete", 3: "unresolved"}[expected_exit]
        assert data["summary"]["status"] == expected_status
        assert data["summary"]["exitCode"] == expected_exit
        assert data["guard"]["passed"] is True, "Required local guard did not pass its self-test"
        assert data["results"] and all(item["blockedOperationCount"] == 0 for item in data["results"])
        assert all(item["execution"]["sourceUnchanged"] for item in data["results"])
        if "--adapter" in options:
            adapter = extracted / options[options.index("--adapter") + 1]
            expected_sources = {path.relative_to(adapter.parent).as_posix(): digest(path) for path in adapter.parent.rglob("*.py")}
            assert data["candidates"][0]["sourceSha256"] == expected_sources, "Report does not identify the executed source bytes"
        item["reportSha256"] = digest(json_output)
        return data

    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = archive.namelist()
            assert len(names) == len(set(names)), "Duplicate archive paths"
            assert sum(item.file_size for item in archive.infolist()) < 16 * 1024 * 1024, "Unexpected package size"
            for item in archive.infolist():
                relative = PurePosixPath(item.filename)
                assert not relative.is_absolute() and ".." not in relative.parts, "Unsafe archive path"
                assert (item.external_attr >> 16) & 0o170000 != 0o120000, "Symlink in archive"
                assert not item.is_dir(), "Only file entries are expected"
                path = extracted / item.filename
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(item))
        sums = dict(line.split("  ", 1)[::-1] for line in (extracted / "SHA256SUMS").read_text().splitlines())
        assert set(sums) == set(names) - {"SHA256SUMS"}, "Checksum coverage differs from archive contents"
        for name, expected in sums.items():
            assert digest(extracted / name) == expected, f"Checksum mismatch: {name}"
        metadata = json.loads((extracted / "PACKAGE.json").read_text())
        assert metadata["kind"] == "portable-repair-lab"
        assert set(metadata["sourceSha256"]) == set(names) - {"PACKAGE.json", "SHA256SUMS"}
        for name, expected in metadata["sourceSha256"].items():
            assert digest(extracted / name) == expected, f"Manifest mismatch: {name}"
        assert not any(name.startswith(("evidence/", "web/", "tests/", "docs/competitive-review/")) for name in names)
        checks.append({"name": "archive-integrity-and-scope", "status": "passed", "files": len(names)})

        candidate = extracted / "candidate/adapter.py"
        candidate.parent.mkdir()
        original = (extracted / "repair_lab/adapters/business_key.py").read_bytes()
        candidate.write_bytes(original)
        selection = ["--adapter", "candidate/adapter.py", "--case", "crash-retry"]
        run_case("01-correct", selection, 0)
        before_hash = digest(candidate)
        source = original.decode()
        key = 'key=order["orderId"]'
        assert source.count(key) == 1, "Reference key expression changed; review the intended mutation"
        candidate.write_text(source.replace(key, "key=None", 1))
        broken_hash = digest(candidate)
        try:
            run_case("02-broken-key", selection, 1)
        finally:
            candidate.write_bytes(original)
        run_case("03-restored", selection, 0)
        assert digest(candidate) == before_hash != broken_hash
        checks.append({"name": "actual-candidate-pass-fail-restoration", "status": "passed", "correctSha256": before_hash, "brokenSha256": broken_hash})

        run_case("04-dispatchdesk", ["--adapter", "examples/dispatchdesk/adapter.py", "--case-file", "examples/dispatchdesk/cases.json"], 0)
        checks.append({"name": "independent-application-plan", "status": "passed"})

        recreated = work / "recreated.zip"
        command = [sys.executable, "-I", "-S", "scripts/export_repair.py", "--output", str(recreated)]
        result = subprocess.run(command, cwd=extracted, env={"LANG": "C.UTF-8"}, text=True, capture_output=True, timeout=30)
        (output / "reexport.stdout.txt").write_text(result.stdout)
        (output / "reexport.stderr.txt").write_text(result.stderr)
        assert result.returncode == 0, result.stderr
        assert recreated.read_bytes() == archive_path.read_bytes(), "Re-export was not byte-identical"
        checks.append({"name": "deterministic-reexport", "status": "passed", "sha256": digest(recreated)})

        if args.protected_manifest:
            protected = json.loads(args.protected_manifest.read_text())["files"]
            for name, expected in protected.items():
                assert digest(args.repo / name) == expected, f"Historical artifact changed: {name}"
            checks.append({"name": "historical-artifact-preservation", "status": "passed", "files": len(protected)})
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        report["completedAt"] = datetime.now(timezone.utc).isoformat()
        (output / "package-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "checks": len(checks), "runs": len(runs), "report": str(output / "package-validation.json")}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
