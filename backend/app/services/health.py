"""외부 모델 요청 없이 로컬 설정·보안 자원과 DB의 준비 상태를 판정한다."""

import asyncio

from app.core.config import Settings
from app.core.db.revisions import COMPATIBLE_SCHEMA_REVISIONS
from app.core.db.session import Database
from app.repositories.health import probe_database
from app.security.passwords import PasswordBlocklist


def ai_client_ready(driver: object | None) -> bool:
    """이미 생성된 SDK client의 로컬 상태만 확인하고 네트워크는 사용하지 않는다."""
    model = getattr(driver, "model", None)
    client = getattr(model, "root_async_client", None)
    closed = getattr(client, "is_closed", None)
    return client is not None and callable(closed) and not closed()


def _consume_probe_result(task: asyncio.Task[frozenset[str]]) -> None:
    if not task.cancelled():
        task.exception()


class ReadinessProbe:
    """앱이 한 개의 DB 검사와 제한 시간 이후의 정리까지 소유한다."""

    def __init__(self) -> None:
        self._task: asyncio.Task[frozenset[str]] | None = None
        self._closing = False

    async def revisions(
        self, database: Database, seconds: float
    ) -> frozenset[str] | None:
        if self._closing or (self._task is not None and not self._task.done()):
            return None

        async def probe() -> frozenset[str]:
            async with database.session() as session:
                return await probe_database(session)

        task = asyncio.create_task(probe())
        self._task = task
        task.add_done_callback(_consume_probe_result)
        try:
            # wait_for·timeout은 취소 뒤 세션 정리를 기다려 응답 예산을 넘길 수 있다.
            # 정리가 끝나기 전의 다음 요청은 새 task를 만들지 않고 503을 받는다.
            done, _ = await asyncio.wait({task}, timeout=seconds)
            return task.result() if done else None
        finally:
            if not task.done():
                task.cancel()

    async def close(self, seconds: float) -> bool:
        """종료 한도까지 기존 검사를 취소·회수하고 미완료 여부를 반환한다."""
        self._closing = True
        task = self._task
        if task is None or task.done():
            return True
        if not task.cancelling():
            task.cancel()
        done, _ = await asyncio.wait({task}, timeout=seconds)
        if not done:
            task.cancel()
        return bool(done)


async def is_ready(
    settings: Settings,
    database: Database | None,
    blocklist: PasswordBlocklist | None,
    driver: object | None,
    probe: ReadinessProbe,
) -> bool:
    try:
        # Settings는 앱 수명 동안 공유되므로 검사 시에도 현재 값을 재검증한다.
        settings = Settings(_env_file=None, **settings.model_dump())
        settings.require_http_configuration()
        if (
            database is None
            or settings.csrf_signing_key is None
            or not settings.auth_allowed_origins
            or settings.password_blocklist_path is None
            or blocklist is None
            or blocklist.entry_count < 1
            or not blocklist.version.strip()
            or blocklist.version != settings.password_blocklist_version
            or (
                (settings.ai_enabled or settings.ai_required)
                and not ai_client_ready(driver)
            )
        ):
            return False
        revisions = await probe.revisions(database, settings.readiness_timeout_seconds)
        return (
            revisions is not None
            and len(revisions) == 1
            and revisions <= COMPATIBLE_SCHEMA_REVISIONS
        )
    except Exception:
        # 연결·schema·보안 자원의 실패 원문에는 접속 정보가 포함될 수 있다.
        return False
