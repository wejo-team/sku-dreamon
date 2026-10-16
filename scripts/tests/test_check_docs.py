import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_docs import DocsChecker, ValidationError


class DocsCheckTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.write("docs/README.md", "# 문서 홈\n")

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        return target

    def check(self):
        return DocsChecker(self.root).check()

    def snapshot(self):
        return {
            path.relative_to(self.root).as_posix(): (
                path.read_bytes() if path.is_file() else None
            )
            for path in self.root.rglob("*")
        }

    def test_relative_links_directory_indexes_unicode_and_fragments(self):
        self.write("docs/development/README.md", "# 개발 가이드\n## 실행 방법\n")
        self.write(
            "docs/README.md",
            "# 홈\n[가이드](development/)\n[실행](development/README.md#실행-방법)\n[홈](#홈)\n",
        )
        self.assertEqual(self.check(), 2)

    def test_images_and_repository_files_are_checked_without_modification(self):
        self.write("docs/assets/a b.png", "image")
        self.write("backend/main.py", "pass")
        self.write(
            "docs/README.md",
            "# 홈\n![화면](<assets/a b.png>)\n[코드](../backend/main.py#L1)\n[폴더](../backend/)\n",
        )
        before = self.snapshot()
        self.assertEqual(self.check(), 1)
        self.assertEqual(self.snapshot(), before)
        (self.root / "backend/main.py").unlink()
        with self.assertRaisesRegex(ValidationError, "missing link target"):
            self.check()

    def test_reference_images_links_and_external_urls(self):
        self.write("docs/assets/logo.png", "image")
        self.write("docs/guide.md", "# Guide\n")
        self.write(
            "docs/README.md",
            '# 홈\n![로고][logo]\n[안내][guide]\n\n[logo]: assets/logo.png "로고"\n[guide]: guide.md\n[외부](https://example.com/a(b)?x=1&y=2#ok)\n[메일](mailto:docs@example.com)\n',
        )
        self.assertEqual(self.check(), 2)
        (self.root / "docs/assets/logo.png").unlink()
        with self.assertRaisesRegex(ValidationError, "missing link target"):
            self.check()

    def test_code_examples_are_not_checked_as_links(self):
        self.write(
            "docs/README.md",
            "# 홈\n`[example](missing.md)`\n```md\n[example](missing.md)\n```\n~~~md\n[example](missing.md)\n~~~\n    [example](missing.md)\n",
        )
        self.assertEqual(self.check(), 1)

    def test_link_labels_with_code_and_escaped_heading_fragments(self):
        self.write("docs/config.md", "# 설정\n## `uv` 설정\n")
        self.write(
            "docs/README.md", "# 홈\n[`uv` 설정](config.md#uv-%EC%84%A4%EC%A0%95)\n"
        )
        self.assertEqual(self.check(), 2)

    def test_missing_target_or_fragment_is_rejected(self):
        for target in ["missing.md", "README.md#missing-heading", "assets/missing.png"]:
            with self.subTest(target=target):
                self.write("docs/README.md", f"# 홈\n[링크]({target})\n")
                with self.assertRaises(ValidationError):
                    self.check()

    def test_traversal_encoded_traversal_and_unsupported_paths_are_rejected(self):
        for target in [
            "../../outside.md",
            "%2e%2e/%2e%2e/outside.md",
            "/etc/passwd",
            "javascript:alert(1)",
            "//example.com/page",
            "bad%00path",
            "bad%5cpath",
        ]:
            with self.subTest(target=target):
                self.write("docs/README.md", f"# 홈\n[링크]({target})\n")
                with self.assertRaises(ValidationError):
                    self.check()

    def test_symlinked_documents_and_escaping_asset_links_are_rejected(self):
        link = self.root / "docs/escape.md"
        link.symlink_to(self.root / "docs/README.md")
        with self.assertRaisesRegex(ValidationError, "symlinked document"):
            self.check()
        link.unlink()
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "image.png"
            target.write_text("image")
            (self.root / "docs/escape.png").symlink_to(target)
            self.write("docs/README.md", "# 홈\n![이미지](escape.png)\n")
            with self.assertRaisesRegex(ValidationError, "link escapes repository"):
                self.check()

    def test_images_cannot_point_to_directories(self):
        self.write("docs/assets/README.md", "# 자산\n")
        for image in ["![이미지](assets/)", "![이미지][asset]\n\n[asset]: assets/"]:
            with self.subTest(image=image):
                self.write("docs/README.md", f"# 홈\n{image}\n")
                with self.assertRaisesRegex(ValidationError, "image target must be a file"):
                    self.check()

    def test_local_html_links_and_unclosed_angle_links_are_rejected(self):
        self.write("docs/guide.md", "# Guide\n")
        for link in ['<a href="guide.md">Guide</a>', "[Guide](<guide.md)"]:
            with self.subTest(link=link):
                self.write("docs/README.md", f"# 홈\n{link}\n")
                with self.assertRaises(ValidationError):
                    self.check()

    def test_page_names_do_not_have_flat_export_restrictions(self):
        for path in ["a-b.md", "a/b.md", "A-B.md", "_Sidebar.md", "_Footer.md"]:
            self.write(f"docs/{path}", "# 문서\n")
        self.assertEqual(self.check(), 6)

    def test_missing_document_index_is_rejected(self):
        (self.root / "docs/README.md").unlink()
        with self.assertRaisesRegex(ValidationError, "docs/README.md"):
            self.check()

    def test_cli_returns_failure_without_changing_files(self):
        script = Path(__file__).resolve().parents[1] / "check_docs.py"
        local_script = self.write("scripts/check_docs.py", script.read_text())
        for markdown, expected_status in [
            ("# 홈\n", 0),
            ("# 홈\n[누락](missing.md)\n", 1),
        ]:
            with self.subTest(expected_status=expected_status):
                self.write("docs/README.md", markdown)
                before = self.snapshot()
                result = subprocess.run(
                    [sys.executable, str(local_script)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, expected_status, result.stderr)
                if expected_status:
                    self.assertIn("missing link target", result.stderr)
                else:
                    self.assertIn("1 source Markdown documents", result.stdout)
                self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
