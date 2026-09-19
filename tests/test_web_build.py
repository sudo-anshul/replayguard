"""Verify the public viewer's build and untouched evidence embedding, offline."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_web", ROOT / "scripts/build_web.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Page(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.links = []
        self.scripts = {}
        self.script = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.append(attrs["id"])
        for name in ("href", "src"):
            if name in attrs:
                self.links.append(attrs[name])
        if tag == "script" and attrs.get("type") == "application/json":
            self.script = attrs["id"]
            self.scripts[self.script] = ""

    def handle_endtag(self, tag):
        if tag == "script":
            self.script = None

    def handle_data(self, data):
        if self.script:
            self.scripts[self.script] += data


class WebBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.outputs = MODULE.build()
        cls.html = cls.outputs["web/index.html"].decode("utf-8")
        cls.page = Page(cls.html)

    def test_deterministic_outputs_match_committed_build(self):
        self.assertEqual(self.outputs, MODULE.build())
        for name, data in self.outputs.items():
            self.assertEqual(data, (ROOT / name).read_bytes(), name + " needs rebuild")

    def test_aliases_and_important_anchors_survive(self):
        self.assertEqual(self.outputs["web/index.html"], self.outputs["web/repair.html"])
        self.assertEqual(len(self.page.ids), len(set(self.page.ids)))
        for anchor in ("top", "page-title", "bench", "inspector", "run", "evidence", "replay"):
            self.assertIn(anchor, self.page.ids)

    def test_recordings_preserve_exact_original_utf8_bytes(self):
        for element, source in (("example-report", "repair-example.json"), ("transfer-report", "repair-transfer.json")):
            text = json.loads(self.page.scripts[element])
            self.assertEqual(text.encode("utf-8"), (ROOT / "web" / source).read_bytes())
            self.assertNotIn("<", self.page.scripts[element], "data must not close an HTML script")

    def test_generated_manifest_matches_assets_and_sources(self):
        manifest = json.loads(self.outputs["web/build-manifest.json"])
        for name, digest in manifest["assets"].items():
            self.assertEqual(hashlib.sha256(self.outputs[name]).hexdigest(), digest, name)
        for name, digest in manifest["sources"].items():
            self.assertEqual(hashlib.sha256((ROOT / name).read_bytes()).hexdigest(), digest, name)

    def test_local_rendering_assets_and_downloads_exist(self):
        for link in self.page.links:
            if link.startswith("./"):
                path = link.split("?", 1)[0].split("#", 1)[0][2:]
                self.assertTrue((ROOT / "web" / path).is_file(), link)
            elif link.startswith("#"):
                self.assertIn(link[1:], self.page.ids, link)
        self.assertNotIn("127.0.0.1", self.html)
        self.assertNotIn("localhost", self.html)
        self.assertNotIn('src="https://', self.html)


if __name__ == "__main__":
    unittest.main()
