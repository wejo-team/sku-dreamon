"""실제 앱 라우터와 저장된 인증 세션으로 생성 HTTP 검사를 준비한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.main import create_app
from tests.integration.application_support import ORIGIN, SIGNING_KEY, ApplicationData


@asynccontextmanager
async def creation_client(
    data: ApplicationData, account_id: UUID | None
) -> AsyncIterator[AsyncClient]:
    app = create_app(
        Settings(
            csrf_signing_key=SecretStr(SIGNING_KEY),
            auth_allowed_origins=(ORIGIN,),
            _env_file=None,
        )
    )
    app.state.database = data.database
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False), base_url=ORIGIN
    ) as client:
        if account_id is not None:
            client.cookies.set(SESSION_COOKIE_NAME, data.sessions[account_id].token)
        token = (await client.get("/api/v1/auth/csrf")).json()["data"]["csrfToken"]
        client.headers.update({"Origin": ORIGIN, "X-CSRF-Token": token})
        yield client
