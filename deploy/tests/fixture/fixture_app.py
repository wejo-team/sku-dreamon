"""격리된 Docker DB에서 제품 API의 모델 driver만 대체한다."""

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.agents.tools import SourceTools
from app.agents.types import PreviousContext, RecommendationGate, RecommendationPlan
from app.core.config import Settings
from app.product_main import create_app as create_product_app
from fastapi import FastAPI, Request
from sqlalchemy.engine import make_url
from starlette.responses import JSONResponse


class FixtureDriver:
    """제품 실행·저장·SSE를 통과하는 유한한 결정론적 응답을 만든다."""

    async def stream(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
    ) -> AsyncIterator[str]:
        await gate(
            RecommendationPlan(
                intent="empty", selections=[], guidance="가상 배포 검증 응답입니다."
            )
        )
        yield "fixture started "
        delay = int(content.removeprefix("pause:"))
        if not 0 <= delay <= 310:
            raise ValueError("Invalid synthetic delay")
        await asyncio.sleep(delay)
        yield "fixture completed"


def create_app() -> FastAPI:
    settings = Settings(_env_file=None)
    explicit = make_url(os.environ.get("DATABASE_URL", ""))
    if (
        os.environ.get("DEP03_CONTAINER_E2E") != "1"
        or settings.app_env != "production"
        or explicit != make_url(str(settings.database_url))
        or explicit.drivername != "postgresql+asyncpg"
        or explicit.host != "postgres"
        or explicit.query
        or not (explicit.database or "").endswith("_e2e")
        or settings.openai_api_key
        or os.environ.get("OPENAI_API_KEY", "")
    ):
        raise RuntimeError(
            "Container fixture requires opt-in, postgres *_e2e and no key"
        )
    application = create_product_app(settings)
    product_lifespan = application.router.lifespan_context

    @asynccontextmanager
    async def fixture_lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with product_lifespan(app):
            original = app.state.ai_driver
            app.state.ai_driver = FixtureDriver()
            try:
                yield
            finally:
                app.state.ai_driver = original

    application.router.lifespan_context = fixture_lifespan

    @application.get("/_fixture/peer")
    async def peer(request: Request) -> dict[str, object]:
        return {
            "client": request.client.host if request.client else None,
            "scheme": request.url.scheme,
            "forwarded": {
                key: value
                for key, value in request.headers.items()
                if key == "forwarded" or key.startswith("x-forwarded-")
            },
        }

    if os.environ.get("DEP03_READY_FAIL") == "1":
        application.router.routes = [
            route
            for route in application.router.routes
            if getattr(route, "path", None) != "/api/v1/ready"
        ]

        @application.get("/api/v1/ready")
        async def not_ready() -> JSONResponse:
            return JSONResponse({"status": "unavailable"}, status_code=503)

    return application


app = create_app()
