"""공고 목록의 공개 범위·검색·페이지·시간 경계를 확인한다."""

from datetime import timedelta

import pytest

from tests.integration.test_contest_detail import CONTEST_ID, END, START, ContestApi

pytest_plugins = ["tests.integration.test_contest_detail"]
pytestmark = [pytest.mark.integration, pytest.mark.database]


async def test_public_list_defaults_to_all_and_clamps(api: ContestApi) -> None:
    response = await api.client.get("/api/v1/contests?page=999&pageSize=1")
    assert response.status_code == 200, response.text
    assert response.json()["pagination"] == {
        "page": 2,
        "pageSize": 1,
        "total": 2,
        "totalPages": 2,
    }
    assert response.json()["data"][0]["id"] == str(CONTEST_ID)
    assert response.json()["data"][0]["teamCount"] == 2


@pytest.mark.parametrize(
    "query,total",
    [("q=원문", 2), ("q=디자인", 1), ("fieldCode=design", 1), ("q=%25", 0), ("q=_", 0)],
)
async def test_search_and_field_filter(api: ContestApi, query: str, total: int) -> None:
    response = await api.client.get(f"/api/v1/contests?{query}")
    assert response.status_code == 200, response.text
    assert response.json()["pagination"]["total"] == total


async def test_status_at_exact_boundaries(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.services import contests

    for moment, status in (
        (START - timedelta(microseconds=1), "scheduled"),
        (START, "open"),
        (END, "closed"),
    ):
        monkeypatch.setattr(contests, "_utcnow", lambda moment=moment: moment)
        response = await api.client.get(f"/api/v1/contests?registrationStatus={status}")
        assert response.json()["pagination"]["total"] == 2
        assert all(
            item["registrationStatus"] == status for item in response.json()["data"]
        )
        assert (await api.client.get("/api/v1/contests")).json()["pagination"][
            "total"
        ] == 2


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "pageSize=101",
        "q=%00",
        "registrationStatus=invalid",
        "fieldCode=invalid",
        "sort=invalid",
    ],
)
async def test_invalid_query(api: ContestApi, query: str) -> None:
    assert (await api.client.get(f"/api/v1/contests?{query}")).status_code == 422


async def test_count_and_rows_share_snapshot(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    from uuid import uuid4

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.repositories import contest_list
    from tests.integration.test_contest_detail import make_contest

    original = contest_list.count_contests

    async def count_then_insert(
        session: AsyncSession, filters: contest_list.ContestFilter
    ) -> int:
        count = await original(session, filters)
        async with api.database.session() as writer:
            writer.add(make_contest(uuid4()))
            await writer.commit()
        return count

    monkeypatch.setattr(contest_list, "count_contests", count_then_insert)
    first = (await api.client.get("/api/v1/contests?sort=deadline_asc")).json()
    assert first["pagination"]["total"] == len(first["data"]) == 2
    assert first["data"][0]["id"] == str(CONTEST_ID)


@pytest.mark.parametrize(
    "sort,expected",
    [
        # 마감 공고(1·3)는 마감이 가장 이르고 가장 최근 등록이어도 마지막에 온다.
        ("deadline_asc", [5, 4, 1, 3]),
        ("created_desc", [5, 4, 3, 1]),
    ],
)
async def test_closed_contests_come_last_in_both_sorts(
    api: ContestApi, monkeypatch: pytest.MonkeyPatch, sort: str, expected: list[int]
) -> None:
    from datetime import UTC, datetime
    from uuid import UUID

    from app.services import contests
    from tests.integration.test_contest_detail import make_contest

    async with api.database.session() as session:
        for number, closes_in, created in ((4, 10, 1), (5, 5, 2)):
            contest = make_contest(UUID(int=number))
            contest.registration_closes_at = END + timedelta(days=closes_in)
            contest.created_at = datetime(2020, 1, created, tzinfo=UTC)
            session.add(contest)
        await session.commit()
    monkeypatch.setattr(contests, "_utcnow", lambda: END + timedelta(hours=1))

    response = await api.client.get(f"/api/v1/contests?sort={sort}")
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert [item["id"] for item in data] == [str(UUID(int=n)) for n in expected]
    assert [item["registrationStatus"] for item in data] == [
        "open",
        "open",
        "closed",
        "closed",
    ]
