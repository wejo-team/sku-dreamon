"""체크인된 프론트 기호 집합이 서버 Unicode 버전 및 레퍼런스와 같은지 검사한다."""

import contextlib
import io
import re
import sys
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import generate_password_symbols as generator


class PasswordSymbolTests(unittest.TestCase):
    def test_checked_in_tables_match_generator_and_each_other(self):
        with patch.object(sys, "argv", ["generate_password_symbols.py", "--check"]):
            self.assertEqual(generator.main(), 0)

    def test_checked_in_ranges_match_every_server_unicode_category(self):
        source = (generator.ROOT / generator.TARGETS[0]).read_text(encoding="utf-8")
        pattern = source.split("/[", 1)[1].split("]/u;", 1)[0]
        parts = list(
            re.finditer(r"\\u\{([0-9A-F]+)\}(?:-\\u\{([0-9A-F]+)\})?", pattern)
        )
        self.assertEqual("".join(part.group() for part in parts), pattern)
        included = bytearray(0x110000)
        for part in parts:
            first = int(part.group(1), 16)
            last = int(part.group(2) or part.group(1), 16)
            included[first : last + 1] = b"\x01" * (last - first + 1)
        for codepoint in range(0x110000):
            expected = unicodedata.category(chr(codepoint)).startswith(("P", "S"))
            if bool(included[codepoint]) != expected:
                self.fail(f"서버와 프론트의 기호 판정 불일치: U+{codepoint:04X}")

    def test_check_detects_reference_drift_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = generator.render_module()
            for relative in generator.TARGETS:
                path = root / relative
                path.parent.mkdir(parents=True)
                path.write_text(expected, encoding="utf-8")
            reference = root / generator.TARGETS[1]
            reference.write_text(expected + "// drift\n", encoding="utf-8")
            with (
                patch.object(generator, "ROOT", root),
                patch.object(sys, "argv", ["generate_password_symbols.py", "--check"]),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(generator.main(), 1)
            self.assertEqual(
                reference.read_text(encoding="utf-8"), expected + "// drift\n"
            )

    def test_generation_rejects_a_different_unicode_version(self):
        with patch.object(unicodedata, "unidata_version", "17.0.0"):
            with self.assertRaisesRegex(RuntimeError, "Unicode 15.1.0"):
                generator.render_module()


if __name__ == "__main__":
    unittest.main()
