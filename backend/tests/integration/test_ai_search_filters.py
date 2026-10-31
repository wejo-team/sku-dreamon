"""AI 도구의 enum 역할 조건과 현재 지원 가능 경계를 실제 DB로 검증한다."""

from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Table

from app.agents.tools import SourceTools
from app.agents.types import AgentContext
from app.core.db.base import Base
from app.models.auth import Account, AuthSession
from app.models.teams import TeamMembership, TeamRecruitmentRole
from app.services.ai_sources import SourceReader
from app.services.sessions import SessionPrincipal
from tests.integration.test_team_queries import (
    NOW,
    TeamApi,
    api,  # noqa: F401 -- 격리 스키마와 기존 모집 경계 fixture 재사용
    new_team,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


async def authenticated_sources(team_api: TeamApi, account_id: UUID) -> SourceTools:
    """가짜 모델 호출 없이 실제 로그인 세션 검사와 검색 서비스를 연결한다."""
    now = datetime.now(UTC)
    auth_session_id = uuid4()
    token_hash = auth_session_id.bytes * 2
    async with team_api.database.engine.begin() as connection:
        await connection.run_sync(
            lambda conn: Base.metadata.create_all(
                conn, tables=[cast(Table, AuthSession.__table__)]
            )
        )
    async with team_api.database.session() as session:
        session.add(
            AuthSession(
                auth_session_id=auth_session_id,
                account_id=account_id,
                token_hash=token_hash,
                created_at=now,
                last_seen_at=now,
                expires_at=now + timedelta(days=1),
            )
        )
        await session.commit()
    principal = SessionPrincipal(
        auth_session_id=auth_session_id,
        account_id=account_id,
        token_hash=token_hash,
        expires_at=now + timedelta(days=1),
    )
    return SourceTools(
        SourceReader(
            team_api.database, AgentContext(principal=principal, purpose="chat")
        ),
        max_sources=30,
        max_calls=8,
    )


@pytest.fixture
async def search_sources(api: TeamApi) -> SourceTools:  # noqa: F811 -- pytest fixture
    # 기존 다섯 제외 사례에도 같은 역할을 붙여 역할 필터가 자격을 넓히지 않게 한다.
    async with api.database.session() as session:
        session.add_all(
            TeamRecruitmentRole(team_id=UUID(int=index), role_code="development")
            for index in range(101, 106)
        )
        other_leader_id = UUID(int=1008)
        session.add(
            Account(
                account_id=other_leader_id,
                login_id_normalized="person8",
                password_hash="test-password-hash",
            )
        )
        await session.flush()
        other = new_team(106, UUID(int=1), other_leader_id)
        session.add(other)
        await session.flush()
        session.add_all(
            [
                TeamRecruitmentRole(team_id=other.team_id, role_code="design"),
                TeamMembership(
                    team_id=other.team_id,
                    contest_id=other.contest_id,
                    account_id=other_leader_id,
                    joined_at=NOW - timedelta(days=1),
                ),
            ]
        )
        await session.commit()
    # 취소된 지원·종료된 소속만 가진 사용자는 다시 지원할 수 있다.
    return await authenticated_sources(api, UUID(int=1007))


async def test_role_filter_finds_team_without_role_word_in_text(
    search_sources: SourceTools,
) -> None:
    search = next(t for t in search_sources.build() if t.name == "find_teams")
    result = await search.ainvoke({"role_code": "development"})
    assert [item["key"] for item in result["items"]] == [f"team:{UUID(int=100)}"]
    assert result["hasMore"] is False
    facts = result["items"][0]["facts"]
    assert "개발자" not in facts["name"] + facts["introduction"]
    assert "development" in facts["roleCodes"]
    assert facts["isRecruiting"] is True


@pytest.mark.parametrize(
    ("query", "role_code", "expected"),
    [
        ("Alpha", "development", [f"team:{UUID(int=100)}"]),
        ("없는 검색어", "development", []),
        ("Alpha", "design", []),
    ],
)
async def test_team_name_and_role_filter_both_apply(
    search_sources: SourceTools, query: str, role_code: str, expected: list[str]
) -> None:
    search = next(t for t in search_sources.build() if t.name == "search_teams_by_name")
    result = await search.ainvoke({"name": query, "role_code": role_code})
    assert [item["key"] for item in result["items"]] == expected


async def test_role_filter_still_excludes_current_contest_member(
    api: TeamApi,  # noqa: F811 -- pytest fixture
    search_sources: SourceTools,
) -> None:
    # 이 계정은 같은 공모전에 이미 소속돼 있어 공개 검색의 일치 팀도 추천할 수 없다.
    sources = await authenticated_sources(api, UUID(int=1006))
    search = next(t for t in sources.build() if t.name == "find_teams")
    result = await search.ainvoke({"role_code": "development"})
    assert result == {
        "items": [],
        "hasMore": False,
        "page": 1,
        "pageLimitReached": False,
        "appliedFilters": {"roleCode": "development"},
    }
    assert sources.observed == {}
