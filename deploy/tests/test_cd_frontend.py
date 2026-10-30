"""CLI 경계의 버전별 객체 저장소로 게시·부분 실패·복구 동작을 검증한다."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit

DEPLOY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(DEPLOY))

import cd_frontend as cd  # noqa: E402

SHA = "b" * 40
BUCKET = "synthetic-frontend"
SITE = "https://app.example.invalid"
API = "https://api.example.invalid/api/v1"
MAIN = "assets/index-new.js"


class Store:
    def __init__(self) -> None:
        self.objects: dict[str, dict] = {}
        self.versions: dict[tuple[str, str], dict] = {}
        self.calls: list[tuple[str, ...]] = []
        self.mutations: list[tuple[str, str]] = []
        self.counter = 0
        self.fail_put: str | None = None
        self.fail_after_commit = False
        self.copy_failure = False
        self.corrupt_copy: str | None = None
        self.restore_failure: str | None = None
        self.site_failure = False
        self.spa_errors = False
        self.invalidation_failure = False
        self.pages = False

    def seed(self, key: str, body: bytes, **metadata) -> None:
        self.counter += 1
        version = "version/" + str(self.counter) + "+old"
        record = {
            "body": body,
            "metadata": {
                "ContentType": "application/octet-stream",
                "CacheControl": cd.MUTABLE,
                **metadata,
                "VersionId": version,
            },
        }
        self.objects[key] = record
        self.versions[key, version] = copy.deepcopy(record)

    def aws(self, *args: str, **kwargs) -> dict:
        self.calls.append(args)
        operation = args[1]

        def option(flag: str) -> str:
            return args[args.index(flag) + 1]

        if operation == "list-objects-v2":
            keys = sorted(self.objects)
            if self.pages:
                offset = (
                    int(option("--continuation-token"))
                    if "--continuation-token" in args
                    else 0
                )
                end = min(len(keys), offset + 2)
                return {
                    "Contents": [{"Key": k} for k in keys[offset:end]],
                    "IsTruncated": end < len(keys),
                    "NextContinuationToken": str(end),
                }
            return {"Contents": [{"Key": k} for k in keys]}
        if operation == "get-object":
            record = self.objects[option("--key")]
            Path(args[-1]).write_bytes(record["body"])
            return copy.deepcopy(record["metadata"])
        if operation == "put-object":
            data = json.loads(option("--cli-input-json"))
            key = data.pop("Key")
            data.pop("Bucket")
            self.mutations.append(("put", key))
            if "--if-none-match" in args and key in self.objects:
                raise cd.PublicationError("conditional put failed")
            failing = self.fail_put == key
            if failing:
                self.fail_put = None
            if (
                self.restore_failure == key
                and data.get("Metadata", {}).get("release-sha") != SHA
            ):
                raise cd.PublicationError("restore upload failed")
            if not failing or self.fail_after_commit:
                self.seed(key, Path(option("--body")).read_bytes(), **data)
            if failing:
                raise cd.PublicationError("put response lost")
            return {"VersionId": self.objects[key]["metadata"]["VersionId"]}
        if operation == "copy-object":
            key = option("--key")
            self.mutations.append(("copy", key))
            if self.copy_failure or self.restore_failure == key:
                raise cd.PublicationError("version copy failed")
            source, version = option("--copy-source").split("?versionId=", 1)
            source_key = unquote(source).split("/", 1)[1]
            record = self.versions[source_key, unquote(version)]
            metadata = {k: v for k, v in record["metadata"].items() if k != "VersionId"}
            self.seed(
                key,
                b"corrupt" if key == self.corrupt_copy else record["body"],
                **metadata,
            )
            return {"VersionId": self.objects[key]["metadata"]["VersionId"]}
        if operation == "delete-object":
            key = option("--key")
            self.mutations.append(("delete", key))
            self.objects.pop(key, None)
            return {}
        if operation == "create-invalidation":
            self.mutations.append(("invalidate", option("--paths")))
            return {"Invalidation": {"Id": "INVALIDATION", "Status": "InProgress"}}
        if operation == "get-invalidation":
            if self.invalidation_failure:
                self.invalidation_failure = False
                raise cd.PublicationError("invalidation failed")
            return {"Invalidation": {"Status": "Completed"}}
        raise AssertionError(operation)

    def http(self, url: str, accept: str) -> tuple[int, dict[str, str], bytes]:
        path = urlsplit(url).path.lstrip("/")
        if self.site_failure:
            self.site_failure = False
            return (
                200,
                {"content-type": "text/html", "cache-control": "no-cache"},
                b"stale index",
            )
        if path == "profile" and accept == "text/html":
            path = "index.html"
        if self.spa_errors and path not in self.objects:
            path = "index.html"
        if path not in self.objects:
            return 403, {"content-type": "application/xml"}, b"AccessDenied"
        record = self.objects[path]
        return (
            200,
            {
                "content-type": record["metadata"].get("ContentType", ""),
                "cache-control": record["metadata"].get("CacheControl", ""),
            },
            record["body"],
        )


class PublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.dist = self.root / "dist"
        (self.dist / "assets").mkdir(parents=True)
        (self.dist / "index.html").write_text(
            f'<script type="module" src="/{MAIN}"></script>new'
        )
        (self.dist / MAIN).write_text(
            f'const api="{API}";function send(e,t){{return fetch(e,t)}}'
        )
        (self.dist / "assets/style-new.css").write_text("body{color:green}")
        (self.dist / "favicon.ico").write_bytes(b"new favicon")
        (self.dist / "new-public.txt").write_text("new mutable")
        self.store = Store()
        self.store.seed(
            "index.html",
            b"old HTML",
            ContentType="text/html; charset=utf-8",
            CacheControl="no-cache",
            Metadata={"release-sha": "a" * 40},
        )
        self.store.seed(
            "favicon.ico",
            b"old icon",
            ContentType="image/x-icon",
            ContentDisposition="inline",
            ContentLanguage="ko",
            ContentEncoding="identity",
            Expires="2030-01-01T00:00:00Z",
            WebsiteRedirectLocation="/icon",
            Metadata={"custom": "retained"},
            ServerSideEncryption="AES256",
        )
        self.store.seed(
            "manifest.webmanifest",
            b"old manifest",
            ContentType="application/manifest+json",
        )
        self.store.seed("assets/old.js", b"old immutable", CacheControl=cd.IMMUTABLE)
        self.before = copy.deepcopy(self.store.objects)
        self.addCleanup(patch.stopall)
        patch.object(cd, "_aws", self.store.aws).start()
        patch.object(cd, "_http", self.store.http).start()

    def publish(self) -> dict:
        return cd.publish(
            self.dist, SHA, BUCKET, "DISTRIBUTION1", SITE, API, self.root / "state"
        )

    def receipt(self) -> dict:
        return json.loads(
            next((self.root / "state").glob("*/receipt.json")).read_text()
        )

    def assert_restored(self) -> None:
        for key, old in self.before.items():
            current = self.store.objects[key]
            self.assertEqual(current["body"], old["body"], key)
            self.assertEqual(
                {k: v for k, v in current["metadata"].items() if k != "VersionId"},
                {k: v for k, v in old["metadata"].items() if k != "VersionId"},
                key,
            )
        self.assertNotIn("new-public.txt", self.store.objects)

    def test_success_snapshots_all_mutable_keys_and_publishes_html_last(self) -> None:
        self.store.pages = True
        result = self.publish()
        self.assertEqual(result["release_sha"], SHA)
        self.assertEqual(result["smoke"]["checks"], 6)
        puts = [key for operation, key in self.store.mutations if operation == "put"]
        self.assertEqual(puts[:2], sorted([MAIN, "assets/style-new.css"]))
        self.assertEqual(puts[-1], "index.html")
        self.assertEqual(
            self.store.objects["index.html"]["metadata"]["Metadata"],
            {"release-sha": SHA},
        )
        self.assertEqual(
            self.store.objects[MAIN]["metadata"]["CacheControl"], cd.IMMUTABLE
        )
        snapshot = json.loads((Path(result["state_dir"]) / "snapshot.json").read_text())
        self.assertEqual(
            set(snapshot["objects"]),
            {"index.html", "favicon.ico", "manifest.webmanifest"},
        )
        self.assertEqual(snapshot["new_mutable"], ["new-public.txt"])
        self.assertIn("assets/old.js", self.store.objects)
        self.assertFalse(any(op == "delete" for op, _ in self.store.mutations))
        self.assertEqual(self.store.mutations[-1], ("invalidate", "/*"))

    def test_repeated_release_does_not_rewrite_existing_immutable_versions(
        self,
    ) -> None:
        self.publish()
        version = self.store.objects[MAIN]["metadata"]["VersionId"]
        self.store.mutations.clear()
        second = self.publish()
        self.assertEqual(self.store.objects[MAIN]["metadata"]["VersionId"], version)
        self.assertNotIn(("put", MAIN), self.store.mutations)
        self.assertEqual(len(list((self.root / "state").iterdir())), 2)
        self.assertEqual(second["status"], "published")

    def test_immutable_collision_rejected_before_any_mutation(self) -> None:
        self.store.seed(MAIN, b"different content", CacheControl=cd.IMMUTABLE)
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(self.store.mutations, [])
        self.assertEqual(self.store.objects["index.html"], self.before["index.html"])

    def test_partial_asset_upload_needs_no_mutable_rollback(self) -> None:
        self.store.fail_put = "assets/style-new.css"
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(self.store.objects["index.html"], self.before["index.html"])
        self.assertEqual(self.receipt()["rollback"]["status"], "not-needed")
        self.assertIn(MAIN, self.store.objects)
        self.assertFalse(
            any(
                op in ("copy", "delete", "invalidate") for op, _ in self.store.mutations
            )
        )

    def test_journal_failure_before_first_mutable_put_needs_no_rollback(self) -> None:
        original_save = cd._save
        failed = False

        def save(path, value):
            nonlocal failed
            if not failed and value.get("attempted_mutable"):
                failed = True
                raise OSError("disk full")
            original_save(path, value)

        with patch.object(cd, "_save", side_effect=save):
            with self.assertRaises(cd.PublicationError) as raised:
                self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(self.store.objects["index.html"], self.before["index.html"])
        self.assertFalse(
            any(
                op in ("copy", "delete", "invalidate") for op, _ in self.store.mutations
            )
        )

    def test_partial_mutable_put_restores_index_first_and_all_old_metadata(
        self,
    ) -> None:
        self.store.fail_put = "favicon.ico"
        self.store.fail_after_commit = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()
        copies = [key for op, key in self.store.mutations if op == "copy"]
        self.assertEqual(copies[0], "index.html")
        self.assertEqual(
            set(copies), {"index.html", "favicon.ico", "manifest.webmanifest"}
        )
        self.assertIn(MAIN, self.store.objects)

    def test_smoke_failure_restores_versions_and_deletes_only_new_mutable_keys(
        self,
    ) -> None:
        self.store.site_failure = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()
        self.assertEqual(
            [key for op, key in self.store.mutations if op == "delete"],
            ["new-public.txt"],
        )
        self.assertEqual(
            [key for op, key in self.store.mutations if op == "invalidate"],
            ["/*", "/*"],
        )
        self.assertEqual(self.receipt()["rollback"]["status"], "restored")
        self.assertIn(MAIN, self.store.objects)

    def test_index_put_response_lost_is_restored_and_new_objects_removed(self) -> None:
        self.store.fail_put = "index.html"
        self.store.fail_after_commit = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()
        self.assertEqual(
            next((op, key) for op, key in self.store.mutations if op == "copy"),
            ("copy", "index.html"),
        )

    def test_old_version_unavailable_uses_snapshot_bytes_and_headers(self) -> None:
        self.store.copy_failure = True
        self.store.site_failure = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()
        self.assertEqual(
            sum(
                op == "put" and key == "index.html" for op, key in self.store.mutations
            ),
            2,
        )

    def test_unversioned_old_index_uses_body_snapshot(self) -> None:
        self.store.objects["index.html"]["metadata"]["VersionId"] = "null"
        self.before = copy.deepcopy(self.store.objects)
        self.store.site_failure = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()
        self.assertNotIn(("copy", "index.html"), self.store.mutations)

    def test_first_deploy_failure_removes_new_index_before_other_mutable_keys(
        self,
    ) -> None:
        self.store.objects.clear()
        self.store.site_failure = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        deletes = [key for op, key in self.store.mutations if op == "delete"]
        self.assertEqual(deletes[0], "index.html")
        self.assertEqual(set(deletes), {"index.html", "favicon.ico", "new-public.txt"})
        self.assertTrue(all(key.startswith("assets/") for key in self.store.objects))

    def test_invalidation_failure_also_restores_published_html(self) -> None:
        self.store.invalidation_failure = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()

    def test_failed_rollback_preserves_evidence_and_reports_false(self) -> None:
        self.store.site_failure = True
        self.store.restore_failure = "index.html"
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertFalse(raised.exception.rollback_succeeded)
        self.assertEqual(self.receipt()["rollback"]["status"], "failed")
        self.assertIn(("copy", "favicon.ico"), self.store.mutations)
        self.assertEqual(self.store.mutations[-1], ("invalidate", "/*"))

    def test_successful_copy_response_with_wrong_bytes_is_not_verified_rollback(
        self,
    ) -> None:
        self.store.site_failure = True
        self.store.corrupt_copy = "favicon.ico"
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertFalse(raised.exception.rollback_succeeded)
        self.assertIn(
            "restore failed: favicon.ico", self.receipt()["rollback"]["errors"]
        )

    def test_spa_error_rewrite_fails_smoke_and_rolls_back(self) -> None:
        self.store.spa_errors = True
        with self.assertRaises(cd.PublicationError) as raised:
            self.publish()
        self.assertTrue(raised.exception.rollback_succeeded)
        self.assert_restored()

    def test_wrong_api_or_mock_bundle_rejected_without_aws_writes(self) -> None:
        for bundle in (
            '"https://other.example.invalid";function f(a,b){return fetch(a,b)}',
            f'"{API}0";function f(a,b){{return fetch(a,b)}}',
            f'"{API}";function f(a,b){{return fetch(a,b)}};import("api-mock-abc.js")',
        ):
            with self.subTest(bundle=bundle):
                (self.dist / MAIN).write_text(bundle)
                with self.assertRaises(cd.PublicationError) as raised:
                    self.publish()
                self.assertTrue(raised.exception.rollback_succeeded)
        self.assertEqual(self.store.mutations, [])

    def test_symlinks_and_non_https_sites_rejected_before_writes(self) -> None:
        alias = self.root / "alias"
        alias.symlink_to(self.dist)
        with self.assertRaises(cd.PublicationError):
            cd.publish(
                alias, SHA, BUCKET, "DISTRIBUTION1", SITE, API, self.root / "state"
            )
        with self.assertRaises(cd.PublicationError):
            cd.publish(
                self.dist,
                SHA,
                BUCKET,
                "DISTRIBUTION1",
                "http://example.invalid",
                API,
                self.root / "state",
            )
        self.assertEqual(self.store.mutations, [])


class BoundaryTests(unittest.TestCase):
    def test_invalidation_wait_has_deadline_and_only_one_wildcard(self) -> None:
        with (
            patch.object(
                cd,
                "_aws",
                side_effect=[
                    {"Invalidation": {"Id": "ONE"}},
                    {"Invalidation": {"Status": "InProgress"}},
                ],
            ) as aws,
            patch.object(cd.time, "monotonic", side_effect=[0, 0, 300, 300]),
            patch.object(cd.time, "sleep"),
        ):
            with self.assertRaisesRegex(cd.PublicationError, "timed out"):
                cd._invalidate("DISTRIBUTION1")
        self.assertEqual(aws.call_args_list[0].args[-2:], ("--paths", "/*"))
        self.assertEqual(aws.call_count, 2)

    def test_cli_failure_does_not_include_credentials_or_stderr(self) -> None:
        secret = "synthetic-sensitive-value"
        with patch.object(
            cd.subprocess,
            "run",
            side_effect=subprocess.CalledProcessError(1, "aws", stderr=secret),
        ):
            with self.assertRaises(cd.PublicationError) as raised:
                cd._aws("s3api", "put-object")
        self.assertNotIn(secret, str(raised.exception))

    def test_https_redirect_cannot_downgrade(self) -> None:
        with self.assertRaises(cd.PublicationError):
            cd._HTTPSRedirect().redirect_request(
                None, None, 301, "", {}, "http://example.invalid"
            )


if __name__ == "__main__":
    unittest.main()
