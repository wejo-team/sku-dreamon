"""동시에 조회해도 실행별 자료 예산과 근거 일관성이 유지되는지 검사한다."""

import asyncio
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest

from app.agents.tools import SourceTools, ToolBudgetExceeded
from app.agents.types import Reference, Resource
from app.core.exceptions import AppError
from app.services.ai_sources import SourceReader


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
