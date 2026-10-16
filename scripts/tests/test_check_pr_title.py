import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_pr_title import validate_title


SCRIPT = Path(__file__).resolve().parents[1] / "check_pr_title.py"


class PullRequestTitleTests(unittest.TestCase):
    def test_supported_types_optional_scope_and_korean_subject(self):
        titles = [
            "feat(frontend): 모집글 작성 폼 추가",
            "fix: 연결 오류 수정",
            "refactor(backend): simplify session cleanup",
            "test(api): cover cancellation",
            "docs: 개발 가이드 정리",
            "chore(deps): update locked dependencies",
            "ci: validate PR titles",
            "fix:설명은 비어 있지 않아야 함",
        ]
        for title in titles:
            with self.subTest(title=title):
                validate_title(title)

    def test_rejects_invalid_types_empty_fields_and_multiline_titles(self):
        titles = [
            "",
            "build: add a script",
            "Feat: add a page",
            "fix missing separator",
            "fix(): add a page",
            "fix(   ): add a page",
            "fix(api):",
            "fix:   ",
            "fix: first line\nsecond line",
            "fix: trailing newline\n",
            "fix: carriage return\r",
            "fix(api\n): line break in scope",
        ]
        for title in titles:
            with self.subTest(title=title):
                with self.assertRaises(ValueError):
                    validate_title(title)

    def run_event(self, event, directory):
        event_path = directory / "event.json"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=directory,
            env={**os.environ, "GITHUB_EVENT_PATH": str(event_path)},
            text=True,
            capture_output=True,
            check=False,
        )

    def test_edited_event_validates_current_title_instead_of_previous_title(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for previous, current, expected_code in [
                ("invalid title", "fix: 제목 형식 수정", 0),
                ("fix: valid title", "invalid title", 1),
            ]:
                with self.subTest(current=current):
                    result = self.run_event(
                        {
                            "action": "edited",
                            "pull_request": {"title": current},
                            "changes": {"title": {"from": previous}},
                        },
                        directory,
                    )
                    self.assertEqual(result.returncode, expected_code, result.stderr)

    def test_shell_syntax_in_title_is_only_data(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            title = 'fix: $(touch dollar-marker) `touch backtick-marker`; "quoted"'
            result = self.run_event({"pull_request": {"title": title}}, directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((directory / "dollar-marker").exists())
            self.assertFalse((directory / "backtick-marker").exists())
            self.assertNotIn(title, result.stdout + result.stderr)

    def test_missing_or_non_string_title_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for event in [{}, {"pull_request": {}}, {"pull_request": {"title": None}}]:
                with self.subTest(event=event):
                    result = self.run_event(event, directory)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("PR title validation failed", result.stderr)


if __name__ == "__main__":
    unittest.main()
