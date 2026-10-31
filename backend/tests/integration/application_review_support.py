"""팀장 검토·선발 검증에 현재 프로필과 팀장 소속을 준비한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.core.config import Settings
from app.core.db.base import Base
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.models.academic_units import AcademicUnit
from app.models.contests import ContestField
from app.models.courses import Course, ProfileCourse
from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)
from app.routers.application_review import router
from app.security.csrf import issue_csrf_token
from tests.integration.application_support import (
    ORIGIN,
    SIGNING_KEY,
    ApplicationData,
)


@pytest.fixture
async def review_data(application_data: ApplicationData) -> ApplicationData:
    data = application_data
    tables = [
        Base.metadata.tables[model.__tablename__]
        for model in (
            AcademicUnit,
            Profile,
            ProfileInterest,
            ProfileDesiredRole,
            ProfileSkill,
            PortfolioLink,
            Course,
            ProfileCourse,
            ContestField,
        )
    ]
    async with data.database.engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables))
    async with data.database.session() as session:
        session.add_all(
            [
                Profile(profile_id=account_id, real_name="검토 사용자", is_public=False)
                for account_id in (data.applicant_id, data.leader_id, data.stranger_id)
            ]
        )
        await session.flush()
        for account_id in (data.applicant_id, data.leader_id, data.stranger_id):
            session.add(ProfileInterest(account_id=account_id, field_code="design"))
            session.add(ProfileDesiredRole(account_id=account_id, role_code="design"))
        session.add(ContestField(contest_id=data.contest_id, field_code="design"))
        await session.commit()
    return data


@asynccontextmanager
async def review_client(
    data: ApplicationData, account_id: UUID | None
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database = data.database
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
            issued = data.sessions[account_id]
            client.cookies.set(SESSION_COOKIE_NAME, issued.token)
            token = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            client.cookies.set(CSRF_COOKIE_NAME, token)
            client.headers[CSRF_HEADER_NAME] = token
            client.headers["Origin"] = ORIGIN
        yield client
