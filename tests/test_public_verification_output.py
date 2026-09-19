"""Existing deployment evidence must survive a mistaken verifier output path."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class PublicationOutputTests(unittest.TestCase):
    def test_existing_evidence_rejected_before_network_or_input_parse(self):
        script = Path(__file__).resolve().parents[1] / "scripts/verify_public_site.py"
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "deployment.json"
            original = b"original evidence; deliberately not JSON\n"
            evidence.write_bytes(original)
            for output in (evidence, Path(directory) / "prior-verification.json"):
                with self.subTest(output=output.name):
                    output.write_bytes(original)
                    result = subprocess.run(
                        [sys.executable, "-I", "-S", str(script), str(evidence), "--output", str(output)],
                        capture_output=True, text=True, timeout=5,
                    )
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("Output must be a new file", result.stderr)
                    self.assertEqual(output.read_bytes(), original)
                    self.assertEqual(evidence.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
