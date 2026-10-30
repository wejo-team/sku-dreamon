"""빌드된 SPA를 게시하고 비공개 스냅샷으로 변경 가능한 S3 객체를 복구한다.

호출자가 버킷의 동시 배포를 막고 백엔드 롤백을 담당한다. 불변 자산은 성공·실패
모두 보존하며 인증 정보는 저장하지 않는다. AWS CLI 계약의 근거:
https://docs.aws.amazon.com/cli/latest/reference/s3api/copy-object.html
https://docs.aws.amazon.com/cli/latest/reference/cloudfront/get-invalidation.html
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import subprocess
import tempfile
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

IMMUTABLE = "public,max-age=31536000,immutable"
MUTABLE = "public,max-age=300,must-revalidate"
AWS_TIMEOUT = 60
INVALIDATION_TIMEOUT = 300
POLL_INTERVAL = 5
RESTORE_FIELDS = (
    "Metadata",
    "ContentType",
    "CacheControl",
    "ContentEncoding",
    "ContentDisposition",
    "ContentLanguage",
    "Expires",
    "WebsiteRedirectLocation",
    "StorageClass",
    "ServerSideEncryption",
    "SSEKMSKeyId",
    "BucketKeyEnabled",
)


class PublicationError(RuntimeError):
    """상위 배포 코드는 rollback_succeeded가 참일 때만 백엔드를 롤백할 수 있다."""

    def __init__(self, message: str, *, rollback_succeeded: bool = True) -> None:
        super().__init__(message)
        self.rollback_succeeded = rollback_succeeded


def _aws(*arguments: str, timeout: float = AWS_TIMEOUT) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [
                "aws",
                *arguments,
                "--output",
                "json",
                "--no-cli-pager",
                "--cli-connect-timeout",
                "10",
                "--cli-read-timeout",
                "30",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "AWS_PAGER": "", "AWS_CLI_AUTO_PROMPT": "off"},
        )
        return json.loads(result.stdout) if result.stdout.strip() else {}
    except (OSError, subprocess.SubprocessError, ValueError):
        raise PublicationError(f"AWS {' '.join(arguments[:2])} failed") from None


def _save(path: Path, value: object) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


class _Scripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("type") == "module":
            source = attributes.get("src")
            if source:
                self.sources.append(source)


def _https_url(value: str, *, origin: bool = False) -> str:
    parts = urlsplit(value)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.query
        or parts.fragment
        or (origin and parts.path not in ("", "/"))
    ):
        raise PublicationError("expected an HTTPS URL without credentials")
    return value.rstrip("/")


def _build(dist: Path, api_base_url: str) -> tuple[dict[str, Path], str]:
    if not dist.is_dir() or dist.is_symlink():
        raise PublicationError("dist must be a directory of built files")
    files: dict[str, Path] = {}
    for path in sorted(dist.rglob("*")):
        if path.is_symlink():
            raise PublicationError("symlinks are not accepted in dist")
        if path.is_file():
            files[path.relative_to(dist).as_posix()] = path
    if "index.html" not in files:
        raise PublicationError("dist/index.html is required")
    parser = _Scripts()
    parser.feed(files["index.html"].read_text())
    if len(parser.sources) != 1:
        raise PublicationError("expected one built module entry in index.html")
    source = urlsplit(parser.sources[0])
    main = source.path.removeprefix("/")
    if (
        source.scheme
        or source.netloc
        or source.query
        or source.fragment
        or not main.startswith("assets/")
        or main not in files
    ):
        raise PublicationError("module entry must be a local built asset")
    bundle = files[main].read_text()
    literal = re.search(r"([\"'`])" + re.escape(api_base_url) + r"/?\1", bundle)
    position = literal.start() if literal else -1
    # 현재 Vite 출력은 운영 API 문자열 뒤에 fetch를 직접 호출하는 함수를 둔다.
    direct_fetch = r"function\s+\w+\((\w+),(\w+)\)\{return fetch\(\1,\2\)\}"
    if (
        position < 0
        or "api-mock-" in bundle
        or not re.search(direct_fetch, bundle[position : position + 600])
    ):
        raise PublicationError(
            "bundle must use the configured API directly, without mocks"
        )
    return files, main


def _keys(bucket: str) -> set[str]:
    keys: set[str] = set()
    token = None
    seen: set[str] = set()
    while True:
        arguments = [
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--no-paginate",
            "--max-keys",
            "1000",
        ]
        if token:
            arguments.extend(("--continuation-token", token))
        page = _aws(*arguments)
        keys.update(item["Key"] for item in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")
        if not isinstance(token, str) or not token or token in seen:
            raise PublicationError("invalid S3 listing continuation")
        seen.add(token)


def _download(bucket: str, key: str, destination: Path) -> dict[str, Any]:
    metadata = _aws(
        "s3api", "get-object", "--bucket", bucket, "--key", key, str(destination)
    )
    destination.chmod(0o600)
    return metadata


def _put(
    bucket: str,
    key: str,
    path: Path,
    metadata: dict[str, Any],
    *,
    immutable: bool = False,
) -> None:
    arguments = [
        "s3api",
        "put-object",
        "--cli-input-json",
        json.dumps({"Bucket": bucket, "Key": key, **metadata}),
        "--body",
        str(path),
    ]
    if immutable:
        # 스냅샷 이후 다른 게시자가 만든 해시 자산을 덮어쓰지 않는다.
        arguments.extend(("--if-none-match", "*"))
    _aws(*arguments)


def _invalidate(distribution_id: str) -> str:
    deadline = time.monotonic() + INVALIDATION_TIMEOUT
    result = _aws(
        "cloudfront",
        "create-invalidation",
        "--distribution-id",
        distribution_id,
        "--paths",
        "/*",
        timeout=min(AWS_TIMEOUT, INVALIDATION_TIMEOUT),
    )
    invalidation = result["Invalidation"]["Id"]
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise PublicationError("CloudFront invalidation timed out")
        current = _aws(
            "cloudfront",
            "get-invalidation",
            "--distribution-id",
            distribution_id,
            "--id",
            invalidation,
            timeout=min(AWS_TIMEOUT, remaining),
        )
        if current["Invalidation"]["Status"] == "Completed":
            return invalidation
        time.sleep(min(POLL_INTERVAL, max(0, deadline - time.monotonic())))


class _HTTPSRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise PublicationError("site redirected away from HTTPS")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _http(url: str, accept: str) -> tuple[int, dict[str, str], bytes]:
    # urllib의 기본 HTTPS 처리가 인증서와 호스트 이름을 검증한다.
    try:
        response = build_opener(_HTTPSRedirect()).open(
            Request(url, headers={"Accept": accept}),
            timeout=20,
        )
    except HTTPError as error:
        response = error
    with response:
        body = response.read(32 * 1024 * 1024 + 1)
        if len(body) > 32 * 1024 * 1024:
            raise PublicationError("site response is too large")
        return (
            response.status,
            {k.lower(): v for k, v in response.headers.items()},
            body,
        )


def _smoke(site_url: str, files: dict[str, Path], main: str) -> dict[str, Any]:
    expected = _digest(files["index.html"])
    for path in ("/index.html", "/profile"):
        status, headers, body = _http(site_url + path, "text/html")
        if (
            status != 200
            or hashlib.sha256(body).hexdigest() != expected
            or headers.get("cache-control") != "no-cache"
            or "text/html" not in headers.get("content-type", "")
        ):
            raise PublicationError("site HTML does not match this release")
    missing = "/assets/__cd_missing_" + uuid.uuid4().hex + ".js"
    for path, accept in (
        (missing, "text/html"),
        ("/api/v1/health", "text/html"),
        ("/profile", "application/json"),
    ):
        status, headers, body = _http(site_url + path, accept)
        if (
            status not in (403, 404)
            or "text/html" in headers.get("content-type", "")
            or hashlib.sha256(body).hexdigest() == expected
        ):
            raise PublicationError("asset/API errors must not become SPA HTML")
    status, headers, body = _http(site_url + "/" + main, "*/*")
    if (
        status != 200
        or hashlib.sha256(body).hexdigest() != _digest(files[main])
        or headers.get("cache-control") != IMMUTABLE
    ):
        raise PublicationError("published module asset verification failed")
    return {"checks": 6, "index_sha256": expected, "main": main}


def _restore(bucket: str, key: str, snapshot: dict[str, Any], run_dir: Path) -> None:
    metadata = snapshot["metadata"]
    version = metadata.get("VersionId")
    if version and version != "null":
        try:
            arguments = [
                "s3api",
                "copy-object",
                "--bucket",
                bucket,
                "--key",
                key,
                "--copy-source",
                quote(bucket + "/" + key, safe="/")
                + "?versionId="
                + quote(version, safe=""),
                "--metadata-directive",
                "COPY",
            ]
            # S3의 MetadataDirective=COPY는 WebsiteRedirectLocation을 복사하지 않는다.
            if metadata.get("WebsiteRedirectLocation"):
                arguments.extend(
                    ("--website-redirect-location", metadata["WebsiteRedirectLocation"])
                )
            _aws(*arguments)
            return
        except PublicationError:
            pass  # 이전 버전을 읽을 수 없어도 보관한 본문과 헤더로 복구한다.
    _put(
        bucket,
        key,
        run_dir / snapshot["body"],
        {field: metadata[field] for field in RESTORE_FIELDS if field in metadata},
    )


def _rollback(
    bucket: str,
    distribution_id: str,
    site_url: str,
    run_dir: Path,
    snapshots: dict[str, Any],
    new_mutable: set[str],
    attempted: set[str],
) -> dict[str, Any]:
    errors: list[str] = []
    # 일부 업로드만 완료된 경우에도 이전 HTML을 다른 변경 가능 객체보다 먼저 복구한다.
    keys = sorted(
        set(snapshots) | (new_mutable & attempted),
        key=lambda key: (key != "index.html", key),
    )
    for key in keys:
        try:
            if key in snapshots:
                _restore(bucket, key, snapshots[key], run_dir)
                body = run_dir / "restored-object-check"
                metadata = _download(bucket, key, body)
                original = snapshots[key]
                if _digest(body) != original["sha256"] or any(
                    metadata.get(field) != original["metadata"][field]
                    for field in RESTORE_FIELDS
                    if field in original["metadata"]
                ):
                    raise PublicationError("restored object differs from snapshot")
            else:
                # 이 배포에서 새로 만든 변경 가능 키만 정확히 지정해 삭제한다.
                _aws("s3api", "delete-object", "--bucket", bucket, "--key", key)
        except Exception:
            errors.append("restore failed: " + key)
    try:
        if (new_mutable & attempted) & _keys(bucket):
            errors.append("new mutable object remains after rollback")
    except Exception:
        errors.append("rollback object absence check failed")
    invalidation = None
    try:
        invalidation = _invalidate(distribution_id)
    except Exception:
        errors.append("rollback invalidation failed")
    if not errors:
        try:
            status, _, body = _http(site_url + "/index.html", "text/html")
            old = snapshots.get("index.html")
            if old:
                if status != 200 or hashlib.sha256(body).hexdigest() != old["sha256"]:
                    raise PublicationError("old index mismatch")
            elif status not in (403, 404):
                raise PublicationError("new index still reachable")
        except Exception:
            errors.append("rollback site verification failed")
    return {
        "status": "failed" if errors else "restored",
        "errors": errors,
        "invalidation_id": invalidation,
    }


def _publish(
    dist: Path,
    sha: str,
    bucket: str,
    distribution_id: str,
    site_url: str,
    api_base_url: str,
    state_dir: Path,
    progress: dict[str, bool],
) -> dict[str, Any]:
    """현재 dist를 게시하고 업로드·검증 실패 시 복구한 뒤 예외를 발생시킨다.

    스냅샷과 실행 기록은 state_dir 아래 별도의 비공개 디렉터리에 남긴다. dist에 없는
    기존 변경 가능 파일도 보존하며, 이전 index가 없는 최초 배포도 처리한다.
    프로세스 강제 종료에는 호출자의 별도 복구 정책이 필요하다.
    """
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise PublicationError("a full lowercase commit SHA is required")
    if not re.fullmatch(
        r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket
    ) or not re.fullmatch(r"[A-Z0-9]+", distribution_id):
        raise PublicationError("invalid frontend AWS target")
    site_url = _https_url(site_url, origin=True)
    api_base_url = _https_url(api_base_url)
    files, main = _build(dist.absolute(), api_base_url)
    state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix=sha + "-", dir=state_dir))
    (run_dir / "objects").mkdir(mode=0o700)
    existing = _keys(bucket)
    mutable = {key for key in files if not key.startswith("assets/")}
    new_mutable = mutable - existing
    snapshots: dict[str, Any] = {}
    for key in sorted(key for key in existing if not key.startswith("assets/")):
        body = Path("objects") / hashlib.sha256(key.encode()).hexdigest()
        metadata = _download(bucket, key, run_dir / body)
        snapshots[key] = {
            "body": body.as_posix(),
            "metadata": metadata,
            "sha256": _digest(run_dir / body),
        }
    # 첫 쓰기 전에 기존 불변 자산과 겹치는 모든 키의 내용을 검증한다.
    assets = sorted(key for key in files if key.startswith("assets/"))
    for key in assets:
        if key in existing:
            body = run_dir / "immutable-check"
            _download(bucket, key, body)
            if _digest(body) != _digest(files[key]):
                raise PublicationError(
                    "immutable asset key already has different bytes"
                )
    snapshot = {
        "bucket": bucket,
        "objects": snapshots,
        "new_mutable": sorted(new_mutable),
    }
    _save(run_dir / "snapshot.json", snapshot)
    receipt: dict[str, Any] = {
        "release_sha": sha,
        "status": "prepared",
        "state_dir": str(run_dir),
        "files": len(files),
        "attempted_mutable": [],
    }
    _save(run_dir / "receipt.json", receipt)
    attempted: set[str] = set()
    try:
        order = [key for key in assets if key not in existing]
        order += sorted(mutable - {"index.html"}) + ["index.html"]
        for key in order:
            immutable = key.startswith("assets/")
            if not immutable:
                receipt["attempted_mutable"] = sorted(attempted | {key})
                _save(run_dir / "receipt.json", receipt)
                attempted.add(
                    key
                )  # 요청 실패·시간 초과여도 서버 쓰기는 끝났을 수 있다.
                progress["mutable_started"] = True
            content_type = (
                "text/html; charset=utf-8"
                if key.endswith(".html")
                else mimetypes.guess_type(key)[0] or "application/octet-stream"
            )
            _put(
                bucket,
                key,
                files[key],
                {
                    "ContentType": content_type,
                    "CacheControl": "no-cache"
                    if key == "index.html"
                    else IMMUTABLE
                    if immutable
                    else MUTABLE,
                    "Metadata": {"release-sha": sha},
                },
                immutable=immutable,
            )
        receipt["invalidation_id"] = _invalidate(distribution_id)
        receipt["smoke"] = _smoke(site_url, files, main)
        receipt["status"] = "published"
        _save(run_dir / "receipt.json", receipt)
        return receipt
    except Exception as error:
        receipt["status"] = "failed"
        receipt["rollback"] = (
            _rollback(
                bucket,
                distribution_id,
                site_url,
                run_dir,
                snapshots,
                new_mutable,
                attempted,
            )
            if attempted
            else {"status": "not-needed", "errors": [], "invalidation_id": None}
        )
        _save(run_dir / "receipt.json", receipt)
        outcome = receipt["rollback"]["status"]
        raise PublicationError(
            f"frontend publication failed; rollback {outcome}; see private receipt",
            rollback_succeeded=outcome in ("restored", "not-needed"),
        ) from error


def publish(
    dist: Path,
    sha: str,
    bucket: str,
    distribution_id: str,
    site_url: str,
    api_base_url: str,
    state_dir: Path,
) -> dict[str, Any]:
    """배포 기록을 반환하거나 복구 상태를 담은 PublicationError를 발생시킨다."""
    progress = {"mutable_started": False}
    try:
        return _publish(
            dist,
            sha,
            bucket,
            distribution_id,
            site_url,
            api_base_url,
            state_dir,
            progress,
        )
    except PublicationError:
        raise
    except Exception as error:
        raise PublicationError(
            "frontend publication stopped unexpectedly; inspect private state",
            rollback_succeeded=not progress["mutable_started"],
        ) from error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in (
        "dist",
        "sha",
        "bucket",
        "distribution-id",
        "site-url",
        "api-base-url",
        "state-dir",
    ):
        parser.add_argument(
            "--" + name,
            required=True,
            type=Path if name in ("dist", "state-dir") else str,
        )
    arguments = vars(parser.parse_args())
    try:
        result = publish(**arguments)
    except PublicationError as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
