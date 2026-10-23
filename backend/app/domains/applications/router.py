"""지원 API의 인증과 전송 계약을 업무 서비스에 연결한다."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Success
from app.domains.applications import service
from app.domains.applications.schemas import (
    ApplicationResponse,
    CancellationResult,
    VersionedAction,
)
from app.domains.auth.csrf import require_csrf
from app.domains.auth.dependencies import CurrentAccount


async def get_application(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> ApplicationResponse:
    return await service.get_application(session, application_id, account_id)


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


@router.put(
    "/applications/{applicationId}/cancellation",
    dependencies=[Depends(require_csrf)],
    responses=error_responses(401, 403, 404, 409, 422, 500, 503),
    summary="본인 지원 취소",
)
async def cancel_application(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    body: VersionedAction,
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> Success[CancellationResult]:
    return Success(
        data=await service.cancel_application(
            session, application_id, account_id, int(body.expected_version)
        )
    )
