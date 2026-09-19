"""AWS web-build controls using explicitly mocked observations in temporary roots.

No mock is written to the public web directory or presented as real AWS evidence.
"""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


BUILD = module("web_aws_build", ROOT / "scripts/build_web.py")
MOCK = module("web_aws_mock_controls", ROOT / "tests/test_aws_key_scope.py")


class AwsWebViewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock = MOCK.executed_fixture()

    def view(self, evidence=None, archive_evidence=None):
        with tempfile.TemporaryDirectory(prefix="replayguard-mock-web-test-") as folder:
            root = Path(folder)
            (root / "web").mkdir()
            (root / "scripts").mkdir()
            (root / "scripts/verify_key_case.py").write_bytes((ROOT / "scripts/verify_key_case.py").read_bytes())
            raw = None
            if evidence is not None:
                raw = (json.dumps(evidence, indent=2) + "\n").encode()
                (root / "web/aws-key-scope-report.json").write_bytes(raw)
            if archive_evidence is not None:
                with zipfile.ZipFile(root / "web/aws-key-scope-regression.zip", "w") as package:
                    package.writestr("evidence.json", archive_evidence)
            return BUILD.aws_key_scope_view(root, lambda name: (root / name).read_bytes()), raw

    def test_missing_report_has_no_results_or_downloads(self):
        view, _ = self.view()
        self.assertIsNone(view["report"])
        self.assertIsNone(view["verification"])
        self.assertIsNone(view["archive"])

    def test_verdict_recomputed_from_mock_observations_with_separate_business_states(self):
        view, raw = self.view(self.mock)
        self.assertEqual(view["verification"]["experimentStatus"], "passed")
        self.assertEqual([r["status"] for r in view["verification"]["candidateResults"]], ["violation", "violation", "passed"])
        self.assertEqual(view["report"]["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertIsNone(view["archive"])

    def test_saved_optimistic_verdict_does_not_override_missing_fault_evidence(self):
        changed = copy.deepcopy(self.mock)
        changed["result"] = MOCK.verifier.verify(self.mock)
        changed["events"] = [event for event in changed["events"] if event["stage"] != "fault_injected"]
        view, _ = self.view(changed)
        self.assertEqual(view["verification"]["experimentStatus"], "unresolved")
        self.assertTrue(any(row["id"] == "stored-verdict" for row in view["verification"]["assertions"]))

    def test_missing_query_keeps_counts_unknown(self):
        changed = copy.deepcopy(self.mock)
        changed["ledgerObservations"] = [row for row in changed["ledgerObservations"] if row["candidate"] != "order-key"]
        view, _ = self.view(changed)
        candidate = view["verification"]["candidateResults"][-1]
        self.assertEqual(candidate["status"], "incomplete")
        self.assertTrue(all(value is None for value in candidate["receiptCounts"].values()))

    def test_archive_link_requires_exact_same_report_bytes(self):
        raw = (json.dumps(self.mock, indent=2) + "\n").encode()
        matched, _ = self.view(self.mock, raw)
        self.assertIsNotNone(matched["archive"])
        stale, _ = self.view(self.mock, raw + b" ")
        self.assertIsNone(stale["archive"])
        self.assertIn("exact report bytes", stale["archiveIssue"])

    def test_local_report_cannot_be_routed_through_aws_view(self):
        local = json.loads((ROOT / "web/repair-example.json").read_bytes())
        with self.assertRaisesRegex(ValueError, "separately versioned actual AWS report"):
            self.view(local)


if __name__ == "__main__":
    unittest.main()
