"""AI 조건이 도메인 조회·서버 기준 시각·페이지 한도로 연결되는지 검사한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import AgentContext
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.schemas.contests import ContestSearch
from app.schemas.profiles import PeopleQuery
from app.schemas.teams import TeamSearch
from app.services import ai_sources, application_review, contests, profiles, teams
from app.services.ai_sources import SourceReader, SourceSearchResult


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
async def test_search_passes_filters_without_using_http_free_text(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["team", "person", "contest"],
) -> None:
    reader, session, require_session = source_reader
    resource_id = uuid4()
    listing = AsyncMock(
        return_value=Mock(
            data=[Mock(id=resource_id, account_id=resource_id)],
            pagination=Mock(page=2, total_pages=3),
        )
    )
    current = datetime(2026, 10, 31, 8, 30, tzinfo=UTC)
    monkeypatch.setattr(ai_sources, "_utcnow", lambda: current)
    if kind == "team":
        monkeypatch.setattr(teams, "list_teams", listing)
        result = await reader.search(
            kind, 2, name="도서관", role_code=RoleCode.DEVELOPMENT
        )
    elif kind == "person":
        monkeypatch.setattr(profiles, "list_people", listing)
        result = await reader.search(
            kind,
            2,
            name="도서관",
            role_code=RoleCode.DEVELOPMENT,
            field_code=FieldCode.IT_TECHNOLOGY,
        )
    else:
        monkeypatch.setattr(contests, "list_contests", listing)
        result = await reader.search(
            kind,
            2,
            title="도서관",
            field_code=FieldCode.IT_TECHNOLOGY,
            registration_status=RegistrationStatus.OPEN,
            deadline_within_days=7,
        )

    assert result.ids == [resource_id]
    assert result.metadata()["hasMore"] is True
    require_session.assert_awaited_once_with()
    listing.assert_awaited_once()
    assert listing.call_args.args[0] is session
    search = listing.call_args.args[1]
    assert search.q is None
    assert search.page == 2 and search.page_size == 8
    if kind == "team":
        assert isinstance(search, TeamSearch)
        assert search.role_code is RoleCode.DEVELOPMENT
        assert search.recruiting_only is True
        assert listing.call_args.kwargs == {"name_contains": "도서관"}
        assert result.applied_filters == {"name": "도서관", "roleCode": "development"}
    elif kind == "person":
        assert isinstance(search, PeopleQuery)
        assert search.role_code is RoleCode.DEVELOPMENT
        assert search.field_code is FieldCode.IT_TECHNOLOGY
        assert listing.call_args.kwargs == {"name_contains": "도서관"}
        assert result.applied_filters == {
            "name": "도서관",
            "roleCode": "development",
            "fieldCode": "it_technology",
        }
    else:
        assert isinstance(search, ContestSearch)
        assert search.field_code is FieldCode.IT_TECHNOLOGY
        assert search.registration_status is RegistrationStatus.OPEN
        assert search.sort == "deadline_asc"
        assert listing.call_args.kwargs == {
            "title_contains": "도서관",
            "deadline_within_days": 7,
            "now": current,
        }
        assert result.applied_filters == {
            "title": "도서관",
            "fieldCode": "it_technology",
            "registrationStatus": "open",
            "deadlineWithinDays": 7,
            "checkedAt": "2026-10-31T08:30:00Z",
            "deadlineAfter": "2026-10-31T08:30:00Z",
            "deadlineOnOrBefore": "2026-11-07T08:30:00Z",
        }


@pytest.mark.parametrize("kind", ["team", "person", "contest"])
async def test_find_without_filters_preserves_domain_defaults(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["team", "person", "contest"],
) -> None:
    reader, _, _ = source_reader
    listing = AsyncMock(
        return_value=Mock(data=[], pagination=Mock(page=1, total_pages=0))
    )
    if kind == "team":
        monkeypatch.setattr(teams, "list_teams", listing)
    elif kind == "person":
        monkeypatch.setattr(profiles, "list_people", listing)
    else:
        monkeypatch.setattr(contests, "list_contests", listing)

    result = await reader.search(kind, 1)
    assert result.ids == []
    assert result.metadata()["hasMore"] is False
    assert result.metadata()["pageLimitReached"] is False
    search = listing.call_args.args[1]
    assert search.q is None and search.page == 1 and search.page_size == 8
    if isinstance(search, TeamSearch):
        assert search.role_code is None and search.recruiting_only is True
        assert result.applied_filters == {"roleCode": None}
    elif isinstance(search, PeopleQuery):
        assert search.role_code is None and search.field_code is None
        assert result.applied_filters == {"roleCode": None, "fieldCode": None}
    else:
        assert isinstance(search, ContestSearch)
        assert search.field_code is None and search.registration_status is None
        assert search.sort == "deadline_asc"
        assert result.applied_filters == {
            "fieldCode": None,
            "registrationStatus": None,
            "deadlineWithinDays": None,
        }


@pytest.mark.parametrize(
    ("page", "total_pages", "has_more", "limit"),
    [
        (1, 0, False, False),
        (2, 3, True, False),
        (9, 11, True, False),
        (10, 10, False, False),
        (10, 11, False, True),
    ],
)
def test_pagination_distinguishes_end_from_ten_page_budget(
    page: int,
    total_pages: int,
    has_more: bool,
    limit: bool,
) -> None:
    metadata = SourceSearchResult([], page, total_pages, {}).metadata()
    assert metadata == {
        "page": page,
        "hasMore": has_more,
        "pageLimitReached": limit,
        "appliedFilters": {},
    }
    assert "totalCount" not in metadata


@pytest.mark.parametrize("kind", ["team", "person", "contest"])
async def test_reader_returns_actual_clamped_page(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
    kind: Literal["team", "person", "contest"],
) -> None:
    reader, _, _ = source_reader
    listing = AsyncMock(
        return_value=Mock(data=[], pagination=Mock(page=2, total_pages=2))
    )
    module, function = {
        "contest": (contests, "list_contests"),
        "team": (teams, "list_teams"),
        "person": (profiles, "list_people"),
    }[kind]
    monkeypatch.setattr(module, function, listing)
    result = await reader.search(kind, 10)
    assert result.metadata()["page"] == 2
    assert result.metadata()["hasMore"] is False
    assert result.metadata()["pageLimitReached"] is False


async def test_applicant_context_cannot_call_public_search(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
) -> None:
    reader, _, require_session = source_reader
    reader.context = Mock(spec=AgentContext, purpose="applicant_recommendation")
    with pytest.raises(AppError) as error:
        await reader.search("contest", 1)
    assert error.value.code == "FORBIDDEN"
    require_session.assert_not_awaited()


async def test_applicant_reader_preserves_candidates_and_actual_page(
    source_reader: tuple[SourceReader, Mock, AsyncMock],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reader, _, require_session = source_reader
    candidate_id = uuid4()
    reader.context = Mock(
        spec=AgentContext,
        purpose="applicant_recommendation",
        team_id=uuid4(),
        principal=Mock(account_id=uuid4()),
    )
    listing = AsyncMock(
        return_value=Mock(
            data=[
                Mock(application=Mock(id=candidate_id), is_selection_candidate=True),
                Mock(application=Mock(id=uuid4()), is_selection_candidate=False),
            ],
            pagination=Mock(page=2, total_pages=2),
        )
    )
    monkeypatch.setattr(application_review, "list_applicants", listing)
    result = await reader.applicants(10)
    assert result.ids == [candidate_id]
    assert result.metadata() == {
        "page": 2,
        "hasMore": False,
        "pageLimitReached": False,
        "appliedFilters": {},
    }
    require_session.assert_awaited_once_with()
    assert listing.call_args.args[1:3] == (
        reader.context.team_id,
        reader.context.principal.account_id,
    )
