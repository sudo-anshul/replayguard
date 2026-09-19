"""The source-release allowlist excludes private content and is reproducible."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location("source_export", Path(__file__).resolve().parents[1] / "scripts/export_source_release.py")
EXPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EXPORT)


class SourceExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        names = set(EXPORT.REQUIRED) | {"web/" + name for name in EXPORT.WEB_FILES}
        for name in names:
            self.write(name, "fixture\n")

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_private_research_and_credentials_are_not_selected(self):
        forbidden = ["docs/competitive-review/strategy.md", "deployment.local.json", ".aws/credentials", "account/config.json", "prior-project-history.txt"]
        for name in forbidden:
            self.write(name, "private fixture")
        files = EXPORT.assemble(self.root)
        self.assertFalse(set(files) & set(forbidden))
        self.assertIn("SOURCE-SHA256SUMS", files)

    def test_private_configuration_inside_public_docs_fails_closed(self):
        self.write("docs/repair-lab/deployment.local.json", "private fixture")
        with self.assertRaisesRegex(ValueError, "private configuration"):
            EXPORT.assemble(self.root)

    def test_missing_required_browser_asset_is_rejected(self):
        (self.root / "web/repair-contract.js").unlink()
        with self.assertRaisesRegex(ValueError, "Missing required release file"):
            EXPORT.assemble(self.root)

    def test_reexport_matches_and_source_artifacts_are_protected(self):
        original = self.root / "original.zip"
        EXPORT.export(original, self.root)
        extraction = self.root / "extracted"
        with zipfile.ZipFile(original) as archive:
            archive.extractall(extraction)
        recreated = self.root / "recreated.zip"
        EXPORT.export(recreated, extraction)
        self.assertEqual(original.read_bytes(), recreated.read_bytes())
        protected = self.root / "web/regression-case.zip"
        before = protected.read_bytes()
        with self.assertRaisesRegex(ValueError, "cannot replace"):
            EXPORT.export(protected, self.root)
        self.assertEqual(protected.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
