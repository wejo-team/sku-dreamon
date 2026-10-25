"""지원 API의 인증과 전송 계약을 업무 서비스에 연결한다."""

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Path, Query, Response

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Page, Success
from app.dependencies.auth import CurrentAccount, get_current_account
from app.dependencies.csrf import require_csrf
from app.schemas.application_create import ApplicationCreate
from app.schemas.applications import (
    ApplicationResponse,
    ApplicationSearch,
    CancellationResult,
    MyApplication,
    VersionedAction,
)
from app.services import applications as service
from app.services.application_create import submit_application


async def get_application(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> ApplicationResponse:
    return await service.get_application(session, application_id, account_id)


async def list_my_applications(
    query: Annotated[ApplicationSearch, Query()],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> Page[MyApplication]:
    return await service.list_my_applications(
        session,
        account_id,
        page=query.page,
        page_size=query.page_size,
        status=query.status,
    )


applications = BaseCrudRouter(prefix="", tags=["applications"])
applications.add_list(
    "/me/applications",
    handler=list_my_applications,
    response_model=Page[MyApplication],
    error_statuses=(401,),
    name="list_my_applications",
    summary="내 지원 현황",
)
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
    dependencies=[Depends(get_current_account), Depends(require_csrf)],
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


@router.post(
    "/teams/{teamId}/applications",
    status_code=201,
    response_model=Success[ApplicationResponse],
    responses={
        200: {"model": Success[ApplicationResponse]},
        **error_responses(401, 403, 404, 409, 422, 500, 503),
    },
    summary="신규 지원 접수",
)
async def post_application(
    team_id: Annotated[UUID, Path(alias="teamId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
    body: ApplicationCreate,
    response: Response,
    csrf: Annotated[None, Depends(require_csrf)],
) -> Success[ApplicationResponse]:
    result, created = await submit_application(session, account_id, team_id, body)
    response.status_code = 201 if created else 200
    response.headers["Cache-Control"] = "no-store"
    return Success(data=result)
