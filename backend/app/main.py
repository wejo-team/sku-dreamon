"""앱 수명에 맞춰 DB 연결을 관리하고 라우터와 오류 핸들러를 연결한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings
from app.core.db.session import create_database
from app.core.http.handlers import register_error_handlers
from app.domains.applications.router import router as applications_router
from app.domains.auth.router import router as auth_router
from app.domains.catalogs.router import router as catalogs_router
from app.domains.health.router import router as health_router
from app.domains.notifications.router import router as notifications_router
from app.domains.profiles.router import router as profiles_router
from app.domains.teams.management_router import router as team_management_router
from app.domains.teams.router import router as teams_router


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        database = create_database(str(config.database_url))
        app.state.database = database
        try:
            yield
        finally:
            await database.engine.dispose()

    app = FastAPI(title="서경드림온 API", lifespan=lifespan)
    app.state.settings = config
    register_error_handlers(app)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(catalogs_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(teams_router, prefix="/api/v1")
    app.include_router(applications_router, prefix="/api/v1")
    app.include_router(team_management_router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")
    return app


app = create_app()
