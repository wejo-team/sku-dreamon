"""앱 수명에 맞춰 DB 연결을 관리하고 라우터와 오류 핸들러를 연결한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings
from app.core.db.session import create_database
from app.core.http.handlers import register_error_handlers
from app.routers.catalogs import router as catalogs_router
from app.routers.health import router as health_router
from app.routers.notifications import router as notifications_router
from app.routers.profiles import router as profiles_router


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
    return app


app = create_app()
