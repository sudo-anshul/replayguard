#!/usr/bin/env python3
"""Build the public viewer deterministically from ui/ without executing any worker.

Use --check in a clean checkout to verify that committed web assets match source.
Report text is embedded as a JSON string so its original UTF-8 bytes survive HTML
escaping. The manifest records byte consistency, not report execution origin.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def aws_key_scope_view(root: Path, read) -> dict:
    """Regenerate the full verdict from raw observations, never from saved status.

    Missing evidence stays missing. Test fixtures must never be copied into web/.
    The browser independently checks this report hash and its ledger counts.
    """
    view = {"schemaVersion": 1, "kind": "replayguard-aws-key-scope-web-view", "report": None,
            "archive": None, "verification": None,
            "boundary": "Offline verifier result regenerated during the site build. Byte consistency is not trusted AWS attestation."}
    report_path = root / "web/aws-key-scope-report.json"
    if not report_path.is_file():
        return view
    raw = read("web/aws-key-scope-report.json")
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("AWS key-scope report exceeds the 8 MiB viewing limit")
    verifier_path = "scripts/verify_key_case.py"
    verifier_source = read(verifier_path)
    spec = importlib.util.spec_from_file_location("replayguard_web_aws_verifier", root / verifier_path)
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    evidence = verifier.strict_json(raw)
    if evidence.get("kind") != "replayguard-aws-key-scope-report" or evidence.get("schemaVersion") != 2 or evidence.get("provenance") != "aws":
        raise ValueError("The AWS key-scope page requires its separately versioned actual AWS report")
    view.update(report={"path": "aws-key-scope-report.json", "sha256": digest(raw)},
                recordedAt=evidence.get("recordedAt"), verification=verifier.verify(evidence),
                verifier={"path": verifier_path, "sha256": digest(verifier_source)})
    archive_path = root / "web/aws-key-scope-regression.zip"
    if archive_path.is_file():
        archive = read("web/aws-key-scope-regression.zip")
        # A stale archive must not look like the reproduction of a newer report.
        try:
            with zipfile.ZipFile(io.BytesIO(archive)) as package:
                if package.getinfo("evidence.json").file_size > 8 * 1024 * 1024:
                    raise ValueError("Oversized archived evidence")
                if package.read("evidence.json") != raw:
                    raise ValueError("Archive contains a different report")
            view["archive"] = {"path": "aws-key-scope-regression.zip", "sha256": digest(archive)}
        except (ValueError, KeyError, zipfile.BadZipFile):
            view["archiveIssue"] = "The available archive does not contain these exact report bytes; download disabled."
    return view


def build(root: Path = ROOT) -> dict[str, bytes]:
    sources: dict[str, bytes] = {}

    def read(name: str) -> bytes:
        data = (root / name).read_bytes()
        sources[name] = data
        return data

    outputs: dict[str, bytes] = {}
    for name in ("repair.css", "repair-data.js", "repair-imports.js", "repair-app.js", "repair-motion.js", "shared-tokens.css", "aws-key-scope.css", "aws-key-scope-data.js", "aws-key-scope.js"):
        outputs[f"web/{name}"] = read(f"ui/{name}")
    outputs["web/mark.svg"] = read("ui/replayguard-mark.svg")
    source = read("ui/index.template.html").decode("utf-8")
    aws_view = aws_key_scope_view(root, read)
    aws_label = "Recording not yet attached · incomplete"
    if aws_view["report"]:
        state = aws_view["verification"]["experimentStatus"]
        aws_label = {"passed": "Recorded AWS evidence · experiment passed", "incomplete": "Recorded AWS evidence · incomplete", "unresolved": "Recorded AWS evidence · unresolved", "violation": "Recorded AWS evidence · violation"}.get(state, "Recorded AWS evidence · incomplete")
    source = source.replace("{{AWS_KEY_SCOPE_LABEL}}", aws_label)
    for marker, name in (("REPORT_JSON", "repair-example.json"), ("TRANSFER_JSON", "repair-transfer.json")):
        text = read("web/" + name).decode("utf-8")
        json.loads(text)  # fail before publishing malformed bundled evidence
        encoded = json.dumps(text, ensure_ascii=False).replace("<", "\\u003c")
        source = source.replace("/* " + marker + " */", encoded)
    read("web/repair-contract.js")
    for name in ("repair.css", "repair-contract.js", "repair-data.js", "repair-imports.js", "repair-app.js", "repair-motion.js"):
        data = outputs.get("web/" + name, sources.get("web/" + name))
        source = source.replace("{{" + name + "}}", "./" + name + "?v=" + digest(data)[:12])
    if "/* REPORT_JSON */" in source or "{{" in source:
        raise ValueError("An unresolved build marker remains in the public template.")
    if "127.0.0.1" in source or "localhost" in source:
        raise ValueError("A loopback preview URL must not enter the public viewer.")
    outputs["web/index.html"] = source.encode("utf-8")
    outputs["web/repair.html"] = outputs["web/index.html"]
    aws_source = read("ui/aws-key-scope.template.html").decode("utf-8")
    aws_source = aws_source.replace("/* AWS_KEY_SCOPE_VIEW */", json.dumps(aws_view, ensure_ascii=False).replace("<", "\\u003c"))
    for name in ("repair.css", "aws-key-scope.css", "aws-key-scope-data.js", "aws-key-scope.js"):
        aws_source = aws_source.replace("{{" + name + "}}", "./" + name + "?v=" + digest(outputs["web/" + name])[:12])
    if "{{" in aws_source or "/* AWS_KEY_SCOPE_VIEW */" in aws_source:
        raise ValueError("An unresolved marker remains in the AWS viewer")
    outputs["web/aws-key-scope.html"] = aws_source.encode("utf-8")
    read("scripts/build_web.py")
    manifest = {
        "schemaVersion": 1,
        "buildCommand": "python3 -I -S scripts/build_web.py",
        "scope": "Generated viewer assets and their source inputs; hashes establish byte consistency, not report origin.",
        "sources": {name: digest(data) for name, data in sorted(sources.items())},
        "assets": {name: digest(data) for name, data in sorted(outputs.items())},
    }
    outputs["web/build-manifest.json"] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check committed outputs without writing files")
    args = parser.parse_args()
    outputs = build()
    stale = []
    for name, data in outputs.items():
        target = ROOT / name
        if args.check:
            if not target.is_file() or target.read_bytes() != data:
                stale.append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
    if stale:
        print("Stale generated web assets: " + ", ".join(stale))
        print("Run python3 -I -S scripts/build_web.py and retain the resulting files.")
        return 1
    print(("Checked" if args.check else "Built") + f" {len(outputs)} deterministic public assets.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
