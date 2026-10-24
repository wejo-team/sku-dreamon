"""접속 IP·정규화 아이디를 인증 시도 제한 서비스로 전달한다."""

from typing import Literal, cast

from fastapi import Request

from app.core.config import Settings
from app.core.db.session import Database
from app.services.auth_attempts import consume


async def limit_auth(
    request: Request,
    operation: Literal["login", "signup", "availability"],
    login_id: str | None = None,
) -> None:
    settings = cast(Settings, request.app.state.settings)
    database = cast(Database, request.app.state.database)
    ip = request.client.host if request.client else "unknown"
    limit = {
        "login": settings.auth_login_ip_limit,
        "signup": settings.auth_signup_ip_limit,
        "availability": settings.auth_availability_ip_limit,
    }[operation]
    limits = [(f"{operation}:ip:{ip}", limit)]
    if operation == "login" and login_id is not None:
        limits.append((f"login:account:{login_id}", settings.auth_login_account_limit))
    await consume(database, limits)
