"""공고 요약은 명세에 없는 URL 길이 제한을 추가하지 않는다."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.models.contests import Contest
from app.services.contests import build_contest_summary


@pytest.mark.parametrize("scheme", ["http", "https"])
def test_contest_summary_preserves_long_poster_url(scheme: str) -> None:
    now = datetime(2026, 10, 24, tzinfo=UTC)
    url = f"{scheme}://example.com/poster?token=" + "a" * 2100
    contest = Contest(
        contest_id=UUID(int=1),
        title="공고",
        organizer_name="주최기관",
        poster_url=url,
        registration_opens_at=now,
        registration_closes_at=now + timedelta(days=1),
        created_at=now,
        version=1,
    )

    summary = build_contest_summary(contest, field_codes=[], team_count=0, now=now)

    assert summary.model_dump(mode="json")["posterUrl"] == url
