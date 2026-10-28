"""동시에 조회해도 실행별 자료 예산과 근거 일관성이 유지되는지 검사한다."""

import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import Reference, Resource
from app.core.exceptions import AppError
from app.services.ai_sources import SourceReader


@pytest.mark.parametrize(
    ("name", "kind"),
    [
        ("search_people", "person"),
        ("search_contests", "contest"),
        ("search_teams", "team"),
    ],
)
async def test_domain_search_tools_fix_resource_kind(name: str, kind: str) -> None:
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
    assert set(exposed[name].args) == {"query", "page"}
    result = await exposed[name].ainvoke({"query": "AI 아키텍처", "page": 2})
    assert result == {"items": [], "hasMore": False}
    reader.search.assert_awaited_once_with(kind, "AI 아키텍처", 2)
    assert sources.calls == 1


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
