"""명시적으로 실행할 때만 가상 자료로 실제 Luna 도구·구조화 출력·스트림을 검사한다."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID, uuid4

from app.agents.factory import OpenAiAgentDriver
from app.agents.tools import SourceTools
from app.agents.types import AgentContext, Reference, Resource, fingerprint
from app.core.config import Settings
from app.core.db.session import create_database
from app.core.exceptions import AppError
from app.services.ai import validate_plan
from app.services.ai_sources import SourceReader
from app.services.sessions import SessionPrincipal

CONTEST_ID = UUID("a8b2e7d2-3afe-4e4c-a982-88f00d2c7400")


class SyntheticReader(SourceReader):
    async def require_session(self) -> None:
        pass

    async def search(
        self, kind: Literal["contest", "team", "person"], query: str, page: int
    ) -> tuple[list[UUID], bool]:
        return ([CONTEST_ID] if kind == "contest" else []), False

    async def get(self, kind: str, resource_id: UUID) -> Resource:
        if kind != "contest" or resource_id != CONTEST_ID:
            raise AppError(404, "RESOURCE_NOT_FOUND", "가상 검증 자료가 없습니다.")
        facts: dict[str, object] = {
            "title": "연동 검증용 가상 공모전",
            "description": "실제 공고가 아닌 자동화 연결 검사 자료",
            "fieldCodes": ["design"],
            "eligibilityText": "가상 안내문이며 원문 확인 필요",
        }
        return Resource(
            reference=Reference(
                kind="contest",
                resource_id=CONTEST_ID,
                contest_id=CONTEST_ID,
                fingerprint=fingerprint(facts),
            ),
            title="연동 검증용 가상 공모전",
            is_demo=False,
            facts=facts,
        )


async def main() -> None:
    settings = Settings(ai_max_output_tokens=1024)
    if (
        settings.openai_api_key is None
        or not settings.openai_api_key.get_secret_value()
    ):
        print({"success": False, "reason": "OPENAI_API_KEY is not configured"})
        raise SystemExit(1)
    database = create_database("postgresql+asyncpg://unused@127.0.0.1:1/unused")
    driver = OpenAiAgentDriver(settings)
    context = AgentContext(
        SessionPrincipal(uuid4(), uuid4(), b"", datetime.now(UTC) + timedelta(hours=1)),
        "chat",
    )
    sources = SourceTools(
        SyntheticReader(database, context), max_sources=3, max_calls=3
    )
    stage = "plan"
    try:
        async with asyncio.timeout(90):
            request = (
                "검색 도구로 연동 검증용 가상 공모전을 찾아 한 개 추천하고 "
                "이유와 주의점을 세 문장으로 알려줘."
            )
            plan = await driver.plan(sources, request, [], [])
            selected = validate_plan(plan, sources)
            assert len(selected) == 1 and sources.calls > 0
            stage = "stream"
            chunks = [part async for part in driver.write(plan, selected, request)]
            assert "".join(chunks).strip()
            print(
                {
                    "success": True,
                    "model": settings.ai_model,
                    "toolCalls": sources.calls,
                    "selected": len(selected),
                    "textChunks": len(chunks),
                }
            )
    except Exception as error:
        print(
            {
                "success": False,
                "stage": stage,
                "errorType": type(error).__name__,
                "status": getattr(error, "status_code", None),
                "code": getattr(error, "code", None),
            }
        )
        raise SystemExit(1) from None
    finally:
        await driver.model.root_async_client.close()
        await database.engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
