"""제품 기호 표의 서버 Unicode 일치와 보관한 레퍼런스의 독립성을 검사한다."""

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
    def test_checked_in_product_table_matches_generator(self):
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

    def test_check_detects_product_drift_without_overwriting(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = generator.render_module()
            product = root / "frontend/src/features/demo/password-symbols.ts"
            product.parent.mkdir(parents=True)
            product.write_text(expected + "// drift\n", encoding="utf-8")
            errors = io.StringIO()
            with (
                patch.object(generator, "ROOT", root),
                patch.object(sys, "argv", ["generate_password_symbols.py", "--check"]),
                contextlib.redirect_stderr(errors),
            ):
                self.assertEqual(generator.main(), 1)
            self.assertIn(str(product.relative_to(root)), errors.getvalue())
            self.assertNotIn("design-reference/", errors.getvalue())
            self.assertEqual(
                product.read_text(encoding="utf-8"), expected + "// drift\n"
            )

    def test_generation_and_check_leave_archived_reference_independent(self):
        expected = generator.render_module()
        for reference_exists in (True, False):
            with self.subTest(reference_exists=reference_exists):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    product = root / "frontend/src/features/demo/password-symbols.ts"
                    product.parent.mkdir(parents=True)
                    product.write_text("// stale product\n", encoding="utf-8")
                    reference = root / (
                        "design-reference/src/features/design-preview/password-symbols.ts"
                    )
                    archived = "// archived reference may differ\n"
                    if reference_exists:
                        reference.parent.mkdir(parents=True)
                        reference.write_text(archived, encoding="utf-8")
                    for arguments in ([], ["--check"]):
                        with (
                            patch.object(generator, "ROOT", root),
                            patch.object(
                                sys, "argv", ["generate_password_symbols.py", *arguments]
                            ),
                            contextlib.redirect_stdout(io.StringIO()),
                        ):
                            self.assertEqual(generator.main(), 0)
                        self.assertEqual(product.read_text(encoding="utf-8"), expected)
                        if reference_exists:
                            self.assertEqual(
                                reference.read_text(encoding="utf-8"), archived
                            )
                        else:
                            self.assertFalse(reference.exists())

    def test_generation_rejects_a_different_unicode_version(self):
        with patch.object(unicodedata, "unidata_version", "17.0.0"):
            with self.assertRaisesRegex(RuntimeError, "Unicode 15.1.0"):
                generator.render_module()


if __name__ == "__main__":
    unittest.main()
