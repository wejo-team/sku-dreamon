"""동시에 조회해도 실행별 자료 예산과 근거 일관성이 유지되는지 검사한다."""

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
from app.services.ai_sources import SourceReader


@pytest.mark.parametrize(
    ("name", "kind", "filters"),
    [
        ("search_people", "person", {"role_code": None, "field_code": None}),
        (
            "search_contests",
            "contest",
            {"field_code": None, "registration_status": None},
        ),
        ("search_teams", "team", {"role_code": None}),
    ],
)
async def test_domain_search_tools_fix_resource_kind(
    name: str, kind: str, filters: dict[str, None]
) -> None:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose="chat")
    reader.search = AsyncMock(return_value=([], False))
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    exposed = {item.name: item for item in sources.build()}
    assert set(exposed) == {
        "search_people",
        "search_contests",
        "search_teams",
        "get_resource_detail",
    }
    assert set(exposed[name].args) == {"query", "page", *filters}
    result = await exposed[name].ainvoke({"query": "AI 아키텍처", "page": 2})
    assert result == {"items": [], "hasMore": False}
    reader.search.assert_awaited_once_with(kind, "AI 아키텍처", 2, **filters)
    assert sources.calls == 1


@pytest.fixture
def chat_tools() -> tuple[Mock, SourceTools, dict[str, BaseTool]]:
    reader = Mock(spec=SourceReader)
    reader.context = Mock(purpose="chat")
    reader.search = AsyncMock(return_value=([], False))
    sources = SourceTools(reader, max_sources=30, max_calls=8)
    return reader, sources, {item.name: item for item in sources.build()}


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
        ("search_teams", "role_code", RoleCode),
        ("search_people", "role_code", RoleCode),
        ("search_people", "field_code", FieldCode),
        ("search_contests", "field_code", FieldCode),
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
    input_schema = input_model.model_json_schema()
    assert input_schema["additionalProperties"] is False
    property_schema = parameters["properties"][field]
    assert _enum_values(property_schema) == {code.value for code in catalog}
    description = property_schema["description"]
    for code in catalog:
        assert code.value in description
        assert code.display_name in description


def test_contest_status_schema_exposes_all_supported_states(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
) -> None:
    _, _, exposed = chat_tools
    schema = convert_to_openai_tool(exposed["search_contests"])["function"][
        "parameters"
    ]["properties"]["registration_status"]
    assert _enum_values(schema) == {status.value for status in RegistrationStatus}
    assert "예정" in schema["description"]
    assert "접수" in schema["description"]
    assert "마감" in schema["description"]


@pytest.mark.parametrize(
    ("name", "kind", "filters"),
    [
        ("search_teams", "team", {"role_code": "development"}),
        (
            "search_people",
            "person",
            {"role_code": "development", "field_code": "it_technology"},
        ),
        (
            "search_contests",
            "contest",
            {"field_code": "it_technology", "registration_status": "open"},
        ),
    ],
)
async def test_search_filters_preserve_additional_query_and_page(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    kind: str,
    filters: dict[str, str],
) -> None:
    reader, sources, exposed = chat_tools
    arguments: dict[str, object] = {"query": "도서관", "page": 2, **filters}
    result = await exposed[name].ainvoke(arguments)
    assert result == {"items": [], "hasMore": False}
    reader.search.assert_awaited_once_with(kind, "도서관", 2, **filters)
    assert sources.calls == 1


@pytest.mark.parametrize(
    ("name", "kind", "filters"),
    [
        ("search_teams", "team", {"role_code": None}),
        ("search_people", "person", {"role_code": None, "field_code": None}),
        (
            "search_contests",
            "contest",
            {"field_code": None, "registration_status": None},
        ),
    ],
)
async def test_search_defaults_do_not_add_filters(
    chat_tools: tuple[Mock, SourceTools, dict[str, BaseTool]],
    name: str,
    kind: str,
    filters: dict[str, None],
) -> None:
    reader, _, exposed = chat_tools
    await exposed[name].ainvoke({})
    reader.search.assert_awaited_once_with(kind, "", 1, **filters)


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("search_teams", {"role_code": "개발자"}),
        ("search_people", {"role_code": "developer"}),
        ("search_people", {"field_code": "IT·기술"}),
        ("search_contests", {"field_code": "not_a_field"}),
        ("search_contests", {"registration_status": "모집 중"}),
        ("search_teams", {"field_code": "design"}),
        ("search_teams", {"recruiting_only": False}),
        ("search_teams", {"roleCode": "development"}),
        ("search_people", {"skill_code": "programming"}),
        ("search_contests", {"role_code": "development"}),
        ("search_people", {"page_size": 100}),
        ("search_teams", {"page": 0}),
        ("search_teams", {"page": 11}),
        ("search_teams", {"page": 1.5}),
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
    reader.applicants = AsyncMock(return_value=([], False))
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
