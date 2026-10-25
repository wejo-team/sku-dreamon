"""공개 팀 DTO의 모집 경계·전송 타입·시연 분류를 검증한다."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from app.models.contests import Contest
from app.models.teams import Team
from app.services.teams import build_team_summary

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    ("state", "start", "end", "team_end", "count", "expected"),
    [
        ("open", -1, 1, 1, 1, True),
        ("open", 0, 1, 1, 1, True),
        ("open", 1, 2, 1, 1, False),
        ("open", -1, 0, 1, 1, False),
        ("open", -1, 1, 0, 1, False),
        ("open", -1, 1, 1, 3, False),
        ("closed", -1, 1, 1, 1, False),
    ],
)
def test_team_summary_uses_current_common_recruitment_conditions(
    state: str, start: int, end: int, team_end: int, count: int, expected: bool
) -> None:
    contest = Contest(
        contest_id=UUID(int=1),
        title="공고",
        registration_opens_at=NOW + timedelta(seconds=start),
        registration_closes_at=NOW + timedelta(seconds=end),
    )
    team = Team(
        team_id=UUID(int=2),
        contest_id=contest.contest_id,
        version=7,
        name="공개 팀",
        introduction="팀 소개",
        target_capacity=3,
        recruitment_state=state,
        closed_reason="leader_closed" if state == "closed" else None,
        recruitment_closes_at=NOW + timedelta(seconds=team_end),
        created_at=NOW,
        deadline_source_date=date(2026, 10, 24),
        deadline_source_time=None,
        deadline_source_timezone=None,
        deadline_effective_timezone="Asia/Seoul",
        deadline_time_assumed=True,
        deadline_timezone_assumed=True,
    )
    result = build_team_summary(
        team,
        contest,
        field_codes=["public", "design"],
        role_codes=["development", "planning"],
        member_count=count,
        now=NOW,
    )
    body = result.model_dump(mode="json")
    assert body["isRecruiting"] is expected
    assert body["memberCount"] == count
    assert body["capacity"] == "3" and body["version"] == "7"
    assert body["fieldCodes"] == ["design", "public"]
    assert body["roleCodes"] == ["planning", "development"]
    assert body["recruitmentState"] == state
    assert body["recruitmentDeadline"] == {
        "sourceDate": "2026-10-24",
        "sourceTime": None,
        "sourceTimeZone": None,
        "effectiveTimeZone": "Asia/Seoul",
        "timeDefaulted": True,
        "timeZoneDefaulted": True,
    }
    assert "leader" not in body and "members" not in body and "applications" not in body
