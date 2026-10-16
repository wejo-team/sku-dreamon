import tempfile
import unittest
from pathlib import Path

from scripts.export_wiki import ExportError, WikiExporter


class WikiExportTests(unittest.TestCase):
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

    def exporter(self):
        return WikiExporter(self.root, "wejo-team/wejo-app", "abc123")

    def test_flat_pages_home_and_navigation_have_source_links(self):
        self.write("docs/development/README.md", "# 개발 가이드\n")
        self.write("docs/agents/README.md", "# 에이전트 가이드\n")
        self.assertEqual(self.exporter().export(), 3)
        output = self.root / ".wiki-build"
        self.assertEqual(
            {path.name for path in output.iterdir()},
            {
                "Home.md",
                "development-README.md",
                "agents-README.md",
                "_Sidebar.md",
                "_Footer.md",
            },
        )
        self.assertIn("/blob/abc123/docs/README.md", (output / "Home.md").read_text())
        self.assertIn("/edit/main/docs/README.md", (output / "Home.md").read_text())
        self.assertIn("/wiki/agents-README", (output / "_Sidebar.md").read_text())
        self.assertIn("/commit/abc123", (output / "_Footer.md").read_text())

    def test_relative_links_directory_indexes_unicode_and_fragments(self):
        self.write("docs/development/README.md", "# 개발 가이드\n## 실행 방법\n")
        self.write(
            "docs/README.md",
            "# 홈\n[가이드](development/)\n[실행](development/README.md#실행-방법)\n[홈](#홈)\n",
        )
        text = self.exporter().render(self.root / "docs/README.md")
        self.assertIn("/wiki/development-README#실행-방법", text)
        self.assertIn("/wiki/Home#홈", text)

    def test_image_raw_url_code_blob_and_directory_tree(self):
        self.write("docs/assets/a b.png", "image")
        self.write("backend/main.py", "pass")
        source = self.write(
            "docs/README.md",
            "# 홈\n![화면](<assets/a b.png>)\n[코드](../backend/main.py#L1)\n[폴더](../backend/)\n",
        )
        text = self.exporter().render(source)
        self.assertIn(
            "https://raw.githubusercontent.com/wejo-team/wejo-app/abc123/docs/assets/a%20b.png",
            text,
        )
        self.assertIn("/blob/abc123/backend/main.py#L1", text)
        self.assertIn("/tree/abc123/backend", text)

    def test_reference_images_and_links_and_external_urls(self):
        self.write("docs/assets/logo.png", "image")
        self.write("docs/guide.md", "# Guide\n")
        source = self.write(
            "docs/README.md",
            '# 홈\n![로고][logo]\n[안내][guide]\n\n[logo]: assets/logo.png "로고"\n[guide]: guide.md\n[외부](https://example.com/a(b)?x=1&y=2#ok)\n',
        )
        text = self.exporter().render(source)
        self.assertIn("[logo]: https://raw.githubusercontent.com/", text)
        self.assertIn(
            "[guide]: https://github.com/wejo-team/wejo-app/wiki/guide\n", text
        )
        self.assertIn("https://example.com/a(b)?x=1&y=2#ok", text)

    def test_code_examples_remain_untouched(self):
        source = self.write(
            "docs/README.md",
            "# 홈\n`[example](missing.md)`\n```md\n[example](missing.md)\n```\n    [example](missing.md)\n",
        )
        self.assertIn("`[example](missing.md)`", self.exporter().render(source))

    def test_link_labels_with_code_and_escaped_heading_fragments(self):
        self.write("docs/config.md", "# 설정\n## `uv` 설정\n")
        source = self.write(
            "docs/README.md", "# 홈\n[`uv` 설정](config.md#uv-%EC%84%A4%EC%A0%95)\n"
        )
        text = self.exporter().render(source)
        self.assertIn(
            "[`uv` 설정](https://github.com/wejo-team/wejo-app/wiki/config#uv-%EC%84%A4%EC%A0%95)",
            text,
        )

    def test_missing_target_or_fragment_is_rejected(self):
        for target in ["missing.md", "README.md#missing-heading"]:
            with self.subTest(target=target):
                source = self.write("docs/README.md", f"# 홈\n[링크]({target})\n")
                with self.assertRaises(ExportError):
                    self.exporter().render(source)

    def test_traversal_encoded_traversal_and_symlinks_are_rejected(self):
        for target in [
            "../../outside.md",
            "%2e%2e/%2e%2e/outside.md",
            "/etc/passwd",
            "javascript:alert(1)",
        ]:
            with self.subTest(target=target):
                source = self.write("docs/README.md", f"# 홈\n[링크]({target})\n")
                with self.assertRaises(ExportError):
                    self.exporter().render(source)
        self.write("docs/README.md", "# 홈\n")
        (self.root / "docs/escape.md").symlink_to("/etc/passwd")
        with self.assertRaises(ExportError):
            self.exporter()

    def test_case_and_flat_name_collisions_are_rejected(self):
        self.write("docs/a-b.md", "# One\n")
        self.write("docs/a/b.md", "# Two\n")
        with self.assertRaisesRegex(ExportError, "collision"):
            self.exporter()
        (self.root / "docs/a/b.md").unlink()
        self.write("docs/A-B.md", "# Three\n")
        with self.assertRaisesRegex(ExportError, "collision"):
            self.exporter()

    def test_reserved_names_and_missing_home_are_rejected(self):
        self.write("docs/_Sidebar.md", "# Sidebar\n")
        with self.assertRaisesRegex(ExportError, "collision"):
            self.exporter()
        (self.root / "docs/_Sidebar.md").unlink()
        (self.root / "docs/README.md").unlink()
        with self.assertRaisesRegex(ExportError, "README"):
            self.exporter()

    def test_failed_export_preserves_previous_output(self):
        self.exporter().export()
        previous = (self.root / ".wiki-build/Home.md").read_text()
        self.write("docs/broken.md", "# Broken\n[missing](missing.md)\n")
        with self.assertRaises(ExportError):
            self.exporter().export()
        self.assertEqual((self.root / ".wiki-build/Home.md").read_text(), previous)

    def test_repeat_export_is_deterministic_and_removes_stale_pages(self):
        self.write("docs/old.md", "# Old\n")
        self.exporter().export()
        (self.root / "docs/old.md").unlink()
        self.exporter().export()
        self.assertFalse((self.root / ".wiki-build/old.md").exists())
        before = {
            path.name: path.read_bytes()
            for path in (self.root / ".wiki-build").iterdir()
        }
        self.exporter().export()
        after = {
            path.name: path.read_bytes()
            for path in (self.root / ".wiki-build").iterdir()
        }
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
