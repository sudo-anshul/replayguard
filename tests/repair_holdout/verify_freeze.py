"""Verify the independent fixture/plan freeze without importing any candidate."""

import hashlib
import json
from pathlib import Path


def verify_freeze(repo_root: Path) -> dict:
    manifest_path = repo_root / "tests/repair_holdout/freeze.json"
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes)
    checked = []
    for entry in manifest["files"]:
        path = repo_root / entry["path"]
        data = path.read_bytes()
        actual = hashlib.sha256(data).hexdigest()
        checked.append({"path": entry["path"], "sha256": actual, "matches": actual == entry["sha256"]})
    return {
        "freezeManifestSha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "frozenAt": manifest["frozenAt"],
        "intact": all(entry["matches"] for entry in checked),
        "files": checked,
    }


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[2]
    result = verify_freeze(root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["intact"] else 1)
