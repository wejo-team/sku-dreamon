"""로컬 개발 공고의 누락 포스터를 조사하고 검토한 계획만 원자적으로 적용한다."""

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import Database, create_database
from app.models.contests import Contest

ARTIFACTS = Path(__file__).resolve().parents[2] / ".bugbash/explore-feedback/posters"
MAX_HTML = 2 * 1024 * 1024
MAX_IMAGE = 12 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class BackfillError(Exception):
    """민감한 입력이나 접속 정보를 포함하지 않는 실패 코드."""


class Snapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    title: str
    source_url: str
    version: int = Field(gt=0)
    updated_at: AwareDatetime
    row_sha256: str
    poster_url: None = None


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    before: Snapshot
    status: str
    poster_url: str | None = None
    final_image_url: str | None = None
    content_type: str | None = None
    content_length: int | None = None
    html_sha256: str | None = None
    checked_at: AwareDatetime


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = "contest-posters-v1"
    created_at: AwareDatetime
    selected: int
    decisions: list[Decision]


def validate_target(value: str) -> None:
    target = make_url(value)
    if (
        target.drivername != "postgresql+asyncpg"
        or target.host not in {"localhost", "127.0.0.1", "::1"}
        or target.database != "wejo_dev"
        or target.query
    ):
        raise BackfillError("local_wejo_dev_required")


def validate_url(value: str, *, image: bool) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port not in {None, 443}
        or parsed.query
        or parsed.fragment
    ):
        raise BackfillError("url_not_allowed")
    patterns = (
        {
            "api.linkareer.com": r"/attachments/[1-9][0-9]*",
            "media-cdn.linkareer.com": r"/activity_manager/posters/[1-9][0-9]*",
        }
        if image
        else {"linkareer.com": r"/activity/[1-9][0-9]*"}
    )
    if not re.fullmatch(patterns.get(parsed.hostname or "", r"(?!)"), parsed.path):
        raise BackfillError("url_not_allowed")
    return value


def normalized_title(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


class PosterHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.canonicals: set[str] = set()
        self.images: list[tuple[str, str, set[str]]] = []
        self.headings: set[str] = set()
        self.heading_parts: list[str] | None = None
        self.activity_headers: list[bool] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "header":
            self.activity_headers.append(
                any(
                    name.startswith("ActivityInformationHeader__")
                    for name in (values.get("class") or "").split()
                )
            )
        if tag == "link" and values.get("rel") == "canonical":
            self.canonicals.add(values.get("href") or "")
        if tag == "img":
            self.images.append(
                (
                    values.get("alt") or "",
                    values.get("src") or "",
                    set((values.get("class") or "").split()),
                )
            )
        if tag == "h1" and any(self.activity_headers):
            self.heading_parts = []

    def handle_data(self, data: str) -> None:
        if self.heading_parts is not None:
            self.heading_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1" and self.heading_parts is not None:
            self.headings.add(normalized_title("".join(self.heading_parts)))
            self.heading_parts = None
        if tag == "header" and self.activity_headers:
            self.activity_headers.pop()


def parse_poster(html: str, source: str, title: str) -> str:
    validate_url(source, image=False)
    parsed = PosterHTML()
    parsed.feed(html)
    if parsed.canonicals != {source}:
        raise BackfillError("canonical_mismatch")
    if parsed.headings != {normalized_title(title)}:
        raise BackfillError("headline_mismatch")
    images = {
        src
        for alt, src, classes in parsed.images
        if "card-image" in classes and normalized_title(alt) == normalized_title(title)
    }
    if len(images) != 1:
        raise BackfillError("poster_missing_or_ambiguous")
    return validate_url(images.pop(), image=True)


def row_digest(contest: Contest) -> str:
    values = {
        column.name: getattr(contest, column.name)
        for column in Contest.__table__.columns
    }
    raw = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def snapshot(contest: Contest) -> Snapshot:
    if contest.poster_url is not None:
        raise BackfillError("poster_already_present")
    return Snapshot(
        id=contest.contest_id,
        title=contest.title,
        source_url=contest.source_url or "",
        version=contest.version,
        updated_at=contest.updated_at,
        row_sha256=row_digest(contest),
    )


def save_json(path: Path, value: BaseModel | dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        temporary = Path(file.name)
    temporary.chmod(0o600)
    temporary.replace(path)


class PublicFetcher:
    """기본 curl 요청만 사용한다. 우회·UA 변경·재시도 없이 URL마다 한 번 확인한다."""

    def __init__(self) -> None:
        self.last_request = 0.0
        self.image_responses: dict[str, tuple[int, dict[str, str], bytes]] = {}

    async def once(self, url: str, *, head: bool) -> tuple[int, dict[str, str], bytes]:
        await asyncio.sleep(max(0, 1 - (time.monotonic() - self.last_request)))
        self.last_request = time.monotonic()
        with tempfile.TemporaryDirectory() as directory:
            headers, body = Path(directory) / "headers", Path(directory) / "body"
            command = [
                "curl",
                "--silent",
                "--show-error",
                "--proto",
                "=https",
                "--max-time",
                "20",
                "--connect-timeout",
                "5",
                "--max-filesize",
                str(MAX_IMAGE if head else MAX_HTML),
                "--dump-header",
                str(headers),
                "--output",
                str(body),
                "--write-out",
                "%{http_code}",
            ]
            if head:
                command.append("--head")
            process = await asyncio.create_subprocess_exec(
                *command,
                url,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, _ = await asyncio.wait_for(process.communicate(), timeout=25)
            except TimeoutError:
                process.kill()
                await process.wait()
                raise BackfillError("request_timeout") from None
            if process.returncode:
                raise BackfillError("request_failed_or_size_limit")
            content = await asyncio.to_thread(body.read_bytes)
            if len(content) > MAX_HTML:
                raise BackfillError("html_size_limit")
            parsed: dict[str, str] = {}
            for line in (await asyncio.to_thread(headers.read_text)).splitlines():
                if line.startswith("HTTP/"):
                    parsed = {}
                elif ":" in line:
                    key, value = line.split(":", 1)
                    parsed[key.lower()] = value.strip()
            return int(stdout), parsed, content

    async def fetch(
        self, url: str, *, image: bool
    ) -> tuple[str, dict[str, str], bytes]:
        visited: set[str] = set()
        for _ in range(3):
            validate_url(url, image=image)
            if url in visited:
                raise BackfillError("redirect_cycle")
            visited.add(url)
            response = self.image_responses.get(url) if image else None
            if response is None:
                response = await self.once(url, head=image)
                if image:
                    self.image_responses[url] = response
            status, headers, body = response
            if status in {301, 302, 303, 307, 308}:
                url = urljoin(url, headers.get("location", ""))
                continue
            if status != 200:
                raise BackfillError(f"http_{status}")
            return url, headers, body
        raise BackfillError("redirect_limit")


def save_html(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("wb") as file:
        path.chmod(0o600)
        file.write(content)


async def inspect_source(
    before: Snapshot, fetcher: PublicFetcher, evidence_dir: Path | None = None
) -> Decision:
    outcome = Decision(before=before, status="pending", checked_at=datetime.now(UTC))
    try:
        final, headers, html = await fetcher.fetch(before.source_url, image=False)
        if final != before.source_url or "text/html" not in headers.get(
            "content-type", ""
        ):
            raise BackfillError("source_response_mismatch")
        outcome.html_sha256 = hashlib.sha256(html).hexdigest()
        if evidence_dir is not None:
            await asyncio.to_thread(save_html, evidence_dir / f"{before.id}.html", html)
        poster = parse_poster(html.decode("utf-8"), before.source_url, before.title)
        final_image, image_headers, _ = await fetcher.fetch(poster, image=True)
        content_type = image_headers.get("content-type", "").split(";", 1)[0].lower()
        length = image_headers.get("content-length", "")
        if content_type not in IMAGE_TYPES or not length.isdigit():
            raise BackfillError("image_type_or_size_unknown")
        if not 0 < int(length) <= MAX_IMAGE:
            raise BackfillError("image_size_limit")
        outcome.poster_url = poster
        outcome.final_image_url = final_image
        outcome.content_type = content_type
        outcome.content_length = int(length)
        outcome.status = "ready"
    except (BackfillError, UnicodeError, ValueError) as error:
        outcome.status = (
            str(error) if isinstance(error, BackfillError) else "invalid_source"
        )
    return outcome


def reusable(prior: Decision, before: Snapshot, *, retry_failed: bool) -> bool:
    return prior.before == before and (prior.status == "ready" or not retry_failed)


async def collect(
    database: Database, *, limit: int, retry_failed: bool = False
) -> Path:
    async with database.session() as session:
        await session.execute(text("SET TRANSACTION READ ONLY"))
        contests = await session.scalars(
            select(Contest)
            .where(Contest.poster_url.is_(None))
            .order_by(Contest.created_at.desc(), Contest.contest_id.desc())
            .limit(limit)
        )
        snapshots = [snapshot(contest) for contest in contests]
    plan = Plan(created_at=datetime.now(UTC), selected=len(snapshots), decisions=[])
    fetcher = PublicFetcher()
    for before in snapshots:
        cached = ARTIFACTS / "cache" / f"{before.id}.json"
        decision = None
        if cached.exists():
            prior = Decision.model_validate_json(
                await asyncio.to_thread(cached.read_bytes)
            )
            if reusable(prior, before, retry_failed=retry_failed):
                decision = prior
        if decision is None:
            decision = await inspect_source(before, fetcher, ARTIFACTS / "html")
            await asyncio.to_thread(save_json, cached, decision)
        plan.decisions.append(decision)
        if decision.status == "http_429":
            break
    path = ARTIFACTS / f"plan-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"
    await asyncio.to_thread(save_json, path, plan)
    return path


async def apply_changes(
    session: AsyncSession, decisions: list[Decision]
) -> list[dict[str, object]]:
    ready = [item for item in decisions if item.status == "ready"]
    if len({item.before.id for item in ready}) != len(ready):
        raise BackfillError("duplicate_contest")
    locked: list[tuple[Contest, Decision]] = []
    for item in sorted(ready, key=lambda item: item.before.id):
        if not item.poster_url or not item.final_image_url:
            raise BackfillError("invalid_ready_decision")
        validate_url(item.poster_url, image=True)
        validate_url(item.final_image_url, image=True)
        validate_url(item.before.source_url, image=False)
        if (
            item.content_type not in IMAGE_TYPES
            or not 0 < (item.content_length or 0) <= MAX_IMAGE
        ):
            raise BackfillError("invalid_image_evidence")
        contest = await session.get(
            Contest, item.before.id, with_for_update=True, populate_existing=True
        )
        if (
            contest is None
            or contest.poster_url is not None
            or snapshot(contest) != item.before
        ):
            raise BackfillError("stale_or_changed_contest")
        locked.append((contest, item))
    undo: list[dict[str, object]] = []
    for contest, item in locked:
        contest.poster_url = item.poster_url
        contest.version += 1
        contest.updated_at = datetime.now(UTC)
        undo.append(
            {
                "id": str(contest.contest_id),
                "expected_poster_url": item.poster_url,
                "expected_version": contest.version,
                "restore_poster_url": None,
            }
        )
    await session.flush()
    return undo


async def run(
    *, limit: int, apply: Path | None, retry_failed: bool = False
) -> dict[str, object]:
    url = os.environ.get("DATABASE_URL", "")
    validate_target(url)
    database = create_database(url)
    try:
        if apply is None:
            path = await collect(database, limit=limit, retry_failed=retry_failed)
            plan = Plan.model_validate_json(await asyncio.to_thread(path.read_bytes))
            return {
                "plan": str(path),
                "selected": plan.selected,
                "statuses": dict(Counter(item.status for item in plan.decisions)),
            }
        if not (await asyncio.to_thread(apply.resolve)).is_relative_to(
            await asyncio.to_thread(ARTIFACTS.resolve)
        ):
            raise BackfillError("plan_must_be_in_ignored_poster_artifacts")
        plan = Plan.model_validate_json(await asyncio.to_thread(apply.read_bytes))
        if plan.format != "contest-posters-v1":
            raise BackfillError("unknown_plan_format")
        async with database.session() as session, session.begin():
            if await session.scalar(text("SELECT current_database()")) != "wejo_dev":
                raise BackfillError("local_wejo_dev_required")
            undo = await apply_changes(session, plan.decisions)
            recovery: dict[str, object] = {
                "plan": str(apply),
                "rollback": undo,
                "status": "prepared",
                "note": (
                    "Restore only while expected values match; "
                    "increment version and updated_at."
                ),
            }
            await asyncio.to_thread(
                save_json, apply.with_suffix(".recovery.json"), recovery
            )
        recovery["status"] = "applied"
        await asyncio.to_thread(
            save_json, apply.with_suffix(".recovery.json"), recovery
        )
        return {
            "updated": len(undo),
            "recovery": str(apply.with_suffix(".recovery.json")),
        }
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="실패 캐시만 명시적으로 한 번 다시 확인(429는 전체 중단)",
    )
    parser.add_argument(
        "--apply", type=Path, help="검토한 계획 JSON을 실제 개발 DB에 적용"
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("limit must be between 1 and 1000")
    try:
        print(
            json.dumps(
                asyncio.run(
                    run(
                        limit=args.limit,
                        apply=args.apply,
                        retry_failed=args.retry_failed,
                    )
                )
            )
        )
    except Exception as error:
        message = (
            str(error) if isinstance(error, BackfillError) else type(error).__name__
        )
        print(json.dumps({"error": message}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
