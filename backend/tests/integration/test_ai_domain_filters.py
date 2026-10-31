"""AI 전용 이름·제목·기한 조건과 기존 공개 검색의 범위를 실제 DB로 검증한다."""

from datetime import timedelta
from uuid import UUID

import pytest

from app.core.db.session import Database
from app.models.contests import Contest, ContestField
from app.models.teams import Team
from app.schemas.contests import ContestSearch
from app.schemas.profiles import PeopleQuery
from app.schemas.teams import TeamSearch
from app.services import contests, profiles, teams
from tests.integration.test_contest_detail import (
    CONTEST_ID,
    START,
    ContestApi,
    make_contest,
)
from tests.integration.test_contest_detail import (
    api as contest_api,  # noqa: F401 -- 격리 공고 fixture 재사용
)
from tests.integration.test_people_api import (
    add_profile,
    people_database,  # noqa: F401 -- 격리 프로필 fixture 재사용
)
from tests.integration.test_team_queries import (
    NOW,
    TeamApi,
)
from tests.integration.test_team_queries import (
    api as team_api,  # noqa: F401 -- 격리 팀 fixture 재사용
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_contest_title_search_is_literal_and_keeps_http_search(
    contest_api: ContestApi,  # noqa: F811 -- pytest fixture
) -> None:
    async with contest_api.database.session() as session:
        contest = await session.get(Contest, CONTEST_ID)
        assert contest is not None
        contest.title = "ALPHA 100%_공모전"
        await session.commit()

    for needle, expected in (
        ("alpha", [CONTEST_ID]),
        ("%_", [CONTEST_ID]),
        ("주최자", []),
        ("디자인", []),
    ):
        async with contest_api.database.session() as session:
            result = await contests.list_contests(
                session, ContestSearch(), title_contains=needle
            )
        assert [item.id for item in result.data] == expected
        assert result.pagination.total == len(expected)

    # 기존 HTTP q는 계속 주최자·분야 표시명을 검색한다.
    for needle, total in (("주최자", 2), ("디자인", 1)):
        response = await contest_api.client.get(
            "/api/v1/contests", params={"q": needle}
        )
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] == total

    async with contest_api.database.session() as session:
        result = await contests.list_contests(
            session,
            ContestSearch.model_validate({"q": "주최자", "fieldCode": "design"}),
            title_contains="alpha",
        )
    assert [item.id for item in result.data] == [CONTEST_ID]


@pytest.mark.parametrize(
    ("status", "expected"),
    [(None, [12, 15, 13]), ("open", [12, 13]), ("scheduled", [15])],
)
async def test_contest_deadline_bounds_share_one_clock_and_combine_filters(
    contest_api: ContestApi,  # noqa: F811 -- pytest fixture
    monkeypatch: pytest.MonkeyPatch,
    status: str | None,
    expected: list[int],
) -> None:
    async with contest_api.database.session() as session:
        for number, offset in (
            (10, timedelta(microseconds=-1)),
            (11, timedelta()),
            (12, timedelta(microseconds=1)),
            (13, timedelta(days=7)),
            (14, timedelta(days=7, microseconds=1)),
            (15, timedelta(days=2)),
            (16, timedelta(days=3)),
        ):
            contest = make_contest(UUID(int=number))
            contest.title = "기간 경계 공모전"
            contest.registration_opens_at = START + timedelta(
                days=1 if number == 15 else -1
            )
            contest.registration_closes_at = START + offset
            session.add(contest)
        await session.flush()
        session.add_all(
            ContestField(
                contest_id=UUID(int=number),
                field_code="it_technology" if number == 16 else "design",
            )
            for number in range(10, 17)
        )
        await session.commit()
    # 전달한 기준 시각이 목록 필터와 응답 상태 모두에 적용돼야 한다.
    monkeypatch.setattr(contests, "_utcnow", lambda: START + timedelta(days=100))
    async with contest_api.database.session() as session:
        result = await contests.list_contests(
            session,
            ContestSearch.model_validate(
                {
                    "fieldCode": "design",
                    "registrationStatus": status,
                    "sort": "deadline_asc",
                }
            ),
            title_contains="기간",
            deadline_within_days=7,
            now=START,
        )
    assert [item.id for item in result.data] == [UUID(int=n) for n in expected]
    assert result.pagination.total == len(expected)
    assert all(item.registration_status != "closed" for item in result.data)


async def test_team_name_search_excludes_introduction_contest_and_role_labels(
    team_api: TeamApi,  # noqa: F811 -- pytest fixture
) -> None:
    async with team_api.database.session() as session:
        team = await session.get(Team, UUID(int=100))
        assert team is not None
        team.name = "ALPHA 100%_연구"
        await session.commit()
    for needle, expected in (
        ("alpha", [UUID(int=100)]),
        ("%_", [UUID(int=100)]),
        ("공개", []),
        ("공모전", []),
        ("개발", []),
    ):
        async with team_api.database.session() as session:
            result = await teams.list_teams(
                session,
                TeamSearch.model_validate({"recruitingOnly": True}),
                name_contains=needle,
                now=NOW,
            )
        assert [item.id for item in result.data] == expected
        assert result.pagination.total == len(expected)

    # 기존 HTTP q는 계속 소개·연결 공모전·역할 표시명을 검색한다.
    for needle in ("공개", "공모전", "개발"):
        response = await team_api.client.get("/api/v1/teams", params={"q": needle})
        assert response.status_code == 200
        assert response.json()["pagination"]["total"] > 0
    async with team_api.database.session() as session:
        result = await teams.list_teams(
            session,
            TeamSearch.model_validate({"roleCode": "design", "recruitingOnly": True}),
            name_contains="alpha",
            now=NOW,
        )
    assert result.data == [] and result.pagination.total == 0


async def test_people_name_search_is_public_literal_and_independent_of_labels(
    people_database: Database,  # noqa: F811 -- pytest fixture
) -> None:
    await add_profile(people_database, UUID(int=1), name="ALPHA 100%_홍길동")
    await add_profile(people_database, UUID(int=2), name="다른 사람")
    await add_profile(
        people_database, UUID(int=3), name="ALPHA 100%_비공개", public=False
    )
    for needle, expected in (
        ("alpha", [UUID(int=1)]),
        ("%_", [UUID(int=1)]),
        ("협업", []),
        ("개발", []),
        ("IT·기술", []),
    ):
        async with people_database.session() as session:
            result = await profiles.list_people(
                session, PeopleQuery(), name_contains=needle
            )
        assert [item.account_id for item in result.data] == expected
        assert result.pagination.total == len(expected)

    # HTTP에서 사용하는 기존 DTO 경로는 소개·역할·분야를 계속 검색한다.
    for needle in ("협업", "개발", "IT·기술"):
        async with people_database.session() as session:
            result = await profiles.list_people(
                session, PeopleQuery.model_validate({"q": needle})
            )
        assert result.pagination.total == 2
    async with people_database.session() as session:
        result = await profiles.list_people(
            session,
            PeopleQuery.model_validate({"roleCode": "design"}),
            name_contains="alpha",
        )
    assert result.data == [] and result.pagination.total == 0
