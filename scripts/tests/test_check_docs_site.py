import tempfile
import unittest
from pathlib import Path

from scripts.check_docs_site import check_site


class DocsSiteTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.write("index.html", '<a href="/sku-dreamon/development/">개발</a>')
        self.write("development/index.html", '<h1 id="개발-안내">개발 안내</h1>')

    def write(self, path, text):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")

    def test_directory_html_and_relative_links_with_unicode_fragments(self):
        self.write(
            "development/index.html",
            '<h1 id="개발-안내">개발 안내</h1>'
            '<a href="index.html#%EA%B0%9C%EB%B0%9C-%EC%95%88%EB%82%B4">제목</a>'
            '<a href="../guide?from=index#setup">설치</a>'
            '<a href="../">홈</a>',
        )
        self.write("guide.html", '<h2 id="setup">설치</h2>')
        self.assertEqual(check_site(self.root), [])

    def test_missing_page_and_anchor_are_reported(self):
        self.write(
            "index.html",
            '<a href="development/README.html">개발</a>'
            '<a href="development/#missing">제목</a>',
        )
        errors = check_site(self.root)
        self.assertEqual(len(errors), 2)
        self.assertTrue(
            any("README.html: missing local file" in error for error in errors)
        )
        self.assertTrue(
            any("missing HTML anchor #missing" in error for error in errors)
        )

    def test_root_paths_and_encoded_traversal_cannot_escape_project_base(self):
        self.write(
            "index.html",
            '<a href="/development/">잘못된 기본 경로</a>'
            '<a href="/sku-dreamon/%2e%2e/other.html">범위 밖</a>',
        )
        errors = check_site(self.root)
        self.assertEqual(len(errors), 2)
        self.assertTrue(
            all("outside site base /sku-dreamon/" in error for error in errors)
        )

    def test_missing_scripts_styles_and_images_are_reported(self):
        self.write(
            "index.html",
            '<script src="/sku-dreamon/assets/app.js"></script>'
            '<link rel="stylesheet" href="/sku-dreamon/assets/theme.css">'
            '<img src="/sku-dreamon/logo.svg">',
        )
        self.write("assets/app.js", "console.log('loaded');")
        errors = check_site(self.root)
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("theme.css" in error for error in errors))
        self.assertTrue(any("logo.svg" in error for error in errors))

    def test_external_and_embedded_resources_are_not_fetched(self):
        self.write(
            "index.html",
            '<a href="https://github.com/wejo-team/sku-dreamon/blob/main/README.md">소스</a>'
            '<a href="//example.com/guide#unknown">외부</a>'
            '<a href="mailto:team@example.com">메일</a>'
            '<img src="data:image/svg+xml;base64,PHN2Zy8+">',
        )
        self.assertEqual(check_site(self.root), [])

    def test_missing_build_is_not_reported_as_success(self):
        errors = check_site(self.root / "missing-build")
        self.assertEqual(len(errors), 1)
        self.assertIn("missing site entry point", errors[0])


if __name__ == "__main__":
    unittest.main()
