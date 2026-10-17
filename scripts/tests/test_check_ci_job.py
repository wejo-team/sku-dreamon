import itertools
import os
import subprocess
import sys
import unittest
from pathlib import Path

from scripts.check_ci_job import validate_result

SCRIPT = Path(__file__).resolve().parents[1] / "check_ci_job.py"


class RequiredCiCheckTests(unittest.TestCase):
    def test_only_successful_selected_or_explicitly_unaffected_checks_pass(self):
        results = ("success", "failure", "cancelled", "skipped", "", "unknown")
        flags = ("true", "false", "", "TRUE", "unknown")
        accepted = {
            ("success", "true", "success"),
            ("success", "false", "skipped"),
        }
        for case in itertools.product(results, flags, results):
            with self.subTest(case=case):
                if case in accepted:
                    validate_result(*case)
                else:
                    with self.assertRaises(ValueError):
                        validate_result(*case)

    def test_cli_fails_closed_when_outputs_are_missing_or_detection_failed(self):
        for scope_result in ("", "failure", "cancelled", "skipped"):
            with self.subTest(scope_result=scope_result):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT)],
                    env={
                        **os.environ,
                        "SCOPE_RESULT": scope_result,
                        "CHECK_REQUIRED": "false",
                        "CHECK_RESULT": "skipped",
                    },
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertIn("scope detection must succeed", result.stderr)


if __name__ == "__main__":
    unittest.main()
