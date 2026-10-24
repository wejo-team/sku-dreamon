"""지원 API의 인증과 전송 계약을 업무 서비스에 연결한다."""

from typing import Annotated
from uuid import UUID

from fastapi import Path

from app.core.http.dependencies import DatabaseSession
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Success
from app.dependencies.auth import CurrentAccount
from app.queries import applications as application_queries
from app.schemas.applications import ApplicationResponse


async def get_application(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> ApplicationResponse:
    return await application_queries.get_application(
        session, application_id, account_id
    )


applications = BaseCrudRouter(prefix="", tags=["applications"])
applications.add_detail(
    "/applications/{applicationId}",
    handler=get_application,
    response_model=Success[ApplicationResponse],
    error_statuses=(401,),
    name="get_application",
    summary="본인 또는 받은 팀장의 지원 조회",
)
router = applications.router
