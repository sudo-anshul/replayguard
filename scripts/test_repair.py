#!/usr/bin/env python3
"""Run bounded repair adapters; writes a report even on preflight failure."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from repair_lab.engine import error_record, now, run
from repair_lab.plans import PlanError, default_plan, load_plan

BUILTINS = {
    "no-key": ("No fulfillment key", "no_key.py"),
    "business-key": ("Business order key", "business_key.py"),
    "overbroad-key": ("Overbroad SKU key", "overbroad_key.py"),
}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--candidate", action="append", choices=BUILTINS, help="reference candidate (repeatable; default all three)")
    selection.add_argument("--adapter", action="append", help="trusted external adapter.py (repeatable)")
    parser.add_argument("--case-file", help="public schema v2 plan; default built-in schedules")
    parser.add_argument("--case", action="append", help="case ID from selected plan (repeatable)")
    parser.add_argument("--output", help="write JSON to this path; default stdout")
    args = parser.parse_args(argv)
    try:
        if sys.version_info < (3, 11) or sys.platform == "win32":
            raise ValueError("Python 3.11+ on macOS/Linux is required for bounded POSIX execution")
        plan = load_plan(args.case_file) if args.case_file else default_plan()
        if args.case:
            available = {c["id"] for c in plan["cases"]}
            unknown = set(args.case) - available
            if unknown:
                raise PlanError(f"unknown case ID(s): {', '.join(sorted(unknown))}")
            plan["cases"] = [c for c in plan["cases"] if c["id"] in args.case]
        if args.adapter:
            if len(args.adapter) > 8:
                raise ValueError("at most 8 candidates are allowed")
            specs = [{"id": f"external-{i + 1}", "title": Path(path).name, "path": path} for i, path in enumerate(args.adapter)]
        else:
            chosen = list(dict.fromkeys(args.candidate or BUILTINS))
            specs = [{"id": cid, "title": BUILTINS[cid][0], "path": ROOT / "repair_lab" / "adapters" / BUILTINS[cid][1]} for cid in chosen]
        report = run(plan, specs)
    except BaseException as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        report = {"schemaVersion": 2, "kind": "replayguard-repair-report", "provenance": "local-execution", "startedAt": now(), "recordedAt": now(), "candidates": [], "cases": [], "results": [], "summary": {"status": "incomplete", "exitCode": 2, "counts": {"pass": 0, "violation": 0, "incomplete": 0, "unresolved": 0}}, "errors": [error_record("preflight", exc)], "boundaries": ["No successful complete execution is claimed."], "guard": {}}
    encoded = json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(f"{report['summary']['status']}: {len(report['results'])} results; {output}")
    else:
        print(encoded, end="")
    return report["summary"]["exitCode"]


if __name__ == "__main__":
    raise SystemExit(main())
