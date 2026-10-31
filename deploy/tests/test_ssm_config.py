"""SSM 버전 고정·설정 검증·비밀값 비출력 경계를 합성 응답으로 확인한다."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

from cd_release import CDError, trusted  # noqa: E402 -- 독립 배포 도구 경로를 등록한다.
from config import ReleaseError  # noqa: E402
from ssm_config import MAX_VERSION, Source, SourceError  # noqa: E402

NAME = "/sku-dreamon/production/backend"
REGION = "ap-northeast-2"
PRIVATE = "synthetic-private-key-never-log"
ENVIRONMENT = {"APP_ENV": "production", "OPENAI_API_KEY": PRIVATE}


def response(*, version: int = 7, environment=None, **overrides) -> bytes:
    parameter = {
        "ARN": f"arn:aws:ssm:{REGION}:123456789012:parameter{NAME}",
        "Name": NAME,
        "Version": version,
        "Selector": f":{version}",
        "Type": "SecureString",
        "DataType": "text",
        "Value": json.dumps(ENVIRONMENT if environment is None else environment),
        **overrides,
    }
    return json.dumps({"Parameter": parameter}).encode()


class SourceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = Source(REGION, NAME)

    def test_reads_one_explicit_version_without_passing_secrets_as_arguments(self):
        runner = Mock(return_value=response())
        snapshot = self.source.fetch(7, runner)
        self.assertEqual(snapshot.app_env, ENVIRONMENT)
        self.assertEqual(snapshot.metadata["parameter_version"], 7)
        self.assertEqual(snapshot.metadata["parameter_name"], NAME)
        self.assertTrue(snapshot.revision.startswith("ssm-7-"))
        arguments = runner.call_args.args[0]
        self.assertEqual(arguments[:3], ["aws", "ssm", "get-parameter"])
        self.assertEqual(arguments[arguments.index("--name") + 1], NAME + ":7")
        self.assertIn("--with-decryption", arguments)
        self.assertEqual(arguments[arguments.index("--region") + 1], REGION)
        self.assertEqual(runner.call_args.kwargs, {"timeout": 60})
        runner.assert_called_once()
        self.assertNotIn(PRIVATE, " ".join(arguments))
        self.assertNotIn(PRIVATE, repr(snapshot))

    def test_latest_pins_values_and_version_from_one_response(self):
        value = json.loads(response())
        del value["Parameter"]["Selector"]
        runner = Mock(return_value=json.dumps(value).encode())
        snapshot = self.source.fetch_latest(runner)
        self.assertEqual(snapshot.app_env, ENVIRONMENT)
        self.assertEqual(snapshot.metadata["parameter_version"], 7)
        self.assertEqual(
            snapshot.revision,
            self.source.fetch(7, Mock(return_value=response())).revision,
        )
        runner.assert_called_once()
        arguments = runner.call_args.args[0]
        self.assertEqual(arguments[arguments.index("--name") + 1], NAME)
        self.assertNotIn(PRIVATE, repr(snapshot))

    def test_latest_rejects_invalid_versions_and_unexpected_selectors(self):
        for version in (None, False, "7", 0, -1, MAX_VERSION + 1):
            value = json.loads(response())
            value["Parameter"]["Version"] = version
            del value["Parameter"]["Selector"]
            with (
                self.subTest(version=version),
                self.assertRaisesRegex(SourceError, "^ssm_response_invalid$"),
            ):
                self.source.fetch_latest(Mock(return_value=json.dumps(value).encode()))
        with self.assertRaisesRegex(SourceError, "^ssm_response_invalid$"):
            self.source.fetch_latest(Mock(return_value=response()))

    def test_revision_is_stable_for_key_order_and_changes_for_values_or_versions(self):
        first = self.source.fetch(7, Mock(return_value=response()))
        reordered = self.source.fetch(
            7,
            Mock(
                return_value=response(environment=dict(reversed(ENVIRONMENT.items())))
            ),
        )
        changed = self.source.fetch(
            7,
            Mock(
                return_value=response(
                    environment={**ENVIRONMENT, "AI_TIMEOUT_SECONDS": "30"}
                )
            ),
        )
        versioned = self.source.fetch(8, Mock(return_value=response(version=8)))
        self.assertEqual(first.revision, reordered.revision)
        self.assertNotEqual(first.revision, changed.revision)
        self.assertNotEqual(first.revision, versioned.revision)
        self.assertEqual(len(first.metadata["sha256"]), 64)

    def test_largest_supported_version_produces_a_valid_revision_length(self):
        snapshot = self.source.fetch(
            MAX_VERSION, Mock(return_value=response(version=MAX_VERSION))
        )
        self.assertLessEqual(len(snapshot.revision), 80)

    def test_invalid_or_unpinned_versions_never_call_aws(self):
        for version in (0, -1, "latest", "7", 1.0, True, None, MAX_VERSION + 1):
            with self.subTest(version=version):
                runner = Mock()
                with self.assertRaisesRegex(SourceError, "^ssm_version_invalid$"):
                    self.source.fetch(version, runner)
                runner.assert_not_called()

    def test_wrong_parameter_identity_and_plaintext_type_are_rejected(self):
        for overrides in (
            {"Name": NAME + "-other"},
            {"Version": 8},
            {"Version": True},
            {"Version": "7"},
            {"Selector": ":current"},
            {"Selector": ":8"},
            {"Type": "String"},
            {"Type": "StringList"},
            {"DataType": "aws:ec2:image"},
            {"ARN": f"arn:aws:ssm:us-east-1:123456789012:parameter{NAME}"},
            {"ARN": f"arn:aws:ssm:{REGION}:123456789012:parameter/other"},
            {"ARN": None},
        ):
            with self.subTest(overrides=overrides):
                with self.assertRaisesRegex(SourceError, "^ssm_response_invalid$"):
                    self.source.fetch(7, Mock(return_value=response(**overrides)))

    def test_missing_identity_fields_are_rejected(self):
        for name in ("Name", "Version", "Selector", "Type", "DataType", "ARN", "Value"):
            with self.subTest(name=name):
                value = json.loads(response())
                del value["Parameter"][name]
                with self.assertRaisesRegex(SourceError, "^ssm_response_invalid$"):
                    self.source.fetch(7, Mock(return_value=json.dumps(value).encode()))

    def test_malformed_or_oversized_responses_have_no_secret_in_errors(self):
        for output in (
            PRIVATE.encode(),
            b"[]",
            b"{}",
            b'{"Parameter":null}',
            b'{"Parameter":{},"Parameter":{}}',
            b'{"Parameter":NaN}',
            b"\xff",
            b" " * 65537,
            response(Value=PRIVATE * 8192),
            response(Value=123),
            response(Value=""),
            response(Value="\ud800"),
        ):
            with self.subTest(output_length=len(output)):
                with self.assertRaisesRegex(
                    SourceError, "^ssm_response_invalid$"
                ) as error:
                    self.source.fetch(7, Mock(return_value=output))
                self.assertNotIn(PRIVATE, str(error.exception))

    def test_invalid_settings_cannot_become_environment_variables(self):
        for contents in (
            "[]",
            "{}",
            PRIVATE,
            '{"OPENAI_API_KEY":"first","OPENAI_API_KEY":"second"}',
            json.dumps({"UNKNOWN_SETTING": PRIVATE}),
            json.dumps({"AI_TIMEOUT_SECONDS": 90}),
            json.dumps({"OPENAI_API_KEY": None}),
            json.dumps({"OPENAI_API_KEY": [PRIVATE]}),
            json.dumps({"OPENAI_API_KEY": PRIVATE + "\nINJECTED=true"}),
            json.dumps({"OPENAI_API_KEY": PRIVATE + "\rINJECTED=true"}),
            json.dumps({"OPENAI_API_KEY": PRIVATE + "\0"}),
            '{"OPENAI_API_KEY":NaN}',
            '{"OPENAI_API_KEY":"\\ud800"}',
        ):
            with self.subTest(contents_length=len(contents)):
                with self.assertRaisesRegex(
                    SourceError, "^ssm_settings_invalid$"
                ) as error:
                    self.source.fetch(7, Mock(return_value=response(Value=contents)))
                self.assertNotIn(PRIVATE, str(error.exception))

    def test_empty_optional_secret_and_literal_shell_characters_are_preserved(self):
        value = {
            "APP_ENV": "production",
            "OPENAI_API_KEY": "",
            "DATABASE_URL": "literal-$()-backtick-`-quote-'",
        }
        snapshot = self.source.fetch(7, Mock(return_value=response(environment=value)))
        self.assertEqual(snapshot.app_env, value)

    def test_read_failure_never_falls_back_and_suppresses_provider_error(self):
        for failure in (
            RuntimeError(PRIVATE),
            subprocess.CalledProcessError(1, ["aws", PRIVATE], stderr=PRIVATE),
            subprocess.TimeoutExpired(["aws", PRIVATE], 60),
        ):
            with self.subTest(failure_type=type(failure).__name__):
                runner = Mock(side_effect=failure)
                try:
                    self.source.fetch(7, runner)
                except SourceError as error:
                    self.assertEqual(str(error), "ssm_read_failed")
                    rendered = "".join(traceback.format_exception(error))
                    self.assertNotIn(PRIVATE, rendered)
                else:
                    self.fail("failed fetch must fail")
                runner.assert_called_once()

    def test_source_rejects_request_overrides_or_unsafe_names(self):
        for region, name in (
            (REGION, NAME + ":7"),
            (REGION, NAME + " "),
            (REGION, "--endpoint-url"),
            (REGION, "plain-name"),
            (REGION, "/a//b"),
            (REGION, "/aws/private"),
            (REGION, "/SSM/private"),
            (REGION, "/" + "a" * 1011),
            (REGION, "/a" * 16),
            (REGION, None),
            ("--endpoint-url", NAME),
            (REGION + "\n", NAME),
            (None, NAME),
        ):
            with self.subTest(region=region, name=name):
                with self.assertRaisesRegex(SourceError, "^ssm_source_invalid$"):
                    Source(region, name)

    def test_source_file_requires_exact_fields_and_private_direct_file(self):
        def private_for_test(target):
            # root 검사는 실행기에 맡기고 동일 사용자·권한·링크 검사는 유지한다.
            try:
                trusted(target, private=True)
            except CDError:
                raise ReleaseError("unsafe fixture path") from None

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "source.json"
            path.write_text(json.dumps({"region": REGION, "parameter_name": NAME}))
            path.chmod(0o600)
            with patch(
                "ssm_config.private_path",
                side_effect=private_for_test,
            ):
                self.assertEqual(Source.read(path), self.source)
                path.chmod(0o644)
                with self.assertRaises(SourceError):
                    Source.read(path)
                path.chmod(0o600)
                link = path.with_name("link.json")
                link.symlink_to(path)
                with self.assertRaises(SourceError):
                    Source.read(link)
                for contents in (
                    json.dumps(
                        {"region": REGION, "parameter_name": NAME, "profile": "other"}
                    ),
                    '{"region":"ap-northeast-2","region":"us-east-1","parameter_name":"/x"}',
                    "[]",
                    PRIVATE,
                    " " * 4097,
                ):
                    path.write_text(contents)
                    with self.assertRaisesRegex(SourceError, "^ssm_source_invalid$"):
                        Source.read(path)


if __name__ == "__main__":
    unittest.main()
