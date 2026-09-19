#!/usr/bin/env python3
"""Create a local, explicitly allowlisted ReplayGuard source snapshot."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
WEB_FILES = (
    "adapter-guide.html", "app.js", "aws-resources.json", "aws-run.css",
    "aws-run.html", "aws-run.js", "evidence-contract.js", "evidence.json",
    "index.html", "local-example.json", "local-report-contract.js", "mark.svg",
    "recorded-lab.html", "reference-repair.js", "repair-app.js",
    "repair-contract.js", "repair-example.json", "repair-transfer.json",
    "repair.css", "repair.html", "styles.css", "regression-case.zip",
    "replayguard-local-regression.zip", "replayguard-repair-lab.zip",
)
REQUIRED = (
    "README.md", "LICENSE", ".gitignore", "requirements.txt", "requirements.lock.txt",
    "scripts/export_source_release.py", "scripts/export_repair.py", "scripts/test_repair.py",
    "docs/demo-script.md", "docs/repair-lab/adapter.md", "docs/repair-lab/schema.md",
    "docs/repair-lab/runbook.md", "docs/repair-lab/transfer.md",
    "docs/iteration-01/plan.json", "docs/iteration-01/historical-sha256.json",
    "docs/iteration-03/generated/local-results.json",
    "docs/iteration-03/generated/broken-key-results.json",
    "evidence/latest.json", "evidence/initial-cold-start.json",
)
OPTIONAL_DOCS = (
    "docs/deadline.md", "docs/deadline-api-snapshot.json", "docs/deadline-evidence.json",
    "docs/deadline-source-manifest.json", "docs/validation.md", "docs/what-we-learned.md",
    "docs/submission.md", "docs/publication-status.md", "docs/design.md",
    "docs/deadline-refresh-20260919.json",
    ".github/workflows/offline-regression.yml", "docs/publication/README.md",
    "docs/screenshots/comparison.png",
)
PATTERNS = (
    "src/*.py", "infra/*.py", "infra/*.json", "scripts/*.py",
    "local_lab/**/*.py", "repair_lab/**/*.py", "cases/**/*.json",
    "examples/dispatchdesk/*.py", "examples/dispatchdesk/README.md",
    "tests/*.py", "tests/*.cjs", "tests/fixtures/*.json", "tests/fixtures/README.md",
    "tests/repair_holdout/*.py", "tests/repair_holdout/*.cjs", "tests/repair_holdout/*.json",
)
REPAIR_DOC_EXTENSIONS = frozenset({".md", ".py", ".json", ".txt", ".srt", ".png", ".jpg"})
DENIED_PARTS = frozenset({".git", ".aws", ".venv", "node_modules", "__pycache__", "competitive-review", "account", "accounts"})
DENIED_NAMES = frozenset({"deployment.local.json", "credentials", "credentials.json", ".env", "config.local.json"})
SOURCE_README = """# ReplayGuard local source snapshot

This archive contains the current static UI, bounded local repair runtime,
reference/application adapters, tests, public run instructions, and selected
historical evidence required by the retained regressions. It is an explicitly
allowlisted source snapshot, not a Git history export or a public deployment.
Private strategy/prior-project research, account configuration, credentials,
and unrelated workspace files are excluded. Old downloadable archives and AWS
evidence retain their original bytes; they do not attest to a new cloud run.
Exporting source makes no AWS calls. Current operating authorization and
accounting limits are recorded in docs/publication-status.md; credits are
not treated as measured gross-spend headroom.

## Run locally

Requires Python 3.11+ on macOS or Linux/POSIX. No package installation or AWS
credentials are needed for the repair lab:

```sh
python3 -I -S scripts/test_repair.py --candidate business-key --case crash-retry --output repaired.json
python3 -m http.server 8088 --bind 127.0.0.1 --directory web
```

Open http://127.0.0.1:8088/ . The static UI reads JSON; it does not run Python.
Read docs/repair-lab/runbook.md for pass/fail/restoration, the independent
DispatchDesk example, trusted-code and simulation limits. The complete
comparison intentionally includes incomplete/unresolved controls and does not
have an all-green exit status. No new cloud execution is claimed.

## Reproduce checks

```sh
python3 -I -S -m unittest discover -s tests -p 'test_repair*.py'
python3 tests/repair_holdout/run_transfer.py --output-dir /tmp/replayguard-transfer-new
```

JavaScript contract checks additionally require an already-installed Node.js:

```sh
node --test tests/test_*.cjs
```

Browser checks require an already-installed Playwright/browser and the loopback
server; they must not install dependencies or query AWS. The historical AWS
deployment scripts and requirements are retained as source. This exporter
does not deploy or publish anything. Current publication links and the
authorized spending boundary are recorded in docs/publication-status.md.
Some retained historical browser and media scripts refer to artifacts outside
this allowlist and require the original workspace. Self-contained validation
is claimed for the documented commands above; it does not imply that every
retained historical script can run from this archive alone.

## Verify and re-export

SOURCE-SHA256SUMS covers every other archive file. SOURCE-PACKAGE.json records
the exact source-file hashes and exclusions. Verify with `shasum -a 256 -c
SOURCE-SHA256SUMS` on macOS or `sha256sum -c SOURCE-SHA256SUMS` on Linux.

```sh
python3 -I -S scripts/export_source_release.py --output source-recreated.zip
```

The same included bytes produce the same ZIP in the same Python/zlib runtime.
Hashes establish byte consistency, not authorship, Git history or authentic
AWS execution. Public report imports remain unauthenticated. Exporting this
snapshot does not deploy hosting, upload a video or submit an entry; confirmed
delivery links are recorded separately in docs/publication-status.md.
The companion narrated MP4 is distributed separately from this source ZIP;
its script, subtitles, captures and render manifest are included under
docs/repair-lab/media/.
"""


def read_source(root, name):
    parts = PurePosixPath(name).parts
    if PurePosixPath(name).is_absolute() or ".." in parts or any(part in DENIED_PARTS for part in parts):
        raise ValueError(f"Disallowed source path: {name}")
    if any(part in DENIED_NAMES or part.startswith(".env.") for part in parts):
        raise ValueError(f"Disallowed private configuration: {name}")
    cursor = root
    for part in parts:
        cursor /= part
        if cursor.is_symlink():
            raise ValueError(f"Symlinked source is not included: {name}")
    if not cursor.is_file():
        raise ValueError(f"Missing required release file: {name}")
    return cursor.read_bytes()


def assemble(root=ROOT):
    root = Path(root).resolve()
    names = set(REQUIRED) | {"web/" + name for name in WEB_FILES}
    names.update(name for name in OPTIONAL_DOCS if (root / name).is_file())
    for pattern in PATTERNS:
        names.update(path.relative_to(root).as_posix() for path in root.glob(pattern) if path.is_file())
    for path in (root / "docs/repair-lab").rglob("*"):
        if path.is_file() and path.suffix in REPAIR_DOC_EXTENSIONS and "__pycache__" not in path.parts:
            names.add(path.relative_to(root).as_posix())
    files = {name: read_source(root, name) for name in sorted(names)}
    files["SOURCE-README.md"] = SOURCE_README.encode()
    files["SOURCE-PACKAGE.json"] = (json.dumps({
        "schemaVersion": 1,
        "kind": "allowlisted-local-source-snapshot",
        "newCloudEvidence": False,
        "publiclyPublished": False,
        "includesGitHistory": False,
        "excludes": ["private competitive/prior-project research", "account and deployment.local.json configuration", "credentials and environment files", "unrelated workspace artifacts", "Git internal history", "video binaries"],
        "sourceSha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())},
    }, indent=2, sort_keys=True) + "\n").encode()
    files["SOURCE-SHA256SUMS"] = "".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())).encode()
    return files


def export(output, root=ROOT):
    root = Path(root).resolve()
    output = Path(output).absolute()
    files = assemble(root)
    if output.is_symlink() or output.resolve() in {root / name for name in files} or output.resolve().is_relative_to(root / "evidence"):
        raise ValueError("Release output cannot replace a source/evidence artifact or symlink")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=output.name + ".", suffix=".tmp", dir=output.parent, delete=False) as handle:
            temporary = Path(handle.name)
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name, date_time=(2026, 9, 19, 0, 0, 0))
                entry.compress_type = zipfile.ZIP_DEFLATED
                entry.create_system = 3
                entry.external_attr = 0o644 << 16
                archive.writestr(entry, data)
        temporary.replace(output)
        return {"path": str(output), "files": len(files), "bytes": output.stat().st_size, "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}
    finally:
        if temporary and temporary.exists():
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export(args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(json.dumps({**result, "published": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
