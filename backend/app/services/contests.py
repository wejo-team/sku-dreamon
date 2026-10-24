"""공개 공고의 상태·원문 응답을 같은 조회 시점의 저장 자료로 구성한다."""

from collections.abc import Sequence
from datetime import datetime

from pydantic import AnyHttpUrl

from app.core.demo_data import is_demo_contest
from app.models.contests import Contest
from app.rules.catalogs import FieldCode
from app.rules.contests import get_registration_status
from app.schemas.contests import ContestSummary


def build_contest_summary(
    contest: Contest,
    *,
    field_codes: Sequence[str],
    team_count: int,
    now: datetime,
) -> ContestSummary:
    """호출자가 같은 조회 시점에서 구한 분야·전체 팀 수로 공고 요약을 만든다."""
    return ContestSummary(
        id=contest.contest_id,
        title=contest.title,
        organizer=contest.organizer_name,
        field_codes=sorted(
            (FieldCode(code) for code in field_codes), key=lambda code: code.sort_order
        ),
        poster_url=None
        if contest.poster_url is None
        else AnyHttpUrl(contest.poster_url),
        registration_status=get_registration_status(
            starts_at=contest.registration_opens_at,
            ends_at=contest.registration_closes_at,
            now=now,
        ),
        starts_at=contest.registration_opens_at,
        ends_at=contest.registration_closes_at,
        team_count=team_count,
        is_demo=is_demo_contest(contest.contest_id),
        created_at=contest.created_at,
        version=str(contest.version),
    )
