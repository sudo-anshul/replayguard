"""Portable repair exports preserve boundaries and deterministic bytes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("repair_export", Path(__file__).resolve().parents[1] / "scripts/export_repair.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class RepairExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        names = set(EXPORT.REQUIRED) | {"docs/repair-lab/runbook.md", "tests/repair_holdout/dispatchdesk-plan.json"}
        for name in names:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}\n" if name.endswith(".json") else "test fixture\n")

    def tearDown(self):
        self.temp.cleanup()

    def test_only_whitelisted_content_and_complete_hashes(self):
        private = self.root / "docs/competitive-review/private.md"
        private.parent.mkdir(parents=True)
        private.write_text("Never part of a runnable package")
        files = EXPORT.assemble(self.root)
        self.assertNotIn("docs/competitive-review/private.md", files)
        self.assertNotIn("tests/repair_holdout/dispatchdesk-plan.json", files)
        self.assertEqual(files["examples/dispatchdesk/cases.json"], b"{}\n")
        sums = dict(line.split("  ", 1)[::-1] for line in files["SHA256SUMS"].decode().splitlines())
        self.assertEqual(set(sums), set(files) - {"SHA256SUMS"})
        for name, digest in sums.items():
            self.assertEqual(digest, hashlib.sha256(files[name]).hexdigest())
        metadata = json.loads(files["PACKAGE.json"])
        self.assertEqual(set(metadata["sourceSha256"]), set(files) - {"PACKAGE.json", "SHA256SUMS"})

    def test_symlinked_sources_are_rejected(self):
        source = self.root / "examples/dispatchdesk/worker.py"
        source.unlink()
        private = self.root / "private.py"
        private.write_text("not distributable")
        source.symlink_to(private)
        with self.assertRaisesRegex(ValueError, "symlinked"):
            EXPORT.assemble(self.root)

    def test_missing_runtime_is_rejected(self):
        (self.root / "repair_lab/engine.py").unlink()
        with self.assertRaisesRegex(ValueError, "Missing required package source"):
            EXPORT.assemble(self.root)

    def test_reexport_from_extraction_is_byte_identical(self):
        first = self.root / "first.zip"
        EXPORT.export(first, self.root)
        extraction = self.root / "extracted"
        with zipfile.ZipFile(first) as archive:
            archive.extractall(extraction)
        second = self.root / "second.zip"
        EXPORT.export(second, extraction)
        self.assertEqual(first.read_bytes(), second.read_bytes())

    def test_historical_archive_names_cannot_be_replaced(self):
        for name in EXPORT.PROTECTED_ARCHIVES:
            target = self.root / name
            target.write_bytes(b"historical bytes")
            with self.assertRaisesRegex(ValueError, "historical"):
                EXPORT.export(target, self.root)
            self.assertEqual(target.read_bytes(), b"historical bytes")

    def test_package_source_cannot_be_replaced_by_output(self):
        source = self.root / "repair_lab/plans.py"
        before = source.read_bytes()
        with self.assertRaisesRegex(ValueError, "package source"):
            EXPORT.export(source, self.root)
        self.assertEqual(source.read_bytes(), before)

    def test_evidence_cannot_be_replaced_by_output(self):
        evidence = self.root / "evidence/latest.json"
        evidence.parent.mkdir()
        evidence.write_text('{"historical": true}\n')
        before = evidence.read_bytes()
        with self.assertRaisesRegex(ValueError, "preserved evidence"):
            EXPORT.export(evidence, self.root)
        self.assertEqual(evidence.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
