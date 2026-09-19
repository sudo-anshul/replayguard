#!/usr/bin/env python3
"""Export the dependency-free repair lab without historical/private artifacts."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
KIND = "portable-repair-lab"
FIXED_TIME = (2026, 9, 19, 0, 0, 0)
REQUIRED = (
    "scripts/test_repair.py",
    "scripts/export_repair.py",
    "local_lab/__init__.py",
    "local_lab/guard.py",
    "repair_lab/__init__.py",
    "repair_lab/engine.py",
    "repair_lab/plans.py",
    "repair_lab/adapters/__init__.py",
    "repair_lab/adapters/business_key.py",
    "repair_lab/adapters/no_key.py",
    "repair_lab/adapters/overbroad_key.py",
    "examples/dispatchdesk/__init__.py",
    "examples/dispatchdesk/worker.py",
    "examples/dispatchdesk/adapter.py",
    "examples/dispatchdesk/README.md",
    "docs/repair-lab/adapter.md",
    "docs/repair-lab/schema.md",
    "LICENSE",
)
PROTECTED_ARCHIVES = frozenset({"regression-case.zip", "replayguard-local-regression.zip"})


def checked_bytes(root, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe package path: {name}")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Package source must not be symlinked: {name}")
    if not current.is_file():
        raise ValueError(f"Missing required package source: {name}")
    return current.read_bytes()


def assemble(root=ROOT):
    root = Path(root).resolve()
    sources = set(REQUIRED)
    sources.update(path.relative_to(root).as_posix() for path in (root / "repair_lab").rglob("*.py"))
    files = {name: checked_bytes(root, name) for name in sorted(sources)}

    # The export can recreate itself from a clean extraction. Repository-only
    # runbook and independent test-plan paths are mapped to useful public names.
    runbook = "docs/repair-lab/runbook.md"
    plan = "tests/repair_holdout/dispatchdesk-plan.json"
    if (root / "PACKAGE.json").is_file():
        metadata = json.loads(checked_bytes(root, "PACKAGE.json"))
        if metadata.get("kind") != KIND:
            raise ValueError("Unrecognized extracted package")
        runbook = "README.md"
        plan = "examples/dispatchdesk/cases.json"
    files["README.md"] = checked_bytes(root, runbook)
    files["examples/dispatchdesk/cases.json"] = checked_bytes(root, plan)

    hashes = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}
    files["PACKAGE.json"] = (json.dumps({
        "schemaVersion": 1,
        "kind": KIND,
        "pythonMinimum": "3.11",
        "platforms": ["macOS", "Linux/POSIX"],
        "requiresNetwork": False,
        "requiresAwsCredentials": False,
        "requiresThirdPartyPackages": False,
        "containsHistoricalAwsEvidence": False,
        "containsStoredPassOracle": False,
        "trustedCodeOnly": True,
        "commands": {
            "passingCase": "python3 -I -S scripts/test_repair.py --candidate business-key --case crash-retry --output repaired.json",
            "keyScopeCase": "python3 -I -S scripts/test_repair.py --adapter candidate/adapter.py --case interleaved-retries --output before.json",
            "failingControl": "python3 -I -S scripts/test_repair.py --candidate no-key --case crash-retry --output duplicate.json",
            "allComparisons": "python3 -I -S scripts/test_repair.py --output repair-results.json",
            "independentExample": "python3 -I -S scripts/test_repair.py --adapter examples/dispatchdesk/adapter.py --case-file examples/dispatchdesk/cases.json --output dispatchdesk-results.json",
            "reexport": "python3 -I -S scripts/export_repair.py --output recreated.zip",
        },
        "exitCodes": {"0": "passed", "1": "violation", "2": "incomplete", "3": "unresolved"},
        "comparisonExitNote": "The complete comparison deliberately includes negative, incomplete and unresolved controls; it is not expected to exit 0.",
        "sourceSha256": hashes,
        "hashBoundary": "Hashes identify package bytes; they do not authenticate execution or AWS origin.",
    }, indent=2, sort_keys=True) + "\n").encode()
    files["SHA256SUMS"] = "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())
    ).encode()
    return files


def export(output, root=ROOT):
    root = Path(root).resolve()
    output = Path(output).absolute()
    if output.name in PROTECTED_ARCHIVES:
        raise ValueError("Refusing to overwrite a historical regression archive")
    if output.resolve().is_relative_to(root / "evidence"):
        raise ValueError("Refusing to write an archive into preserved evidence")
    files = assemble(root)
    protected = {root / name for name in files}
    protected.update({root / "docs/repair-lab/runbook.md", root / "tests/repair_holdout/dispatchdesk-plan.json"})
    if output.resolve() in protected or output.is_symlink():
        raise ValueError("Output must not replace package source or a symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                info = zipfile.ZipInfo(name, date_time=FIXED_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = 0o644 << 16
                archive.writestr(info, data)
        temporary.replace(output)
        return {"path": str(output), "files": len(files), "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "web/replayguard-repair-lab.zip")
    args = parser.parse_args()
    try:
        result = export(args.output)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    print(json.dumps({**result, "kind": KIND, "newAwsEvidence": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
