"""포스터 복구가 추천·공유 이미지와 다른 출처를 섞지 않는지 검증한다."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from scripts.backfill_contest_posters import (
    MAX_IMAGE,
    BackfillError,
    Decision,
    PublicFetcher,
    Snapshot,
    inspect_source,
    parse_poster,
    reusable,
    validate_target,
    validate_url,
)

SOURCE = "https://linkareer.com/activity/123"
POSTER = "https://api.linkareer.com/attachments/456"


def headline(title: str) -> str:
    return (
        '<header class="ActivityInformationHeader__StyledWrapper-sc-test">'
        f"<h1>{title}</h1></header>"
    )


def test_body_heading_does_not_override_the_matching_activity_header() -> None:
    html = (
        f'<link rel="canonical" href="{SOURCE}">{headline("제목")}'
        f'<img class="card-image" alt="제목" src="{POSTER}">'
        '<article id="DETAIL"><h1>상세 본문의 다른 제목</h1></article>'
    )
    assert parse_poster(html, SOURCE, "제목") == POSTER


@pytest.mark.parametrize("activity_header", ["", headline("변경된 제목")])
def test_body_or_site_heading_cannot_replace_the_activity_header(
    activity_header: str,
) -> None:
    html = (
        f'<link rel="canonical" href="{SOURCE}">{activity_header}'
        '<header class="SiteHeader"><h1>제목</h1></header>'
        '<article id="DETAIL"><h1>제목</h1></article>'
        f'<img class="card-image" alt="제목" src="{POSTER}">'
    )
    with pytest.raises(BackfillError, match="headline_mismatch"):
        parse_poster(html, SOURCE, "제목")


def test_poster_uses_matching_title_and_canonical_not_social_or_recommendations() -> (
    None
):
    html = f'''<link rel="canonical" href="{SOURCE}">{headline("공고 &amp; 제목")}
    <meta property="og:image" content="https://api.linkareer.com/attachments/999">
    <img alt="다른 공고" src="https://api.linkareer.com/attachments/888">
    <img class="card-image" alt="공고 &amp; 제목" src="{POSTER}">
    <img alt="공고 &amp; 제목" src="https://media-cdn.linkareer.com/se2editor/image/123">'''
    assert parse_poster(html, SOURCE, "공고 & 제목") == POSTER


@pytest.mark.parametrize(
    "html",
    [
        f'<link rel="canonical" href="{SOURCE}">{headline("제목")}'
        f'<img class="card-image" alt="다른 제목" src="{POSTER}">',
        '<link rel="canonical" href="https://linkareer.com/activity/999">'
        f'{headline("제목")}<img class="card-image" alt="제목" src="{POSTER}">',
        f'{headline("제목")}<img class="card-image" alt="제목" src="{POSTER}">',
        f'<link rel="canonical" href="{SOURCE}">{headline("제목")}'
        f'<img class="card-image" alt="제목" src="{POSTER}">'
        '<img class="card-image" alt="제목" src="https://api.linkareer.com/attachments/789">',
        f'<link rel="canonical" href="{SOURCE}">{headline("변경된 제목")}'
        f'<img class="card-image" alt="제목" src="{POSTER}">',
    ],
)
def test_changed_or_ambiguous_source_has_no_proposal(html: str) -> None:
    with pytest.raises(BackfillError):
        parse_poster(html, SOURCE, "제목")


@pytest.mark.parametrize(
    "url",
    [
        "http://api.linkareer.com/attachments/456",
        "https://127.0.0.1/attachments/456",
        "https://api.linkareer.com.evil.test/attachments/456",
        "https://user:password@api.linkareer.com/attachments/456",
        "https://api.linkareer.com:444/attachments/456",
        "https://api.linkareer.com/attachments/456?redirect=http://localhost",
        "https://api.linkareer.com/attachments/../private",
    ],
)
def test_image_target_is_restricted_before_request(url: str) -> None:
    with pytest.raises(BackfillError):
        validate_url(url, image=True)


def test_only_known_poster_redirect_host_is_allowed() -> None:
    assert validate_url(POSTER, image=True) == POSTER
    cdn = "https://media-cdn.linkareer.com/activity_manager/posters/456"
    assert validate_url(cdn, image=True) == cdn
    with pytest.raises(BackfillError):
        validate_url(cdn, image=False)


class StubFetcher(PublicFetcher):
    def __init__(self, responses: list[tuple[int, dict[str, str], bytes]]) -> None:
        super().__init__()
        self.responses = responses
        self.requested: list[str] = []

    async def once(self, url: str, *, head: bool) -> tuple[int, dict[str, str], bytes]:
        self.requested.append(url)
        return self.responses.pop(0)


def before() -> Snapshot:
    return Snapshot(
        id=UUID(int=1),
        title="제목",
        source_url=SOURCE,
        version=1,
        updated_at=datetime(2026, 10, 28, tzinfo=UTC),
        row_sha256="original",
    )


@pytest.mark.parametrize("status", [403, 429])
async def test_access_restrictions_are_reported_without_retry(status: int) -> None:
    fetcher = StubFetcher([(status, {}, b"")])
    decision = await inspect_source(before(), fetcher)
    assert decision.status == f"http_{status}"
    assert decision.poster_url is None
    assert fetcher.requested == [SOURCE]


@pytest.mark.parametrize("target", [SOURCE, "http://localhost/private"])
async def test_redirect_cycle_or_unsafe_target_is_not_requested(target: str) -> None:
    fetcher = StubFetcher([(302, {"location": target}, b"")])
    with pytest.raises(BackfillError):
        await fetcher.fetch(SOURCE, image=False)
    assert fetcher.requested == [SOURCE]


@pytest.mark.parametrize(
    ("content_type", "length", "expected"),
    [
        ("image/png", "42", "ready"),
        ("image/svg+xml", "42", "image_type_or_size_unknown"),
        ("text/html", "42", "image_type_or_size_unknown"),
        ("image/jpeg", "", "image_type_or_size_unknown"),
        ("image/jpeg", str(MAX_IMAGE + 1), "image_size_limit"),
    ],
)
async def test_image_must_have_a_supported_type_and_bounded_size(
    content_type: str,
    length: str,
    expected: str,
) -> None:
    html = (
        f'<link rel="canonical" href="{SOURCE}">{headline("제목")}'
        f'<img class="card-image" alt="제목" src="{POSTER}">'
    )
    fetcher = StubFetcher(
        [
            (200, {"content-type": "text/html"}, html.encode()),
            (200, {"content-type": content_type, "content-length": length}, b""),
        ]
    )
    decision = await inspect_source(before(), fetcher)
    assert decision.status == expected
    assert bool(decision.poster_url) == (expected == "ready")


async def test_shared_image_is_validated_only_once_per_run() -> None:
    fetcher = StubFetcher([(200, {"content-type": "image/png"}, b"")])
    await fetcher.fetch(POSTER, image=True)
    await fetcher.fetch(POSTER, image=True)
    assert fetcher.requested == [POSTER]


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://wejo:wejo@remote.example.test/wejo_dev",
        "postgresql+asyncpg://wejo:wejo@localhost/production",
        "postgresql+asyncpg://wejo:wejo@localhost/wejo_dev?host=remote.example.test",
    ],
)
def test_cli_refuses_other_databases_and_connection_overrides(url: str) -> None:
    with pytest.raises(BackfillError):
        validate_target(url)


@pytest.mark.parametrize(
    "status", ["http_429", "http_503", "poster_missing_or_ambiguous"]
)
def test_explicit_retry_can_recover_a_failed_cache(status: str) -> None:
    prior = Decision(before=before(), status=status, checked_at=datetime.now(UTC))
    assert reusable(prior, before(), retry_failed=False)
    assert not reusable(prior, before(), retry_failed=True)


def test_success_cache_survives_retry_but_not_changed_snapshot() -> None:
    prior = Decision(before=before(), status="ready", checked_at=datetime.now(UTC))
    assert reusable(prior, before(), retry_failed=True)
    assert not reusable(
        prior, before().model_copy(update={"version": 2}), retry_failed=False
    )
