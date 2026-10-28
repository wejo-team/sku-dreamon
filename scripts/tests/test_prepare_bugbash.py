"""검사 환경 준비가 개발 DB를 기본값이나 명시적 대상으로 받지 않게 확인한다."""

import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from scripts import prepare_bugbash


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        self.root = Path(directory)
        self.output = self.root / ".bugbash"
        self.output.mkdir()
        (self.root / "frontend").mkdir()
        for name in ("localhost.pem", "localhost-key.pem"):
            (self.output / name).write_text("synthetic-certificate\n")
        self.stack.enter_context(patch.object(prepare_bugbash, "ROOT", self.root))
        self.stack.enter_context(patch.object(prepare_bugbash, "OUTPUT", self.output))

    def run_prepare(self, *arguments):
        with patch.object(sys, "argv", ["prepare_bugbash.py", *arguments]):
            prepare_bugbash.main()

    def test_default_targets_isolated_browser_database_and_ports(self):
        self.run_prepare()
        settings = (self.output / "backend.env").read_text()
        frontend = (self.root / "frontend/.env.bugbash").read_text()
        self.assertIn("127.0.0.1:55433/wejo_e2e", settings)
        self.assertNotIn("wejo_dev", settings)
        self.assertIn("https://localhost:5185", settings)
        self.assertIn("API_PROXY_TARGET=http://127.0.0.1:8013", frontend)

    def test_explicit_database_port_is_used_for_both_test_databases(self):
        self.run_prepare("--database-name", "parallel_e2e", "--database-port", "55434")
        self.assertIn(
            "127.0.0.1:55434/parallel_e2e",
            (self.output / "backend.env").read_text(),
        )
        self.assertIn(
            "127.0.0.1:55434/wejo_test", (self.output / "test.env").read_text()
        )

    def test_rejects_development_database_without_writing_settings(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_prepare("--database-name", "wejo_dev")
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.output / "backend.env").exists())
        self.assertFalse((self.root / "frontend/.env.bugbash").exists())

    def test_rejects_out_of_range_database_port(self):
        with self.assertRaises(SystemExit) as raised:
            self.run_prepare("--database-port", "65536")
        self.assertEqual(raised.exception.code, 2)
        self.assertFalse((self.output / "backend.env").exists())

    def test_repeated_preparation_preserves_key_and_rejects_database_change(self):
        self.run_prepare()
        previous = (self.output / "backend.env").read_text()
        self.run_prepare()
        self.assertEqual((self.output / "backend.env").read_text(), previous)
        with self.assertRaises(SystemExit):
            self.run_prepare("--database-name", "different_e2e")
        self.assertEqual((self.output / "backend.env").read_text(), previous)


if __name__ == "__main__":
    unittest.main()
