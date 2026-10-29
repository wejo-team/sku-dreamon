"""실제 행 잠금으로 지연 정리와 원래 deadline의 복구 계약을 검증한다."""

import asyncio
from datetime import datetime, timedelta, tzinfo

import pytest
from sqlalchemy import update

from app.cli import ai_runs as cleanup_cli
from app.core.config import Settings
from app.core.db.session import Database
from app.models.ai_runs import AiRun
from app.repositories import ai_runs as repository
from app.schemas.ai import ChatStart
from app.services import ai_runs as run_module
from app.services.ai import AiService
from tests.integration.application_review_support import review_data  # noqa: F401 -- fixture
from tests.integration.application_support import (
    ApplicationData,
    application_data,  # noqa: F401 -- fixture
)
from tests.integration.test_ai import (
    FakeDriver,
    ai_data,  # noqa: F401 -- fixture
    events,
    payload,
    principal,
    settings,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest.mark.parametrize("recovery", ["status", "cli"])
async def test_locked_failure_defers_to_original_deadline_then_recovers(
    ai_data: ApplicationData,  # noqa: F811 -- pytest 의존 fixture
    recovery: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configuration = settings().model_copy(update={"ai_cleanup_timeout_seconds": 0.1})
    driver = FakeDriver(ai_data)
    driver.fail_once = True
    service = AiService(ai_data.database, configuration, driver)
    owner = principal(ai_data, ai_data.applicant_id)
    body = ChatStart.model_validate(payload())
    first = await service.start(owner, "chat", body)

    # finish의 SELECT FOR UPDATE를 실제 다른 연결이 막는다. 쿼리 mock으로
    # timeout만 흉내 내지 않고 취소·rollback 후 행과 풀을 다시 사용한다.
    async with ai_data.database.session() as blocker:
        locked = await repository.get_run(blocker, first.request_id, lock=True)
        assert locked is not None
        deadline, retention = locked.deadline_at, locked.expires_at
        started = asyncio.get_running_loop().time()
        chunks = await asyncio.wait_for(_collect(service, first), timeout=1)
        assert asyncio.get_running_loop().time() - started < 0.7
        stream = events(chunks.decode())
        assert stream[-1]["event"] == "error"
        assert not any(frame["event"] in ("result", "done") for frame in stream)
        async with ai_data.database.session() as observer:
            pending = await observer.get(AiRun, first.request_id)
            assert pending is not None
            assert pending.status == "pending"
            assert pending.deadline_at == deadline and pending.expires_at == retention
        await blocker.rollback()

    # 응답 종료가 실행 기한을 앞당기거나 새 5초/24시간 기한을 만들지 않는다.
    assert (await service.runs.get(owner, first.request_id)).status == "pending"
    moment = deadline

    class Clock:
        @staticmethod
        def now(tz: tzinfo | None = None) -> datetime:
            return moment if tz is not None else moment.replace(tzinfo=None)

    monkeypatch.setattr(run_module, "datetime", Clock)
    if recovery == "status":
        failed = await service.runs.get(owner, first.request_id)
    else:
        # 기존 CLI 진입점을 호출하되 런타임 파일·실제 자격 증명은 읽지 않는다.
        def database_for_cli(url: str, *, settings: Settings) -> Database:
            return ai_data.database

        monkeypatch.setattr(cleanup_cli, "Settings", lambda: configuration)
        monkeypatch.setattr(cleanup_cli, "create_database", database_for_cli)
        await cleanup_cli.cleanup()
        async with ai_data.database.session() as session:
            failed_row = await session.get(AiRun, first.request_id)
            assert failed_row is not None
            failed = failed_row
    assert failed.status == "failed" and failed.failure_code == "temporary_failure"
    assert failed.deadline_at == deadline and failed.expires_at == retention

    second = await service.start(owner, "chat", body, expected_attempt=first.attempt)
    assert second.attempt == 2
    assert not await service.runs.finish(first, status="canceled")
    current = await service.runs.get(owner, first.request_id)
    assert current.status == "pending" and current.attempt == second.attempt
    result = events((await _collect(service, second)).decode())
    assert result[-1]["event"] == "done"
    assert result[-1]["status"] == "succeeded"
    await service.close_stream(second)
    assert not await service.runs.finish(first, status="canceled")
    assert (await service.runs.get(owner, first.request_id)).status == "succeeded"

    if recovery == "cli":
        # 실행 메타데이터의 물리 삭제도 CLI의 기존 expires_at을 사용한다.
        moment = retention + timedelta(seconds=1)
        async with ai_data.database.session() as session:
            await session.execute(
                update(AiRun)
                .where(AiRun.ai_run_id == first.request_id)
                .values(expires_at=retention)
            )
            await session.commit()
        await cleanup_cli.cleanup()
        async with ai_data.database.session() as session:
            assert await session.get(AiRun, first.request_id) is None


async def _collect(service: AiService, execution: run_module.Execution) -> bytes:
    return b"".join([chunk async for chunk in service.stream(execution)])
