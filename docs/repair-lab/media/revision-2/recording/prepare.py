#!/usr/bin/env python3
"""Prepare a fresh disposable tutorial from this repository's public kit.

This extracts source and recording helpers only. It runs no regression case.
"""
import datetime as dt
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import zipfile

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
TUTORIAL = HERE / "tutorial"
ARCHIVE = REPO / "web/replayguard-repair-lab.zip"
EXPECTED = "e01bdcaef59a813f56c96a4ba9e10c25175d41dd33c56d7e9b29b5b29d9d2555"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if TUTORIAL.exists():
        raise SystemExit("The tutorial folder already exists. Preserve its evidence before preparing a separate take.")
    if sha(ARCHIVE) != EXPECTED:
        raise SystemExit("The public kit does not match this recording's pinned archive.")
    TUTORIAL.mkdir()
    with zipfile.ZipFile(ARCHIVE) as archive:
        for entry in archive.infolist():
            name = PurePosixPath(entry.filename)
            if name.is_absolute() or ".." in name.parts or entry.is_dir() or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                raise ValueError("Unsupported archive entry")
            destination = TUTORIAL.joinpath(*name.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(entry))
    for line in (TUTORIAL / "SHA256SUMS").read_text().splitlines():
        expected, name = line.split("  ", 1)
        if sha(TUTORIAL / name) != expected:
            raise ValueError("Archive checksum mismatch: " + name)
    original_files = {str(path.relative_to(TUTORIAL)): sha(path) for path in sorted(TUTORIAL.rglob("*")) if path.is_file()}
    (TUTORIAL / "candidate").mkdir()
    (TUTORIAL / ".recording").mkdir()
    shutil.copyfile(HERE / "baseline-adapter.py", TUTORIAL / "candidate/adapter.py")
    shutil.copyfile(HERE / "baseline-adapter.py", TUTORIAL / ".recording/baseline-adapter.py")
    shutil.copyfile(ARCHIVE, TUTORIAL / ".recording/source-kit.zip")
    for name in ("record_run.py", "validate_demo.py"):
        shutil.copyfile(HERE / name, TUTORIAL / name)
    preparation = {"kind": "tutorial-preparation", "preparedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                   "executionPerformed": False, "sourceArchive": "web/replayguard-repair-lab.zip",
                   "sourceArchiveSha256": EXPECTED, "extractedFileSha256": original_files,
                   "initialCandidateSha256": sha(TUTORIAL / "candidate/adapter.py")}
    (TUTORIAL / ".recording/preparation.json").write_text(json.dumps(preparation, indent=2) + "\n")
    print("Prepared a fresh tutorial. No regression case was executed.")
    print("Start the local viewer: python3 docs/repair-lab/media/revision-2/recording/tutorial-viewer/server.py")


if __name__ == "__main__":
    main()
