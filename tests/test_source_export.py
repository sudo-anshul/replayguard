"""The source-release allowlist excludes private content and is reproducible."""
import hashlib
import importlib.util
import json
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

    def write_demo_manifest(self, names):
        indexed = {name: hashlib.sha256((self.root / EXPORT.DEMO_ROOT / name).read_bytes()).hexdigest() for name in names}
        self.write(EXPORT.DEMO_ROOT + "/source-manifest.json", json.dumps({
            "status": "complete", "selfContainedStaticInputs": True, "files": indexed,
        }))

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

    def test_rendered_demo_outputs_do_not_change_source_export(self):
        included = ["README.md", "src/Film.tsx", "frames/original.jpg", "captures/scene/manifest.json"]
        for name in included:
            self.write(EXPORT.DEMO_ROOT + "/" + name, "static demo input\n")
        self.write_demo_manifest(included)
        original = self.root / "before-render.zip"
        EXPORT.export(original, self.root)
        generated = [
            "captures/scene/source.mp4", "captures/scene/encoded-source.json",
            "captures/scene/editorial.ffconcat", "public/media/clip.mp4",
            "render/replayguard-demo-silent.mp4", "prepared.json", "asset-manifest.json",
            "final-review/frame.jpg", "node_modules/package/index.js",
        ]
        for name in generated:
            self.write(EXPORT.DEMO_ROOT + "/" + name, "generated /Users/private/workspace\n")
        after = self.root / "after-render.zip"
        EXPORT.export(after, self.root)
        self.assertEqual(original.read_bytes(), after.read_bytes())
        with zipfile.ZipFile(after) as archive:
            self.assertTrue({EXPORT.DEMO_ROOT + "/" + name for name in included}.issubset(archive.namelist()))
            self.assertFalse({EXPORT.DEMO_ROOT + "/" + name for name in generated} & set(archive.namelist()))

    def test_tampered_or_missing_indexed_demo_source_is_rejected(self):
        name = "src/Film.tsx"
        path = self.write(EXPORT.DEMO_ROOT + "/" + name, "frozen source\n")
        self.write_demo_manifest([name])
        path.write_text("changed source\n")
        with self.assertRaisesRegex(ValueError, "Demo source hash mismatch"):
            EXPORT.assemble(self.root)
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing required release file"):
            EXPORT.assemble(self.root)

    def test_generated_demo_files_cannot_be_added_to_manifest(self):
        for name in ["source.mp4", "clip.MP4", "clip.webm", "voice.mp3", "render/result.json", "public/media/frame.jpg", "asset-manifest.json", "captures/scene/encoded-source.json"]:
            with self.subTest(name=name):
                self.write(EXPORT.DEMO_ROOT + "/" + name, "generated fixture\n")
                self.write_demo_manifest([name])
                with self.assertRaisesRegex(ValueError, "Generated or unsupported demo source"):
                    EXPORT.assemble(self.root)

    def test_demo_requires_complete_manifest_and_valid_hashes(self):
        self.write(EXPORT.DEMO_ROOT + "/README.md", "demo source\n")
        with self.assertRaisesRegex(ValueError, "Missing required release file"):
            EXPORT.assemble(self.root)
        self.write_demo_manifest(["README.md"])
        path = self.root / EXPORT.DEMO_ROOT / "source-manifest.json"
        complete = json.loads(path.read_text())
        for invalid in [
            {**complete, "status": "incomplete"},
            {**complete, "files": {}},
            {**complete, "files": {"README.md": "not-a-hash"}},
            {**complete, "files": {"../outside.py": "0" * 64}},
        ]:
            with self.subTest(manifest=invalid):
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    EXPORT.assemble(self.root)


if __name__ == "__main__":
    unittest.main()
