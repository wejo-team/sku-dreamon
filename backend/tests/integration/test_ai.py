"""실제 PostgreSQL과 가짜 모델로 AI 권한·실행·전송 계약을 검증한다."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, update

from app.agents.tools import SourceTools
from app.agents.types import RecommendationPlan, Resource, Selection
from app.core.config import Settings
from app.core.db.base import Base
from app.core.exceptions import AppError
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.models.ai_runs import AiRun
from app.models.applications import Application
from app.models.auth import AuthSession
from app.models.profiles import Profile
from app.routers.ai import router
from app.schemas.ai import ChatStart
from app.security.csrf import issue_csrf_token
from app.services.ai import AiService
from app.services.sessions import SessionPrincipal
from tests.integration.application_review_support import review_data  # noqa: F401 -- pytest fixture
from tests.integration.application_support import (
    ORIGIN,
    SIGNING_KEY,
    ApplicationData,
    application_data,  # noqa: F401 -- pytest fixture
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


class FakeDriver:
    def __init__(self, data: ApplicationData) -> None:
        self.data = data
        self.fail_once = False
        self.unknown_id = False
        self.block = False
        self.entered = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.plan_calls = 0

    async def plan(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: list[dict[str, object]],
    ) -> RecommendationPlan:
        self.plan_calls += 1
        self.entered.set()
        if self.block:
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled.set()
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("provider failure must not leak")
        context = tools.reader.context
        if context.purpose == "chat":
            resource = await tools.load("person", self.data.stranger_id)
        else:
            resource = await tools.load("application", self.data.application_id)
            if (
                context.purpose == "applicant_recommendation"
                and not resource.is_selection_candidate
            ):
                return RecommendationPlan(
                    intent="empty", selections=[], guidance="현재 유효 후보 없음"
                )
        key = f"person:{uuid4()}" if self.unknown_id else resource.reference.key
        return RecommendationPlan(
            intent="recommend",
            selections=[
                Selection(
                    key=key,
                    reason="등록된 디자인 관심 분야",
                    evidence=["디자인 관심 분야 등록"],
                )
            ],
            guidance="현재 자료를 확인하세요.",
        )

    async def write(
        self, plan: RecommendationPlan, resources: list[Resource], content: str
    ) -> AsyncIterator[str]:
        yield "등록된 정보를 바탕으로 "
        await asyncio.sleep(0)
        yield "추천합니다."


@pytest.fixture
async def ai_data(review_data: ApplicationData) -> ApplicationData:  # noqa: F811 -- pytest 의존 fixture
    data = review_data
    async with data.database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync, [Base.metadata.tables["ai_runs"]]
            )
        )
    async with data.database.session() as session:
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == data.stranger_id)
            .values(is_public=True)
        )
        await session.commit()
    return data


def principal(data: ApplicationData, account_id: UUID) -> SessionPrincipal:
    session = data.sessions[account_id].session
    return SessionPrincipal(
        session.auth_session_id, account_id, session.token_hash, session.expires_at
    )


def settings() -> Settings:
    return Settings(
        csrf_signing_key=SecretStr(SIGNING_KEY),
        auth_allowed_origins=(ORIGIN,),
        _env_file=None,
    )


@asynccontextmanager
async def client_for(
    data: ApplicationData, driver: FakeDriver, account_id: UUID | None
) -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.state.database, app.state.settings, app.state.ai_driver = (
        data.database,
        settings(),
        driver,
    )
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
        if account_id is not None:
            issued = data.sessions[account_id]
            client.cookies.set(SESSION_COOKIE_NAME, issued.token)
            token = issue_csrf_token(SIGNING_KEY, issued.session.token_hash)
            client.cookies.set(CSRF_COOKIE_NAME, token)
            client.headers[CSRF_HEADER_NAME] = token
            client.headers["Origin"] = ORIGIN
        yield client


def payload(conversation_id: UUID | None = None) -> dict[str, object]:
    return {
        "requestId": str(uuid4()),
        "clientMessageId": str(uuid4()),
        "conversationId": str(conversation_id or uuid4()),
        "content": "디자인에 관심 있는 사람 찾아줘",
    }


def events(text: str) -> list[dict[str, object]]:
    result = []
    for frame in text.split("\n\n"):
        if frame.startswith("event: "):
            name, line = frame.split("\n", 1)
            result.append({"event": name[7:], **json.loads(line[6:])})
    return result


async def test_chat_stream_result_integrity_and_public_revocation(
    ai_data: ApplicationData,
) -> None:
    data = ai_data
    driver = FakeDriver(data)
    body = payload()
    async with client_for(data, driver, data.applicant_id) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=body)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        assert response.headers["cache-control"] == "no-store"
        stream = events(response.text)
        assert [event["event"] for event in stream][-4:] == [
            "answer.delta",
            "answer.delta",
            "result",
            "done",
        ]
        assert [event["sequence"] for event in stream] == list(
            range(1, len(stream) + 1)
        )
        result = stream[-2]["result"]
        assert isinstance(result, dict)
        assert result["answer"] == "등록된 정보를 바탕으로 추천합니다."
        assert result["cards"][0]["resourceId"] == str(data.stranger_id)
        assert result["cards"][0]["isDemo"] is False
        base = f"/api/v1/ai/requests/{body['requestId']}"
        status = await client.get(base)
        assert status.json()["data"]["status"] == "succeeded"
        assert "result" not in status.json()["data"]
        valid_body = {"attempt": 1, "result": result}
        assert (await client.post(base + "/validation", json=valid_body)).json()[
            "data"
        ]["valid"] is True
        forged = {**result, "answer": "변조된 답변"}
        assert (
            await client.post(
                base + "/validation", json={"attempt": 1, "result": forged}
            )
        ).status_code == 409
        assert (
            await client.post("/api/v1/ai/chat/stream", json=body)
        ).status_code == 409
        assert driver.plan_calls == 1
        async with data.database.session() as session:
            row = await session.scalar(
                select(AiRun).where(AiRun.ai_run_id == UUID(str(body["requestId"])))
            )
            assert row is not None
            stored = json.dumps(row.references, ensure_ascii=False)
            assert "검토 사용자" not in stored
            assert "등록된" not in stored
            assert row.result_hash is not None
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == data.stranger_id)
                .values(is_public=False)
            )
            await session.commit()
        invalid = await client.post(base + "/validation", json=valid_body)
        assert invalid.json()["data"] == {"valid": False, "result": None}


async def test_auth_csrf_and_other_owner_are_enforced(ai_data: ApplicationData) -> None:
    driver = FakeDriver(ai_data)
    async with client_for(ai_data, driver, None) as client:
        assert (
            await client.post("/api/v1/ai/chat/stream", json=payload())
        ).status_code == 401
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        client.headers[CSRF_HEADER_NAME] = "invalid"
        assert (
            await client.post("/api/v1/ai/chat/stream", json=payload())
        ).status_code == 403
    async with client_for(ai_data, driver, ai_data.stranger_id) as client:
        response = await client.post(
            f"/api/v1/applications/{ai_data.application_id}/ai-reviews/stream",
            json={"requestId": str(uuid4())},
        )
        assert response.status_code == 404
    assert driver.plan_calls == 0


async def test_private_applicant_review_staleness_and_read_only(
    ai_data: ApplicationData,
) -> None:
    data = ai_data
    request_id = uuid4()
    async with client_for(data, FakeDriver(data), data.leader_id) as client:
        response = await client.post(
            f"/api/v1/applications/{data.application_id}/ai-reviews/stream",
            json={"requestId": str(request_id)},
        )
        stream = events(response.text)
        assert stream[-1]["event"] == "done", response.text
        result = stream[-2]["result"]
        assert isinstance(result, dict)
        assert result["profileVersions"][0]["usedVersion"] == "1"
        async with data.database.session() as session:
            application = await session.get(Application, data.application_id)
            assert application is not None and application.status == "submitted"
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == data.applicant_id)
                .values(version=2, introduction="새 경험")
            )
            await session.commit()
        validation = await client.post(
            f"/api/v1/ai/requests/{request_id}/validation",
            json={"attempt": 1, "result": result},
        )
        updated = validation.json()["data"]["result"]
        assert updated["isStale"] is True
        assert updated["profileVersions"][0]["usedVersion"] == "1"
        assert updated["profileVersions"][0]["currentVersion"] == "2"


async def test_failed_retry_fences_attempt_and_preserves_message(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.fail_once = True
    body = payload()
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        first = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(first.text)[-1]["event"] == "error"
        assert "provider failure" not in first.text
        base = f"/api/v1/ai/requests/{body['requestId']}"
        second = await client.post(
            base + "/retries/stream", json={"expectedAttempt": 1, "input": body}
        )
        assert events(second.text)[-1]["event"] == "done", second.text
        assert all(item["attempt"] == 2 for item in events(second.text))
        assert (
            await client.put(base + "/cancellation", json={"expectedAttempt": 1})
        ).status_code == 409
        assert (
            await client.put(base + "/cancellation", json={"expectedAttempt": 2})
        ).json()["data"]["status"] == "succeeded"
        assert (
            await client.post(
                base + "/retries/stream", json={"expectedAttempt": 1, "input": body}
            )
        ).status_code == 409


async def test_overlapping_requests_share_a_single_pending_scope(
    ai_data: ApplicationData,
) -> None:
    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    owner = principal(ai_data, ai_data.applicant_id)
    conversation_id = uuid4()
    results = await asyncio.gather(
        *(
            service.start(
                owner, "chat", ChatStart.model_validate(payload(conversation_id))
            )
            for _ in range(2)
        ),
        return_exceptions=True,
    )
    failures = [value for value in results if isinstance(value, AppError)]
    assert len(failures) == 1 and failures[0].code == "REQUEST_ALREADY_RUNNING"


async def test_cancel_interrupts_model_without_holding_database_locks(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.block = True
    service = AiService(ai_data.database, settings(), driver)
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))

    async def consume() -> bytes:
        return b"".join([chunk async for chunk in service.stream(execution)])

    task = asyncio.create_task(consume())
    await asyncio.wait_for(driver.entered.wait(), 3)
    await asyncio.wait_for(service.runs.cancel(owner, execution.request_id, 1), 3)
    text = (await asyncio.wait_for(task, 3)).decode()
    assert events(text)[-1]["event"] == "canceled"
    assert driver.cancelled.is_set()
    assert "answer.delta" not in text


async def test_logout_during_model_execution_invalidates_response(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.block = True
    service = AiService(ai_data.database, settings(), driver)
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))

    async def consume() -> bytes:
        return b"".join([chunk async for chunk in service.stream(execution)])

    task = asyncio.create_task(consume())
    await asyncio.wait_for(driver.entered.wait(), 3)
    async with ai_data.database.session() as session:
        await session.execute(
            update(AuthSession)
            .where(AuthSession.auth_session_id == owner.auth_session_id)
            .values(revoked_at=datetime.now(UTC))
        )
        await session.commit()
    stream = events((await asyncio.wait_for(task, 3)).decode())
    assert stream[-1]["event"] == "invalidated"
    assert not any(item["event"] == "answer.delta" for item in stream)


async def test_unverified_model_id_never_reaches_answer_stream(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.unknown_id = True
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=payload())
        assert events(response.text)[-1]["event"] == "error"
        assert "answer.delta" not in response.text


async def test_publication_blocks_revocation_until_send_and_stops_next_chunk(
    ai_data: ApplicationData,
) -> None:
    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    execution = await service.start(
        principal(ai_data, ai_data.applicant_id),
        "chat",
        ChatStart.model_validate(payload()),
    )
    stream = service.stream(execution)
    while True:
        frame = await anext(stream)
        if b"event: answer.delta" in frame:
            break

    async def revoke() -> None:
        async with ai_data.database.session() as session:
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == ai_data.stranger_id)
                .values(is_public=False)
            )
            await session.commit()

    mutation = asyncio.create_task(revoke())
    try:
        await asyncio.sleep(0.05)
        assert not mutation.done(), (
            "공개 변경은 현재 전송 경계가 닫힐 때까지 기다려야 한다."
        )
        following = await anext(stream)
        await asyncio.wait_for(mutation, 3)
        assert b"event: invalidated" in following
        assert b"answer.delta" not in following
    finally:
        await stream.aclose()
        if not mutation.done():
            mutation.cancel()
        await asyncio.gather(mutation, return_exceptions=True)


async def test_completed_result_and_cancellation_are_owned_by_current_session(
    ai_data: ApplicationData,
) -> None:
    body = payload()
    driver = FakeDriver(ai_data)
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(response.text)[-1]["event"] == "done"
    async with client_for(ai_data, driver, ai_data.stranger_id) as client:
        base = f"/api/v1/ai/requests/{body['requestId']}"
        assert (await client.get(base)).status_code == 404
        assert (
            await client.put(base + "/cancellation", json={"expectedAttempt": 1})
        ).status_code == 404


async def test_candidate_recommendation_excludes_canceled_applications(
    ai_data: ApplicationData,
) -> None:
    async with ai_data.database.session() as session:
        await session.execute(
            update(Application)
            .where(Application.application_id == ai_data.application_id)
            .values(status="canceled")
        )
        await session.commit()
    async with client_for(ai_data, FakeDriver(ai_data), ai_data.leader_id) as client:
        response = await client.post(
            f"/api/v1/teams/{ai_data.team_id}/applicant-recommendations/stream",
            json={"requestId": str(uuid4())},
        )
        stream = events(response.text)
        assert stream[-1]["event"] == "done", response.text
        assert stream[-1]["status"] == "empty"
        result = stream[-2]["result"]
        assert isinstance(result, dict) and result["candidates"] == []


async def test_expired_pending_execution_is_retryable_and_retention_cleanup_removes_it(
    ai_data: ApplicationData,
) -> None:
    from datetime import timedelta

    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))
    async with ai_data.database.session() as session:
        await session.execute(
            update(AiRun)
            .where(AiRun.ai_run_id == execution.request_id)
            .values(deadline_at=datetime.now(UTC))
        )
        await session.commit()
    run = await service.runs.get(owner, execution.request_id)
    assert run.status == "failed" and run.failure_code == "temporary_failure"
    async with ai_data.database.session() as session:
        now = datetime.now(UTC)
        await session.execute(
            update(AiRun)
            .where(AiRun.ai_run_id == execution.request_id)
            .values(
                created_at=now - timedelta(days=3),
                deadline_at=now - timedelta(days=2),
                expires_at=now - timedelta(days=1),
            )
        )
        await session.commit()
    await service.runs.clean_expired()
    async with ai_data.database.session() as session:
        assert await session.get(AiRun, execution.request_id) is None


async def test_disconnected_stream_releases_publication_locks_and_cancels_run(
    ai_data: ApplicationData,
) -> None:
    from starlette.types import Message

    from app.routers.ai import AiStreamResponse

    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))
    response = AiStreamResponse(service.stream(execution))

    async def send(message: Message) -> None:
        if message["type"] == "http.response.body" and b"answer.delta" in message.get(
            "body", b""
        ):
            raise OSError("client disconnected")

    with pytest.raises(ExceptionGroup):
        await response.stream_response(send)
    run = await service.runs.get(owner, execution.request_id)
    assert run.status == "canceled"

    async def change_profile() -> None:
        async with ai_data.database.session() as session:
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == ai_data.stranger_id)
                .values(is_public=False)
            )
            await session.commit()

    await asyncio.wait_for(change_profile(), 2)


async def test_old_cleanup_cannot_cancel_a_new_retry(ai_data: ApplicationData) -> None:
    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    owner = principal(ai_data, ai_data.applicant_id)
    body = ChatStart.model_validate(payload())
    first = await service.start(owner, "chat", body)
    assert await service.runs.finish(
        first, status="failed", failure_code="temporary_failure"
    )
    second = await service.start(owner, "chat", body, expected_attempt=1)
    assert second.attempt == 2
    assert not await service.runs.finish(first, status="canceled")
    run = await service.runs.get(owner, first.request_id)
    assert run.status == "pending" and run.attempt == 2
    with pytest.raises(AppError) as error:
        await service.runs.cancel(owner, first.request_id, 1)
    assert error.value.code == "ATTEMPT_CONFLICT"


async def test_asgi_disconnect_cancels_the_pending_run(
    ai_data: ApplicationData,
) -> None:
    from starlette.types import Message, Scope

    from app.routers.ai import AiStreamResponse

    driver = FakeDriver(ai_data)
    driver.block = True
    service = AiService(ai_data.database, settings(), driver)
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))
    response = AiStreamResponse(service.stream(execution))

    async def receive() -> Message:
        await driver.entered.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        pass

    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.0"}}
    await asyncio.wait_for(response(scope, receive, send), 3)
    run = await service.runs.get(owner, execution.request_id)
    assert run.status == "canceled"
    assert driver.cancelled.is_set()


async def test_failed_initial_headers_do_not_leave_an_unstarted_run_pending(
    ai_data: ApplicationData,
) -> None:
    from starlette.types import Message, Scope

    from app.routers.ai import stream_response

    driver = FakeDriver(ai_data)
    service = AiService(ai_data.database, settings(), driver)
    owner = principal(ai_data, ai_data.applicant_id)
    execution = await service.start(owner, "chat", ChatStart.model_validate(payload()))
    response = stream_response(service, execution)

    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        raise OSError("closed before headers")

    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(OSError):
        await response(scope, receive, send)
    assert (await service.runs.get(owner, execution.request_id)).status == "canceled"
    assert driver.plan_calls == 0
