"""인증된 본인 프로필과 공개 사람 목록·상세의 읽기 API를 제공한다."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Path, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.handlers import error_responses
from app.core.http.schemas import Page, Success
from app.domains.auth.dependencies import CurrentAccount
from app.domains.profiles import queries
from app.domains.profiles.schemas import PeopleQuery, PersonSummary, ProfileResponse

router = APIRouter(tags=["profiles"], responses=error_responses(401, 422, 500, 503))


@router.get("/me/profile", responses=error_responses(404))
async def get_own_profile(
    account_id: CurrentAccount, session: DatabaseSession
) -> Success[ProfileResponse]:
    return Success(data=await queries.get_own_profile(session, account_id))


@router.get("/people")
async def list_people(
    account_id: CurrentAccount,
    session: DatabaseSession,
    query: Annotated[PeopleQuery, Query()],
) -> Page[PersonSummary]:
    return await queries.list_people(session, query)


@router.get("/people/{accountId}", responses=error_responses(404))
async def get_public_profile(
    current_account_id: CurrentAccount,
    session: DatabaseSession,
    account_id: Annotated[UUID, Path(alias="accountId")],
) -> Success[ProfileResponse]:
    return Success(data=await queries.get_public_profile(session, account_id))
