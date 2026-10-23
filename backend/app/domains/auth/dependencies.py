"""로그인 세션의 식별값을 FastAPI 요청에 연결한다."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyCookie

from app.core.db.session import Database
from app.core.exceptions import AppError
from app.domains.auth.session_service import SessionPrincipal, authenticate_session

SESSION_COOKIE_NAME = "__Host-sku-dreamon-session"
_session_cookie = APIKeyCookie(
    name=SESSION_COOKIE_NAME, scheme_name="SessionCookie", auto_error=False
)


async def get_optional_session(
    request: Request,
    token: Annotated[str | None, Security(_session_cookie)],
) -> SessionPrincipal | None:
    database = cast(Database, request.app.state.database)
    return await authenticate_session(database, token)


OptionalSession = Annotated[SessionPrincipal | None, Depends(get_optional_session)]


async def get_current_session(session: OptionalSession) -> SessionPrincipal:
    if session is None:
        raise AppError(401, "UNAUTHENTICATED", "로그인이 필요합니다.")
    return session


CurrentSession = Annotated[SessionPrincipal, Depends(get_current_session)]


async def get_current_account(session: CurrentSession) -> UUID:
    return session.account_id


async def get_optional_account(session: OptionalSession) -> UUID | None:
    return None if session is None else session.account_id


CurrentAccount = Annotated[UUID, Depends(get_current_account)]
OptionalAccount = Annotated[UUID | None, Depends(get_optional_account)]
