"""지원받은 팀장의 조회와 명시적 검토 행동을 인증·전송 계약에 연결한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.domains.applications import review_service
from app.domains.applications.review_schemas import ApplicantResponse, ApplicantSearch
from app.domains.applications.schemas import ApplicationResponse, VersionedAction
from app.domains.auth.csrf import require_csrf
from app.domains.auth.dependencies import CurrentAccount, get_current_account

router = APIRouter(
    tags=["applications"], responses=error_responses(401, 403, 404, 422, 500, 503)
)


@router.get("/teams/{teamId}/applicants")
async def list_applicants(
    team_id: Annotated[UUID, Path(alias="teamId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
    query: Annotated[ApplicantSearch, Query()],
) -> Page[ApplicantResponse]:
    return await review_service.list_applicants(session, team_id, account_id, query)


@router.get("/applications/{applicationId}/applicant")
async def get_applicant(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
) -> Success[ApplicantResponse]:
    return Success(
        data=await review_service.get_applicant(session, application_id, account_id)
    )


@router.put(
    "/applications/{applicationId}/review-start",
    dependencies=[Depends(get_current_account), Depends(require_csrf)],
    responses=error_responses(409),
)
async def start_review(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
    body: VersionedAction,
) -> Success[ApplicationResponse]:
    return Success(
        data=await review_service.change_review_status(
            session, application_id, account_id, int(body.expected_version), "reviewing"
        )
    )


@router.put(
    "/applications/{applicationId}/rejection",
    dependencies=[Depends(get_current_account), Depends(require_csrf)],
    responses=error_responses(409),
)
async def reject_application(
    application_id: Annotated[UUID, Path(alias="applicationId")],
    account_id: CurrentAccount,
    session: DatabaseSession,
    body: VersionedAction,
) -> Success[ApplicationResponse]:
    return Success(
        data=await review_service.change_review_status(
            session, application_id, account_id, int(body.expected_version), "rejected"
        )
    )
