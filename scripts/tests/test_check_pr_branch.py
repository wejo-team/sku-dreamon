import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_pr_branch import validate_branch_policy

SCRIPT = Path(__file__).resolve().parents[1] / "check_pr_branch.py"


def pull_request(base, head, *, base_repository=1, head_repository=1):
    return {
        "base": {"ref": base, "repo": {"id": base_repository}},
        "head": {"ref": head, "repo": {"id": head_repository}},
    }


class PullRequestBranchTests(unittest.TestCase):
    def test_work_branches_target_develop_including_forks(self):
        for kind in ("feat", "fix", "refactor", "test", "docs", "chore", "ci"):
            for repository in (1, 2):
                with self.subTest(kind=kind, repository=repository):
                    validate_branch_policy(
                        pull_request(
                            "develop", f"{kind}/work-123", head_repository=repository
                        )
                    )

    def test_release_and_reverse_sync_require_the_same_repository(self):
        for base, head in (("main", "develop"), ("develop", "main")):
            with self.subTest(base=base, head=head):
                validate_branch_policy(pull_request(base, head))
                with self.assertRaises(ValueError):
                    validate_branch_policy(pull_request(base, head, head_repository=2))

    def test_delayed_sync_branch_can_target_develop(self):
        validate_branch_policy(pull_request("develop", "chore/sync-main-a1b2c3d"))

    def test_work_and_fork_branches_cannot_bypass_release_to_main(self):
        for head in ("feat/work", "fix/hotfix", "chore/release", "main", "Develop"):
            with self.subTest(head=head), self.assertRaises(ValueError):
                validate_branch_policy(pull_request("main", head))

    def test_other_bases_and_non_work_heads_are_rejected(self):
        for base, head in (
            ("release", "develop"),
            ("feat/base", "feat/work"),
            ("develop", "develop"),
            ("develop", "feature/work"),
            ("develop", "codex/work"),
            ("develop", "feat/Uppercase"),
            ("develop", "feat/nested/work"),
            ("develop", "feat/trailing-"),
            ("develop", "feat/work\n"),
        ):
            with self.subTest(base=base, head=head), self.assertRaises(ValueError):
                validate_branch_policy(pull_request(base, head))

    def test_missing_or_deleted_repository_metadata_fails_closed(self):
        for value in (None, {}, {"id": None}, {"id": "1"}, {"id": True}, {"id": 0}):
            for branch in ("base", "head"):
                event = pull_request("develop", "feat/work")
                event[branch]["repo"] = value
                with (
                    self.subTest(branch=branch, value=value),
                    self.assertRaises(ValueError),
                ):
                    validate_branch_policy(event)
        for event in (None, [], {}, {"base": None, "head": None}):
            with self.subTest(event=event), self.assertRaises(ValueError):
                validate_branch_policy(event)

    def run_event(self, event, directory):
        event_path = directory / "event.json"
        event_path.write_text(json.dumps(event), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=directory,
            env={**os.environ, "GITHUB_EVENT_PATH": str(event_path)},
            capture_output=True,
            text=True,
            check=False,
        )

    def test_cli_accepts_release_metadata_and_rejects_missing_payload(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            result = self.run_event(
                {"pull_request": pull_request("main", "develop")}, directory
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for event in ({}, [], {"pull_request": None}):
                with self.subTest(event=event):
                    result = self.run_event(event, directory)
                    self.assertEqual(result.returncode, 1)
                    self.assertIn("PR branch validation failed", result.stderr)

    def test_untrusted_ref_is_neither_executed_nor_logged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            head = "feat/$(touch marker)`touch another`"
            result = self.run_event(
                {"pull_request": pull_request("develop", head)}, directory
            )
            self.assertEqual(result.returncode, 1)
            self.assertNotIn(head, result.stdout + result.stderr)
            self.assertFalse((directory / "marker").exists())
            self.assertFalse((directory / "another").exists())


if __name__ == "__main__":
    unittest.main()
