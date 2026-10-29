"""앱 수명에 맞춰 DB 연결을 관리하고 라우터와 오류 핸들러를 연결한다."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agents.factory import OpenAiAgentDriver
from app.core.config import Settings
from app.core.db.session import create_database
from app.core.http.deployment import DeploymentFastAPI
from app.core.http.handlers import register_error_handlers
from app.routers.ai import router as ai_router
from app.routers.application_review import router as application_review_router
from app.routers.applications import router as applications_router
from app.routers.auth import router as auth_router
from app.routers.catalogs import router as catalogs_router
from app.routers.contests import router as contests_router
from app.routers.health import router as health_router
from app.routers.notifications import router as notifications_router
from app.routers.profiles import router as profiles_router
from app.routers.team_management import router as team_management_router
from app.routers.teams import router as teams_router
from app.security.passwords import PasswordBlocklist
from app.services.health import ReadinessProbe

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()
    config.require_http_configuration()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = create_database(str(config.database_url), settings=config)
        app.state.database = database
        app.state.ai_driver = None
        try:
            app.state.ai_driver = (
                OpenAiAgentDriver(config) if config.ai_enabled else None
            )
            app.state.password_blocklist = (
                None
                if config.password_blocklist_path is None
                else await asyncio.to_thread(
                    PasswordBlocklist.from_file,
                    config.password_blocklist_path,
                    version=config.password_blocklist_version,
                )
            )
            yield
        finally:
            try:
                if not await app.state.readiness_probe.close(
                    config.shutdown_timeout_seconds
                ):
                    logger.error("readiness_cleanup_incomplete")
            finally:
                try:
                    if app.state.ai_driver is not None:
                        async with asyncio.timeout(config.shutdown_timeout_seconds):
                            await app.state.ai_driver.model.root_async_client.close()
                finally:
                    async with asyncio.timeout(config.shutdown_timeout_seconds):
                        await database.engine.dispose()

    app = DeploymentFastAPI(title="서경드림온 API", lifespan=lifespan)
    app.state.settings = config
    app.state.readiness_probe = ReadinessProbe()
    register_error_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(ai_router, prefix="/api/v1")
    app.include_router(catalogs_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(teams_router, prefix="/api/v1")
    app.include_router(applications_router, prefix="/api/v1")
    app.include_router(team_management_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(application_review_router, prefix="/api/v1")
    app.include_router(contests_router, prefix="/api/v1")
    return app


app = create_app()
