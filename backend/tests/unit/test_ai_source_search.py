"""AI 검색 필터가 기존 도메인 DTO와 서버의 조회 경계를 유지하는지 검사한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import AgentContext
from app.core.db.session import Database
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.schemas.contests import ContestSearch
from app.schemas.profiles import PeopleQuery
from app.schemas.teams import TeamSearch
from app.services import contests, profiles, teams
from app.services.ai_sources import SourceReader


@pytest.fixture
def source_reader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[SourceReader, Mock, AsyncMock]:
    session = Mock(spec=AsyncSession)

    @asynccontextmanager
    async def session_scope() -> AsyncIterator[AsyncSession]:
        yield session

    database = Mock(spec=Database)
    database.session.side_effect = session_scope
    reader = SourceReader(database, Mock(spec=AgentContext, purpose="chat"))
    require_session = AsyncMock()
    monkeypatch.setattr(reader, "require_session", require_session)
    return reader, session, require_session


@pytest.mark.parametrize("kind", ["team", "person", "contest"])
async def test_search_passes_enum_filters_to_domain_dto(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["team", "person", "contest"],
) -> None:
    reader, session, require_session = source_reader
    resource_id = uuid4()
    listing = AsyncMock(
        return_value=Mock(
            data=[Mock(id=resource_id, account_id=resource_id)],
            pagination=Mock(total_pages=3),
        )
    )
    if kind == "team":
        monkeypatch.setattr(teams, "list_teams", listing)
        result = await reader.search(kind, "도서관", 2, role_code=RoleCode.DEVELOPMENT)
    elif kind == "person":
        monkeypatch.setattr(profiles, "list_people", listing)
        result = await reader.search(
            kind,
            "도서관",
            2,
            role_code=RoleCode.DEVELOPMENT,
            field_code=FieldCode.IT_TECHNOLOGY,
        )
    else:
        monkeypatch.setattr(contests, "list_contests", listing)
        result = await reader.search(
            kind,
            "도서관",
            2,
            field_code=FieldCode.IT_TECHNOLOGY,
            registration_status=RegistrationStatus.OPEN,
        )

    assert result == ([resource_id], True)
    require_session.assert_awaited_once_with()
    listing.assert_awaited_once()
    assert listing.call_args.args[0] is session
    search = listing.call_args.args[1]
    assert search.q == "도서관"
    assert search.page == 2 and search.page_size == 8
    if kind == "team":
        assert isinstance(search, TeamSearch)
        assert search.role_code is RoleCode.DEVELOPMENT
        assert search.recruiting_only is True
    elif kind == "person":
        assert isinstance(search, PeopleQuery)
        assert search.role_code is RoleCode.DEVELOPMENT
        assert search.field_code is FieldCode.IT_TECHNOLOGY
    else:
        assert isinstance(search, ContestSearch)
        assert search.field_code is FieldCode.IT_TECHNOLOGY
        assert search.registration_status is RegistrationStatus.OPEN
        assert search.sort == "deadline_asc"


@pytest.mark.parametrize("kind", ["team", "person", "contest"])
async def test_search_without_filters_preserves_existing_defaults(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["team", "person", "contest"],
) -> None:
    reader, _, _ = source_reader
    listing = AsyncMock(return_value=Mock(data=[], pagination=Mock(total_pages=0)))
    if kind == "team":
        monkeypatch.setattr(teams, "list_teams", listing)
    elif kind == "person":
        monkeypatch.setattr(profiles, "list_people", listing)
    else:
        monkeypatch.setattr(contests, "list_contests", listing)

    assert await reader.search(kind, "", 1) == ([], False)
    search = listing.call_args.args[1]
    assert search.q == "" and search.page == 1 and search.page_size == 8
    if isinstance(search, TeamSearch):
        assert search.role_code is None
        assert search.recruiting_only is True
    elif isinstance(search, PeopleQuery):
        assert search.role_code is None and search.field_code is None
    else:
        assert isinstance(search, ContestSearch)
        assert search.field_code is None and search.registration_status is None
        assert search.sort == "deadline_asc"
