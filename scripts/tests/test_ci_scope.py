import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.ci_scope import classify_paths

SCRIPT = Path(__file__).resolve().parents[1] / "ci_scope.py"
ALL = {"frontend", "backend", "docs"}


class ScopeRulesTests(unittest.TestCase):
    def test_directory_scope_and_common_file_rules(self):
        cases = [
            (["docs/specs/authentication.md"], {"docs"}),
            (
                ["design-reference/src/app/App.tsx", "design-reference/package-lock.json"],
                {"docs"},
            ),
            (
                ["design-reference/src/app/App.tsx", "frontend/src/app/App.tsx"],
                {"docs", "frontend"},
            ),
            (
                ["design-reference/public/favicon.svg", "backend/app/core/config.py"],
                {"docs", "backend"},
            ),
            (["design-reference-extra/shared.ts"], ALL),
            (["docs/.vitepress/config.ts", "package-lock.json"], {"docs"}),
            (["README.md", "AGENTS.md", ".nvmrc", "package.json"], {"docs"}),
            (
                ["scripts/check_docs.py", "scripts/tests/test_check_docs_site.py"],
                {"docs"},
            ),
            (["frontend/package-lock.json", "frontend/src/app/App.tsx"], {"frontend"}),
            (["backend/uv.lock", "backend/app/core/config.py"], {"backend"}),
            (["backend/app/api/health.py"], {"backend"}),
            (["backend/app/schemas/account.py"], {"backend"}),
            (["backend/app/main.py"], {"backend"}),
            (["frontend/src/lib/api.ts"], {"frontend"}),
            (["frontend/src/features/teams/api.ts"], {"frontend"}),
            (["frontend/src/features/teams/api/client.ts"], {"frontend"}),
            (["frontend/src/features/teams/types.ts"], {"frontend"}),
            (
                ["frontend/src/features/teams/response.schema.ts"],
                {"frontend"},
            ),
            (
                ["frontend/src/features/teams/contracts/index.ts"],
                {"frontend"},
            ),
            (["docs/README.md", "frontend/src/Button.tsx"], {"frontend", "docs"}),
            (
                ["backend/app/core/config.py", "frontend/src/Button.tsx"],
                {"frontend", "backend"},
            ),
            ([".github/workflows/ci.yml"], ALL),
            ([".gitignore"], ALL),
            (["scripts/ci_scope.py"], ALL),
            (["scripts/tests/test_ci_scope.py"], ALL),
            (["new-shared-directory/contract.json"], ALL),
            ([], ALL),
        ]
        for paths, expected in cases:
            with self.subTest(paths=paths):
                self.assertEqual(classify_paths(paths), expected)


class ScopeGitIntegrationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.repository = self.directory / "repository"
        self.repository.mkdir()
        self.output = self.directory / "output"
        self.summary = self.directory / "summary"
        self.event_file = self.directory / "event.json"
        self.git("init", "--initial-branch=main")
        self.git("config", "user.name", "CI test")
        self.git("config", "user.email", "ci-test@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.write_file("README.md", "Initial repository\n")
        self.base = self.commit()

    def git(self, *arguments):
        return subprocess.run(
            ["git", *arguments],
            cwd=self.repository,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()

    def write_file(self, path, content="example\n"):
        target = self.repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "--quiet", "--message=test change")
        return self.git("rev-parse", "HEAD")

    def run_scope(
        self,
        *,
        event_name="pull_request",
        event=None,
        ref="refs/heads/main",
        raw_event=None,
        overrides=None,
    ):
        if event is None:
            event = {
                "pull_request": {
                    "base": {"sha": self.base},
                    "head": {"sha": self.git("rev-parse", "HEAD")},
                }
            }
        self.event_file.write_text(
            json.dumps(event) if raw_event is None else raw_event, encoding="utf-8"
        )
        self.output.write_text("", encoding="utf-8")
        self.summary.write_text("", encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=self.repository,
            env={
                **os.environ,
                "GITHUB_EVENT_NAME": event_name,
                "GITHUB_EVENT_PATH": str(self.event_file),
                "GITHUB_REF": ref,
                "GITHUB_OUTPUT": str(self.output),
                "GITHUB_STEP_SUMMARY": str(self.summary),
                **(overrides or {}),
            },
            text=True,
            capture_output=True,
            check=False,
        )

    def assert_success(self, result, expected):
        self.assertEqual(result.returncode, 0, result.stderr)
        actual = dict(
            line.split("=", 1) for line in self.output.read_text().splitlines()
        )
        self.assertEqual(
            actual,
            {area: str(area in expected).lower() for area in ALL},
        )

    def assert_failed(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_text(), "")
        self.assertEqual(self.summary.read_text(), "")
        self.assertNotIn("=true", result.stdout)

    def test_pr_includes_earlier_commits_and_ignores_later_base_commits(self):
        self.git("checkout", "-b", "feature")
        self.write_file("frontend/src/Button.tsx")
        self.commit()
        self.write_file("docs/specs/login.md")
        head = self.commit()
        self.git("checkout", "main")
        self.write_file("backend/app/core/config.py")
        self.base = self.commit()
        self.git("checkout", "feature")
        self.assertEqual(head, self.git("rev-parse", "HEAD"))
        self.assert_success(self.run_scope(), {"frontend", "docs"})

    def test_cross_area_rename_includes_deleted_path(self):
        self.write_file("backend/app/core/note.md", "unique text\n" * 20)
        self.base = self.commit()
        (self.repository / "docs").mkdir()
        self.git("mv", "backend/app/core/note.md", "docs/note.md")
        self.commit()
        self.assert_success(self.run_scope(), {"backend", "docs"})

    def test_move_from_product_to_reference_keeps_product_check(self):
        self.write_file("frontend/src/Example.tsx", "unique reference text\n" * 20)
        self.base = self.commit()
        (self.repository / "design-reference").mkdir()
        self.git("mv", "frontend/src/Example.tsx", "design-reference/Example.tsx")
        self.commit()
        self.assert_success(self.run_scope(), {"frontend", "docs"})

    def test_backend_schema_deletion_selects_only_backend(self):
        self.write_file("backend/app/schemas/user.py")
        self.base = self.commit()
        (self.repository / "backend/app/schemas/user.py").unlink()
        self.commit()
        self.assert_success(self.run_scope(), {"backend"})

    def test_unusual_filenames_are_data_and_never_enter_logs_or_summary(self):
        path = "docs/한글\nfrontend=attack $(touch marker) `touch another` |.md"
        self.write_file(path)
        self.commit()
        result = self.run_scope()
        self.assert_success(result, {"docs"})
        self.assertNotIn(path, result.stdout + result.stderr + self.summary.read_text())
        self.assertFalse((self.repository / "marker").exists())
        self.assertFalse((self.repository / "another").exists())

    def test_empty_diff_runs_all(self):
        self.assert_success(self.run_scope(), ALL)

    def test_main_push_and_manual_run_need_no_pr_payload(self):
        for event, ref in [
            ("push", "refs/heads/main"),
            ("workflow_dispatch", "refs/heads/feature"),
        ]:
            with self.subTest(event=event):
                self.assert_success(
                    self.run_scope(event_name=event, event={}, ref=ref), ALL
                )

    def test_unsupported_event_or_non_main_push_fails_without_outputs(self):
        for event, ref in [
            ("pull_request_target", "refs/heads/main"),
            ("push", "refs/heads/feature"),
            ("", ""),
        ]:
            with self.subTest(event=event):
                self.assert_failed(self.run_scope(event_name=event, ref=ref))

    def test_missing_or_malformed_payload_fails_without_outputs(self):
        events = [
            {},
            [],
            {"pull_request": {}},
            {"pull_request": {"base": None, "head": {"sha": self.base}}},
            {"pull_request": {"base": {"sha": 123}, "head": {"sha": self.base}}},
            {
                "pull_request": {
                    "base": {"sha": "$(touch marker)"},
                    "head": {"sha": self.base},
                }
            },
        ]
        for event in events:
            with self.subTest(event=event):
                self.assert_failed(self.run_scope(event=event))
        self.assertFalse((self.repository / "marker").exists())

    def test_missing_git_commit_fails_without_outputs(self):
        event = {
            "pull_request": {"base": {"sha": "f" * 40}, "head": {"sha": self.base}}
        }
        self.assert_failed(self.run_scope(event=event))

    def test_invalid_json_fails_without_outputs(self):
        for raw_event in ["{", "null", '"unexpected string"']:
            with self.subTest(raw_event=raw_event):
                self.assert_failed(self.run_scope(raw_event=raw_event))

    def test_missing_event_file_fails_without_outputs(self):
        for event_path in ["", str(self.directory / "missing-event.json")]:
            with self.subTest(event_path=event_path):
                self.assert_failed(
                    self.run_scope(overrides={"GITHUB_EVENT_PATH": event_path})
                )

    def test_unrelated_histories_fail_without_outputs(self):
        self.git("checkout", "--orphan", "unrelated")
        self.git("rm", "-rf", ".")
        self.write_file("docs/new.md")
        self.commit()
        self.assert_failed(self.run_scope())


if __name__ == "__main__":
    unittest.main()
