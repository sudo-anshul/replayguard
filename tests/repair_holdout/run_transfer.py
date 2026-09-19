"""Run the frozen independent transfer suite through the public CLI only.

Does not import or edit the evaluator. All candidates execute from fresh,
cache-free temporary copies; deliberate defects never touch the original app.
"""

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from verify_freeze import verify_freeze


EXPECTED_FREEZE_SHA256 = "f9979ca9217a40f72c521ca901e7cf902966bc0134b5626fffb386b7359ae85d"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes(directory):
    return {p.name: sha(p) for p in sorted(directory.glob("*.py"))}


def runtime_hashes(root):
    files = [root / "scripts/test_repair.py", root / "local_lab/guard.py", *sorted((root / "repair_lab").rglob("*.py"))]
    return {str(path.relative_to(root)): sha(path) for path in files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    started = datetime.now(timezone.utc)
    output = args.output_dir or root / "docs/repair-lab/transfer-results" / started.strftime("%Y%m%dT%H%M%SZ")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan_path = root / "tests/repair_holdout/dispatchdesk-plan.json"
    plan = json.loads(plan_path.read_text())
    # The first public input draft was frozen before the runner's final
    # vocabulary. These documented aliases preserve the declared semantics.
    canonical_cases = deepcopy(plan["cases"])
    for case in canonical_cases:
        if case["effectModel"] == "atomic-receipt":
            case["effectModel"] = "receiver-owned-receipt"
        if case["observation"] == "complete":
            case["observation"] = "independent-ledger"
        for delivery in case["deliveries"]:
            delivery["deliveryId"] = delivery.pop("id")
            if delivery["fault"] == "after-commit-before-response":
                delivery["fault"] = "after-commit"
    mutations = json.loads((root / "tests/repair_holdout/mutations.json").read_text())
    before_freeze = verify_freeze(root)
    if not before_freeze["intact"] or before_freeze["freezeManifestSha256"] != EXPECTED_FREEZE_SHA256:
        raise SystemExit("Independent fixture freeze changed; refusing to relabel this as held-out evidence.")
    runtime_before = runtime_hashes(root)

    checks = []
    runs = []

    def check(name, passed, observed):
        checks.append({"name": name, "status": "pass" if passed else "fail", "observed": observed})

    candidates = [{"id": "reference"}, *mutations["mutations"]]
    with tempfile.TemporaryDirectory(prefix="replayguard-dispatchdesk-transfer-") as scratch:
        for candidate in candidates:
            name = candidate["id"]
            candidate_dir = Path(scratch) / name
            shutil.copytree(root / "examples/dispatchdesk", candidate_dir,
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            if name != "reference":
                worker = candidate_dir / "worker.py"
                source = worker.read_text()
                if source.count(candidate["find"]) != 1:
                    raise SystemExit("Mutation target is ambiguous or absent: " + name)
                worker.write_text(source.replace(candidate["find"], candidate["replace"], 1))
            candidate_before = source_hashes(candidate_dir)
            report_path = output / (name + ".json")
            command = [sys.executable, "-I", "-S", str(root / "scripts/test_repair.py"),
                       "--adapter", str(candidate_dir / "adapter.py"), "--case-file", str(plan_path),
                       "--output", str(report_path)]
            completed = subprocess.run(command, cwd=root, text=True, capture_output=True, timeout=150)
            (output / (name + ".stdout.txt")).write_text(completed.stdout)
            (output / (name + ".stderr.txt")).write_text(completed.stderr)
            candidate_after = source_hashes(candidate_dir)
            run = {"id": name, "command": command, "exitCode": completed.returncode,
                   "sourceSha256Before": candidate_before, "sourceSha256After": candidate_after,
                   "report": report_path.name}
            runs.append(run)
            check(name + ":source-copy-unchanged", candidate_before == candidate_after, candidate_after)
            if not report_path.exists():
                check(name + ":report-produced", False, completed.stderr[-2000:])
                continue
            report = json.loads(report_path.read_text())
            run["reportSha256"] = sha(report_path)
            check(name + ":exit-code", completed.returncode == (0 if name == "reference" else 1), completed.returncode)
            check(name + ":canonical-plan-preserves-frozen-semantics", report["cases"] == canonical_cases,
                  {"originalPlanSha256": sha(plan_path), "canonicalCaseIds": [c["id"] for c in report["cases"]]})
            results = {r["caseId"]: r for r in report["results"]}
            check(name + ":complete-case-set", len(report["results"]) == len(plan["cases"]) and set(results) == {c["id"] for c in plan["cases"]}, sorted(results))
            check(name + ":single-candidate", len(report["candidates"]) == 1, len(report["candidates"]))
            emitted_sources = report["candidates"][0].get("sourceSha256", {})
            check(name + ":source-fingerprints-match-copy",
                  all(emitted_sources.get(path) == digest for path, digest in candidate_before.items()), emitted_sources)
            for case in plan["cases"]:
                result = results.get(case["id"])
                if result is None:
                    continue
                receipts = result["receipts"]
                counts = Counter(r["order"]["orderId"] for r in receipts) if receipts is not None else Counter()
                execution = result["execution"]
                executed = all(execution.get(k) is True for k in ("imported", "built", "sourceUnchanged", "snapshotComplete", "completedSchedule"))
                no_runtime_failure = not any(d["outcome"] in ("error", "timeout", "not-run") for d in result["deliveries"])
                check(name + ":" + case["id"] + ":executed",
                      executed and no_runtime_failure and result["blockedOperationCount"] == 0,
                      {"execution": execution, "outcomes": [d["outcome"] for d in result["deliveries"]],
                       "errors": result["errors"]})
                if name == "reference":
                    expected = {e["order"]["orderId"]: e["order"] for e in case["expectedOrders"]}
                    right_receipts = receipts is not None and counts == Counter({key: 1 for key in expected})
                    right_receipts = right_receipts and all(r["order"] == expected.get(r["order"]["orderId"]) for r in receipts)
                    check(name + ":" + case["id"] + ":one-correct-receipt-per-order",
                          result["status"] == "pass" and right_receipts,
                          {"status": result["status"], "counts": dict(counts)})
                elif case["id"] in candidate["mustRejectCases"]:
                    if name == "no-business-key":
                        material_witness = receipts is not None and any(count > 1 for count in counts.values())
                    else:
                        missing = any(counts[e["order"]["orderId"]] == 0 for e in case["expectedOrders"])
                        false_conflict = any(d["expect"] == "complete" and d["outcome"] == "conflict" for d in result["deliveries"])
                        material_witness = receipts is not None and missing and false_conflict
                    check(name + ":" + case["id"] + ":material-mutation-detected",
                          result["status"] == "violation" and material_witness,
                          {"status": result["status"], "counts": dict(counts),
                           "outcomes": [d["outcome"] for d in result["deliveries"]]})

    after_freeze = verify_freeze(root)
    check("original-freeze-unchanged", before_freeze == after_freeze and after_freeze["intact"], after_freeze)
    runtime_after = runtime_hashes(root)
    check("runtime-sources-unchanged-during-test", runtime_before == runtime_after, runtime_after)
    summary = {
        "schemaVersion": 1, "kind": "replayguard-independent-transfer-result",
        "startedAt": started.isoformat(), "completedAt": datetime.now(timezone.utc).isoformat(),
        "scope": "Independent API transfer on frozen synthetic application inputs; no human/customer validation.",
        "python": sys.version, "runner": "scripts/test_repair.py",
        "runnerSha256": sha(root / "scripts/test_repair.py"),
        "runtimeSourceSha256Before": runtime_before, "runtimeSourceSha256After": runtime_after,
        "runtimeSourceScope": "Entry script, repair_lab Python sources and imported local_lab guard; excludes standard library and interpreter.",
        "originalPlanSha256": sha(plan_path),
        "freezeBefore": before_freeze, "freezeAfter": after_freeze,
        "runs": runs, "checks": checks,
        "passed": sum(c["status"] == "pass" for c in checks),
        "failed": sum(c["status"] == "fail" for c in checks),
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"output": str(output), "passed": summary["passed"], "failed": summary["failed"]}))
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
