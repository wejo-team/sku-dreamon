"""실제 계정 세션과 CSRF 쿠키로 팀 관리 HTTP 요청을 구성한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.db.session import Database
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.routers.team_management import router
from app.security.csrf import issue_csrf_token
from app.services.sessions import issue_session

ORIGIN = "https://api.example.test"
SIGNING_KEY = "team-management-tests-only-signing-key"


@asynccontextmanager
async def management_client(
    database: Database, account_id: UUID | None
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database = database
    app.state.settings = Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN
    ) as client:
        if account_id is not None:
            async with database.session() as session:
                issued = await issue_session(session, account_id)
                await session.commit()
            token = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            client.cookies.set(SESSION_COOKIE_NAME, issued.token)
            client.cookies.set(CSRF_COOKIE_NAME, token)
            client.headers[CSRF_HEADER_NAME] = token
            client.headers["Origin"] = ORIGIN
        yield client
