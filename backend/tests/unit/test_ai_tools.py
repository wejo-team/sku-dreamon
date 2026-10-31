"""모델 도구의 입력 계약·권한·실행별 조회 예산을 검사한다."""

import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, ValidationError

from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import Reference, Resource
from app.core.exceptions import AppError
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.services.ai_sources import SourceReader, SourceSearchResult


@pytest.fixture
def chat_tools() -> tuple[Mock, SourceTools, dict[str, BaseTool]]:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose="chat")
    reader.search = AsyncMock(return_value=SourceSearchResult([], 1, 0, {}))
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    return reader, sources, {item.name: item for item in sources.build()}


@pytest.mark.parametrize(
    ("name", "kind", "arguments", "filters"),
    [
        ("find_people", "person", {}, {"role_code": None, "field_code": None}),
        (
            "find_contests",
            "contest",
            {},
            {
                "field_code": None,
                "registration_status": None,
                "deadline_within_days": None,
            },
        ),
        ("find_teams", "team", {}, {"role_code": None}),
        (
            "search_people_by_name",
            "person",
            {"name": "  김민수  "},
            {"name": "김민수", "role_code": None, "field_code": None},
        ),
        (
            "search_contests_by_title",
            "contest",
            {"title": "  AI  "},
            {
                "title": "AI",
                "field_code": None,
                "registration_status": None,
                "deadline_within_days": None,
            },
        ),
        (
            "search_teams_by_name",
            "team",
            {"name": "  Alpha  "},
            {"name": "Alpha", "role_code": None},
        ),
    ],
)
async def test_distinct_search_tools_fix_scope_and_normalize_text(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    kind: str,
    arguments: dict[str, object],
    filters: dict[str, object],
) -> None:
    reader, sources, exposed = chat_tools
    assert set(exposed) == {
        "find_people",
        "find_contests",
        "find_teams",
        "search_people_by_name",
        "search_contests_by_title",
        "search_teams_by_name",
        "get_resource_detail",
    }
    assert "query" not in exposed[name].args
    payload: dict[str, object] = {**arguments, "page": 2}
    result = await exposed[name].ainvoke(payload)
    assert result == {
        "items": [],
        "hasMore": False,
        "page": 1,
        "pageLimitReached": False,
        "appliedFilters": {},
    }
    reader.search.assert_awaited_once_with(kind, 2, **filters)
    assert sources.calls == 1


def _enum_values(schema: object) -> set[str]:
    if isinstance(schema, dict):
        values = {str(value) for value in schema.get("enum", [])}
        for value in schema.values():
            values.update(_enum_values(value))
        return values
    if isinstance(schema, list):
        return set().union(*(_enum_values(value) for value in schema))
    return set()


@pytest.mark.parametrize(
    ("name", "field", "catalog"),
    [
        ("find_teams", "role_code", RoleCode),
        ("search_teams_by_name", "role_code", RoleCode),
        ("find_people", "role_code", RoleCode),
        ("find_people", "field_code", FieldCode),
        ("search_people_by_name", "role_code", RoleCode),
        ("search_people_by_name", "field_code", FieldCode),
        ("find_contests", "field_code", FieldCode),
        ("search_contests_by_title", "field_code", FieldCode),
    ],
)
def test_provider_schema_exposes_catalog_codes_and_korean_meanings(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    field: str,
    catalog: type[RoleCode] | type[FieldCode],
) -> None:
    _, _, exposed = chat_tools
    parameters = convert_to_openai_tool(exposed[name])["function"]["parameters"]
    input_model = exposed[name].get_input_schema()
    assert issubclass(input_model, BaseModel)
    assert input_model.model_json_schema()["additionalProperties"] is False
    property_schema = parameters["properties"][field]
    assert _enum_values(property_schema) == {code.value for code in catalog}
    description = property_schema["description"]
    for code in catalog:
        assert f"{code.value}={code.display_name}" in description
    assert "예:" in description and "null" in description and "AND" in description


def test_contest_schema_exposes_status_deadline_and_required_literal_title(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
) -> None:
    _, _, exposed = chat_tools
    parameters = convert_to_openai_tool(exposed["search_contests_by_title"])[
        "function"
    ]["parameters"]
    fields = parameters["properties"]
    assert _enum_values(fields["registration_status"]) == {
        status.value for status in RegistrationStatus
    }
    assert "closed" in fields["deadline_within_days"]["description"]
    assert "24시간" in fields["deadline_within_days"]["description"]
    assert parameters["required"] == ["title"]
    assert fields["title"]["minLength"] == 1 and fields["title"]["maxLength"] == 100


@pytest.mark.parametrize(
    ("name", "kind", "arguments", "filters"),
    [
        (
            "find_teams",
            "team",
            {"role_code": "development"},
            {"role_code": "development"},
        ),
        (
            "search_people_by_name",
            "person",
            {"name": "김", "role_code": "development", "field_code": "it_technology"},
            {"name": "김", "role_code": "development", "field_code": "it_technology"},
        ),
        (
            "search_contests_by_title",
            "contest",
            {
                "title": "AI",
                "field_code": "it_technology",
                "registration_status": "open",
                "deadline_within_days": 7,
            },
            {
                "title": "AI",
                "field_code": "it_technology",
                "registration_status": "open",
                "deadline_within_days": 7,
            },
        ),
    ],
)
async def test_all_filters_apply_together(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    kind: str,
    arguments: dict[str, object],
    filters: dict[str, object],
) -> None:
    reader, _, exposed = chat_tools
    payload: dict[str, object] = {**arguments, "page": 2}
    await exposed[name].ainvoke(payload)
    reader.search.assert_awaited_once_with(kind, 2, **filters)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("find_teams", {"role_code": "개발자"}),
        ("find_people", {"role_code": "developer"}),
        ("find_people", {"field_code": "IT·기술"}),
        ("find_contests", {"field_code": "not_a_field"}),
        ("find_contests", {"registration_status": "모집 중"}),
        ("find_teams", {"field_code": "design"}),
        ("find_teams", {"recruiting_only": False}),
        ("find_teams", {"roleCode": "development"}),
        ("find_people", {"skill_code": "programming"}),
        ("find_contests", {"role_code": "development"}),
        ("find_people", {"page_size": 100}),
        ("find_teams", {"page": 0}),
        ("find_teams", {"page": 11}),
        ("find_teams", {"page": 1.5}),
        ("find_teams", {"page": True}),
        ("find_contests", {"query": "마감이 가까운"}),
        ("find_contests", {"title": "AI"}),
        *[
            ("find_contests", {"deadline_within_days": value})
            for value in [0, 366, 1.5, True, "7"]
        ],
        ("find_contests", {"registration_status": "closed", "deadline_within_days": 7}),
        (
            "search_contests_by_title",
            {"title": "AI", "registration_status": "closed", "deadline_within_days": 7},
        ),
        *[
            (name, {field: value})
            for name, field in [
                ("search_contests_by_title", "title"),
                ("search_teams_by_name", "name"),
                ("search_people_by_name", "name"),
            ]
            for value in ["", "  ", "a" * 101, "a\x00", "\ud800", None]
        ],
        ("search_teams_by_name", {}),
    ],
)
async def test_invalid_tool_arguments_fail_before_reading(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    arguments: dict[str, object],
) -> None:
    reader, sources, exposed = chat_tools
    with pytest.raises(ValidationError):
        await exposed[name].ainvoke(arguments)
    reader.search.assert_not_awaited()
    assert sources.calls == 0


@pytest.mark.parametrize("days", [1, 365, None])
async def test_deadline_boundaries_and_scheduled_status_are_valid(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    days: int | None,
) -> None:
    reader, _, exposed = chat_tools
    await exposed["find_contests"].ainvoke(
        {"deadline_within_days": days, "registration_status": "scheduled"}
    )
    assert reader.search.call_args.kwargs["deadline_within_days"] == days


async def test_search_preserves_pagination_metadata_after_permission_exclusions(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
) -> None:
    reader, _, exposed = chat_tools
    reader.search.return_value = SourceSearchResult(
        [uuid4()], 10, 11, {"roleCode": "development"}
    )
    reader.get = AsyncMock(side_effect=AppError(404, "RESOURCE_NOT_FOUND", "없음"))
    result = await exposed["find_teams"].ainvoke(
        {"page": 10, "role_code": "development"}
    )
    assert result == {
        "items": [],
        "hasMore": False,
        "page": 10,
        "pageLimitReached": True,
        "appliedFilters": {"roleCode": "development"},
    }


@pytest.mark.parametrize(
    ("purpose", "name", "arguments"),
    [
        (
            "chat",
            "get_resource_detail",
            {"kind": "team", "resource_id": str(uuid4()), "include_private": True},
        ),
        ("applicant_recommendation", "list_applicants", {"team_id": str(uuid4())}),
    ],
)
async def test_read_tools_reject_unadvertised_scope_arguments(
    purpose: str, name: str, arguments: dict[str, object]
) -> None:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(
        purpose=purpose,
        application_id=uuid4() if purpose == "applicant_review" else None,
    )
    reader.get = AsyncMock()
    reader.applicants = AsyncMock(return_value=SourceSearchResult([], 1, 0, {}))
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    exposed = {item.name: item for item in sources.build()}
    input_model = exposed[name].get_input_schema()
    assert issubclass(input_model, BaseModel)
    input_schema = input_model.model_json_schema()
    assert input_schema["additionalProperties"] is False
    with pytest.raises(ValidationError):
        await exposed[name].ainvoke(arguments)
    reader.get.assert_not_awaited()
    reader.applicants.assert_not_awaited()
    assert sources.calls == 0


@pytest.mark.parametrize(
    ("purpose", "application_id", "expected"),
    [
        ("applicant_review", uuid4(), {"read_applicant"}),
        ("applicant_recommendation", None, {"list_applicants"}),
    ],
)
def test_applicant_tools_do_not_expose_public_search(
    purpose: str, application_id: UUID | None, expected: set[str]
) -> None:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose=purpose, application_id=application_id)
    exposed = SourceTools(reader, max_sources=30, max_calls=8).build()
    assert {item.name for item in exposed} == expected
    for item in exposed:
        assert (
            not {
                "requester",
                "principal",
                "team_id",
                "application_id",
                "permission",
            }
            & item.args.keys()
        )


async def test_parallel_reads_cannot_exceed_source_budget() -> None:
    async def load(kind: str, resource_id: UUID) -> Resource:
        await asyncio.sleep(0)
        return Resource(
            reference=Reference(
                kind="person", resource_id=resource_id, fingerprint="a" * 64
            ),
            title="가상 사용자",
            is_demo=False,
            facts={},
        )

    reader = Mock(spec=SourceReader)
    reader.get = AsyncMock(side_effect=load)
    tools = SourceTools(reader, max_sources=3, max_calls=8)
    results = await asyncio.gather(
        *(tools.load("person", uuid4()) for _ in range(4)), return_exceptions=True
    )
    assert len(tools.observed) == 3
    assert sum(isinstance(result, ToolBudgetExceeded) for result in results) == 1
    assert reader.get.await_count == 3


async def test_changed_observed_source_cannot_silently_replace_earlier_evidence() -> (
    None
):
    resource_id = uuid4()
    reader = Mock(spec=SourceReader)
    reader.get = AsyncMock(
        side_effect=[
            Resource(
                reference=Reference(
                    kind="person", resource_id=resource_id, fingerprint=digest
                ),
                title="가상 사용자",
                is_demo=False,
                facts={},
            )
            for digest in ("a" * 64, "b" * 64)
        ]
    )
    tools = SourceTools(reader, max_sources=3, max_calls=8)
    await tools.load("person", resource_id)
    with pytest.raises(AppError) as error:
        await tools.load("person", resource_id)
    assert error.value.code == "AI_CONTEXT_CHANGED"


async def test_applicant_page_budget_matches_public_search_metadata() -> None:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose="applicant_recommendation", application_id=None)
    reader.applicants = AsyncMock(return_value=SourceSearchResult([], 10, 11, {}))
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    listing = sources.build()[0]
    result = await listing.ainvoke({"page": 10})
    assert result == {
        "items": [],
        "hasMore": False,
        "page": 10,
        "pageLimitReached": True,
        "appliedFilters": {},
    }
    reader.applicants.assert_awaited_once_with(10)
