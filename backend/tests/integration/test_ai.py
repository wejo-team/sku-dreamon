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
from sqlalchemy import func, select, update

from app.agents.tools import SourceTools
from app.agents.tracing import AiTraceContext
from app.agents.types import (
    AgentContext,
    ApplicantAssessmentPlan,
    ApplicantAssessmentSelection,
    AssessmentCriterionPlan,
    PreviousContext,
    RecommendationGate,
    RecommendationPlan,
    Resource,
    Selection,
)
from app.core.config import Settings
from app.core.db.base import Base
from app.core.exceptions import AppError
from app.core.http.handlers import register_error_handlers
from app.dependencies.auth import SESSION_COOKIE_NAME
from app.dependencies.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.models.ai_runs import AiRun
from app.models.applications import Application
from app.models.auth import AuthSession
from app.models.courses import Course, ProfileCourse
from app.models.profiles import Profile
from app.routers.ai import router
from app.schemas.ai import AssessmentKey, ChatStart
from app.schemas.course_import import CourseImport
from app.security.csrf import issue_csrf_token
from app.services.ai import AiService
from app.services.ai_sources import SourceReader
from app.services.courses import import_courses
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
        self.assessment_calls = 0
        self.write_calls = 0

    async def stream(
        self,
        tools: SourceTools,
        content: str,
        history: list[str],
        previous: PreviousContext,
        *,
        gate: RecommendationGate,
        trace_context: AiTraceContext | None = None,
    ) -> AsyncIterator[str]:
        plan = await self.plan(tools, content, history, await previous())
        await gate(plan)
        resources = [tools.observed[choice.key] for choice in plan.selections]
        async for part in self.write(plan, resources, content):
            yield part

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
        self.write_calls += 1
        yield "등록된 정보를 바탕으로 "
        await asyncio.sleep(0)
        yield "추천합니다."

    async def assess(
        self, tools: SourceTools, *, trace_context: AiTraceContext | None = None
    ) -> ApplicantAssessmentPlan:
        self.assessment_calls += 1
        tools.count_call()
        plan = await self.plan(tools, "현재 지원 자료로 검토해 주세요.", [], [])
        resources = [tools.observed[choice.key] for choice in plan.selections]
        remaining_keys: tuple[AssessmentKey, ...] = (
            "skills",
            "experience",
            "availability",
        )
        return ApplicantAssessmentPlan(
            summary="등록된 역할을 확인하고 나머지 사항은 대화로 확인해 주세요.",
            assessments=[
                ApplicantAssessmentSelection(
                    key=resource.reference.key,
                    criteria=[
                        AssessmentCriterionPlan(
                            key="role",
                            score=75,
                            information_status="sufficient",
                            summary="지원 역할이 등록되어 있어요.",
                            evidence_refs=["application.role"],
                        ),
                        *[
                            AssessmentCriterionPlan(
                                key=key,
                                score=None,
                                information_status="insufficient",
                                summary="직접 확인할 정보가 더 필요해요.",
                                evidence_refs=[],
                            )
                            for key in remaining_keys
                        ],
                    ],
                    questions=["이번 프로젝트에서 어떤 역할을 맡고 싶나요?"],
                )
                for resource in resources
            ],
        )


@pytest.fixture
async def ai_data(review_data: ApplicationData) -> ApplicationData:  # noqa: F811 -- pytest 의존 fixture
    data = review_data
    async with data.database.engine.begin() as connection:
        await connection.run_sync(
            lambda sync: Base.metadata.create_all(
                sync,
                [
                    Base.metadata.tables[name]
                    for name in ("ai_runs", "ai_conversations", "ai_messages")
                ],
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


@pytest.mark.parametrize("rich", [False, True])
async def test_chat_stream_result_integrity_and_public_revocation(
    ai_data: ApplicationData,
    rich: bool,
) -> None:
    data = ai_data
    driver = FakeDriver(data)
    body = payload()
    if rich:
        body["resultFormat"] = "rich"
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
        if rich:
            card = result["cards"][0]
            assert card["details"]["kind"] == "person"
            assert card["evidence"] == ["디자인 관심 분야 등록"]
            assert set(card["details"]) == {
                "kind",
                "skillCodes",
                "weeklyAvailabilityCode",
                "experienceState",
                "experienceBody",
                "introduction",
            }
        else:
            assert "details" not in result["cards"][0]
            assert "evidence" not in result["cards"][0]
        base = f"/api/v1/ai/requests/{body['requestId']}"
        status = await client.get(base)
        assert status.json()["data"]["status"] == "succeeded"
        assert "result" not in status.json()["data"]
        valid_body = {"attempt": 1, "result": result}
        assert (await client.post(base + "/validation", json=valid_body)).json()[
            "data"
        ]["valid"] is True
        if rich:
            altered = json.loads(json.dumps(result))
            altered["cards"][0]["details"]["introduction"] = "변조된 등록 사실"
            assert (
                await client.post(
                    base + "/validation", json={"attempt": 1, "result": altered}
                )
            ).status_code == 409
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


@pytest.mark.parametrize("rich", [False, True])
async def test_failed_retry_fences_attempt_and_preserves_message(
    ai_data: ApplicationData,
    rich: bool,
) -> None:
    driver = FakeDriver(ai_data)
    driver.fail_once = True
    body = payload()
    if rich:
        body["resultFormat"] = "rich"
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        first = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(first.text)[-1]["event"] == "error"
        assert "provider failure" not in first.text
        base = f"/api/v1/ai/requests/{body['requestId']}"
        switched = {**body}
        if rich:
            switched.pop("resultFormat")
        else:
            switched["resultFormat"] = "rich"
        assert (
            await client.post(
                base + "/retries/stream",
                json={"expectedAttempt": 1, "input": switched},
            )
        ).status_code == 409
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

    mutation_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def revoke() -> None:
        async with ai_data.database.session() as session:
            pid = await session.scalar(select(func.pg_backend_pid()))
            assert pid is not None
            mutation_pid.set_result(pid)
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == ai_data.stranger_id)
                .values(is_public=False)
            )
            await session.commit()

    mutation = asyncio.create_task(revoke())
    try:
        # 고정 sleep은 느린 연결 준비를 잠금 대기로 오인한다. UPDATE가 실제로
        # 전송 잠금을 기다리는 것을 확인한 뒤 다음 프레임으로 진행한다.
        async with asyncio.timeout(3):
            pid = await mutation_pid
            async with ai_data.database.session() as observer:
                while not await observer.scalar(  # noqa: ASYNC110 -- 외부 DB 잠금은 Event를 제공하지 않음
                    select(func.cardinality(func.pg_blocking_pids(pid)))
                ):
                    await asyncio.sleep(0.01)
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


async def test_publication_blocks_course_reimport_until_send_and_stops_next_chunk(
    ai_data: ApplicationData,
) -> None:
    catalog = CourseImport.model_validate(
        {
            "schema_version": "0.1.0",
            "courses": [
                {
                    "code": "GE1394",
                    "name": "AI리터러시와가치설계",
                    "aliases": [],
                    "departments": [],
                }
            ],
        }
    )
    async with ai_data.database.session() as session:
        await import_courses(session, catalog)
        course_id = await session.scalar(
            select(Course.course_id).where(Course.code == "GE1394")
        )
        assert course_id is not None
        session.add(ProfileCourse(account_id=ai_data.stranger_id, course_id=course_id))
        await session.commit()

    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    execution = await service.start(
        principal(ai_data, ai_data.applicant_id),
        "chat",
        ChatStart.model_validate(payload()),
    )
    stream = service.stream(execution)
    while b"event: answer.delta" not in await anext(stream):
        pass

    async def reimport() -> None:
        catalog.courses[0].name = "AI리터러시"
        async with ai_data.database.session() as session:
            await import_courses(session, catalog)

    mutation = asyncio.create_task(reimport())
    try:
        # 현재 프레임을 보내는 동안에는 그 근거가 된 공통 과목명도 바뀌지 않는다.
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(mutation), 0.1)
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


async def test_chat_archives_current_messages_once_without_history_api(
    ai_data: ApplicationData,
) -> None:
    from app.models.ai_chat import AiConversation, AiMessage

    driver = FakeDriver(ai_data)
    body = {**payload(), "history": ["과거 발화는 다시 저장하지 않는다"]}
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(response.text)[-1]["event"] == "done"
        assert (
            await client.post("/api/v1/ai/chat/stream", json=body)
        ).status_code == 409
        duplicate = {**body, "requestId": str(uuid4())}
        assert (
            await client.post("/api/v1/ai/chat/stream", json=duplicate)
        ).status_code == 409
        assert (await client.get("/api/v1/ai/conversations")).status_code == 404
    async with ai_data.database.session() as session:
        conversations = list(await session.scalars(select(AiConversation)))
        messages = list(
            await session.scalars(select(AiMessage).order_by(AiMessage.created_at))
        )
        assert len(conversations) == 1
        assert conversations[0].account_id == ai_data.applicant_id
        assert [m.role for m in messages] == ["user", "assistant"]
        assert [m.content for m in messages] == [
            body["content"],
            "등록된 정보를 바탕으로 추천합니다.",
        ]
        assert messages[1].attempt == 1
        assert messages[1].model == "gpt-6-luna"
        assert messages[1].source_references[0]["resource_id"] == str(
            ai_data.stranger_id
        )
        assert messages[0].source_references == []


async def test_chat_retry_archives_one_user_and_only_completed_answer(
    ai_data: ApplicationData,
) -> None:
    from app.models.ai_chat import AiMessage

    driver = FakeDriver(ai_data)
    driver.fail_once = True
    body = payload()
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        first = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(first.text)[-1]["event"] == "error"
        async with ai_data.database.session() as session:
            assert [m.role for m in await session.scalars(select(AiMessage))] == [
                "user"
            ]
        response = await client.post(
            f"/api/v1/ai/requests/{body['requestId']}/retries/stream",
            json={"expectedAttempt": 1, "input": body},
        )
        assert events(response.text)[-1]["event"] == "done"
    async with ai_data.database.session() as session:
        rows = list(await session.scalars(select(AiMessage).order_by(AiMessage.role)))
        assert len(rows) == 2
        assert rows[0].role == "assistant" and rows[0].attempt == 2
        assert rows[1].role == "user"


async def test_chat_archive_survives_run_cleanup_and_prevents_reexecution(
    ai_data: ApplicationData,
) -> None:
    from datetime import timedelta

    from app.models.ai_chat import AiMessage
    from app.repositories.ai_runs import expire_runs

    driver = FakeDriver(ai_data)
    body = payload()
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        assert (
            events((await client.post("/api/v1/ai/chat/stream", json=body)).text)[-1][
                "event"
            ]
            == "done"
        )
        async with ai_data.database.session() as session:
            await expire_runs(session, datetime.now(UTC) + timedelta(days=2))
            await session.commit()
            assert await session.get(AiRun, UUID(str(body["requestId"]))) is None
            assert len(list(await session.scalars(select(AiMessage)))) == 2
        assert (
            await client.post("/api/v1/ai/chat/stream", json=body)
        ).status_code == 409
        duplicate = {**body, "requestId": str(uuid4())}
        assert (
            await client.post("/api/v1/ai/chat/stream", json=duplicate)
        ).status_code == 409
        next_message = payload(UUID(str(body["conversationId"])))
        assert (
            events(
                (await client.post("/api/v1/ai/chat/stream", json=next_message)).text
            )[-1]["event"]
            == "done"
        )
    assert driver.plan_calls == 2


async def test_another_account_cannot_append_to_owned_conversation(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    body = payload()
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        await client.post("/api/v1/ai/chat/stream", json=body)
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        stolen = payload(UUID(str(body["conversationId"])))
        assert (
            await client.post("/api/v1/ai/chat/stream", json=stolen)
        ).status_code == 404
    assert driver.plan_calls == 1


async def test_answer_storage_failure_cannot_commit_success(
    ai_data: ApplicationData,
) -> None:
    from sqlalchemy import text

    from app.models.ai_chat import AiMessage

    async with ai_data.database.session() as session:
        connection = await session.connection()
        assert connection.sync_connection is not None
        schema = connection.sync_connection.get_execution_options()[
            "schema_translate_map"
        ][None]
        await session.execute(
            text(
                f'ALTER TABLE "{schema}".ai_messages ADD CONSTRAINT reject_answer '
                "CHECK (role != 'assistant')"
            )
        )
        await session.commit()
    body = payload()
    async with client_for(ai_data, FakeDriver(ai_data), ai_data.applicant_id) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(response.text)[-1]["event"] == "error"
        assert all(e["event"] != "done" for e in events(response.text))
    async with ai_data.database.session() as session:
        run = await session.get(AiRun, UUID(str(body["requestId"])))
        assert run is not None and run.status == "failed" and run.result_hash is None
        assert [m.role for m in await session.scalars(select(AiMessage))] == ["user"]


@pytest.mark.parametrize("outcome", ["failure", "disconnect", "revocation"])
async def test_partial_answers_are_not_archived(
    ai_data: ApplicationData,
    outcome: str,
) -> None:
    from app.models.ai_chat import AiMessage

    class PartialDriver(FakeDriver):
        async def write(
            self, plan: RecommendationPlan, resources: list[Resource], content: str
        ) -> AsyncIterator[str]:
            yield "완성되지 않은 답변"
            if outcome == "failure":
                raise RuntimeError("generation interrupted")
            if outcome == "revocation":
                async with ai_data.database.session() as session:
                    await session.execute(
                        update(Profile)
                        .where(Profile.profile_id == ai_data.stranger_id)
                        .values(is_public=False)
                    )
                    await session.commit()
            yield "후속 내용"

    service = AiService(ai_data.database, settings(), PartialDriver(ai_data))
    execution = await service.start(
        principal(ai_data, ai_data.applicant_id),
        "chat",
        ChatStart.model_validate(payload()),
    )
    stream = service.stream(execution)
    try:
        while b"event: answer.delta" not in await anext(stream):
            pass
        if outcome != "disconnect":
            remaining = [part async for part in stream]
            assert b"event: done" not in b"".join(remaining)
    finally:
        await stream.aclose()
    async with ai_data.database.session() as session:
        assert [m.role for m in await session.scalars(select(AiMessage))] == ["user"]


async def test_concurrent_accounts_cannot_claim_same_conversation(
    ai_data: ApplicationData,
) -> None:
    from app.models.ai_chat import AiConversation, AiMessage

    conversation_id = uuid4()
    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    results = await asyncio.gather(
        *(
            service.start(
                principal(ai_data, account_id),
                "chat",
                ChatStart.model_validate(payload(conversation_id)),
            )
            for account_id in (ai_data.applicant_id, ai_data.leader_id)
        ),
        return_exceptions=True,
    )
    assert (
        len([r for r in results if isinstance(r, AppError) and r.status_code == 404])
        == 1
    )
    async with ai_data.database.session() as session:
        assert len(list(await session.scalars(select(AiConversation)))) == 1
        assert len(list(await session.scalars(select(AiMessage)))) == 1
        assert len(list(await session.scalars(select(AiRun)))) == 1


async def test_user_storage_failure_rolls_back_conversation_and_run(
    ai_data: ApplicationData,
) -> None:
    from sqlalchemy import text

    from app.models.ai_chat import AiConversation, AiMessage

    async with ai_data.database.session() as session:
        connection = await session.connection()
        assert connection.sync_connection is not None
        schema = connection.sync_connection.get_execution_options()[
            "schema_translate_map"
        ][None]
        await session.execute(
            text(
                f'ALTER TABLE "{schema}".ai_messages ADD CONSTRAINT reject_user '
                "CHECK (role != 'user')"
            )
        )
        await session.commit()
    driver = FakeDriver(ai_data)
    service = AiService(ai_data.database, settings(), driver)
    with pytest.raises(AppError) as error:
        await service.start(
            principal(ai_data, ai_data.applicant_id),
            "chat",
            ChatStart.model_validate(payload()),
        )
    async with ai_data.database.session() as session:
        assert list(await session.scalars(select(AiConversation))) == []
        assert list(await session.scalars(select(AiMessage))) == []
        assert list(await session.scalars(select(AiRun))) == []
    assert error.value.status_code == 503
    assert driver.plan_calls == 0


async def test_empty_chat_answer_is_archived_but_applicant_review_is_not(
    ai_data: ApplicationData,
) -> None:
    from app.models.ai_chat import AiMessage

    class EmptyDriver(FakeDriver):
        async def plan(
            self,
            tools: SourceTools,
            content: str,
            history: list[str],
            previous: list[dict[str, object]],
        ) -> RecommendationPlan:
            return RecommendationPlan(
                intent="empty", selections=[], guidance="현재 후보 없음"
            )

    body = payload()
    async with client_for(
        ai_data, EmptyDriver(ai_data), ai_data.applicant_id
    ) as client:
        response = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(response.text)[-1]["status"] == "empty"
    async with client_for(ai_data, FakeDriver(ai_data), ai_data.leader_id) as client:
        response = await client.post(
            f"/api/v1/applications/{ai_data.application_id}/ai-reviews/stream",
            json={"requestId": str(uuid4())},
        )
        assert events(response.text)[-1]["event"] == "done"
    async with ai_data.database.session() as session:
        rows = list(await session.scalars(select(AiMessage)))
        assert len(rows) == 2
        assert all(row.request_id == UUID(str(body["requestId"])) for row in rows)


async def test_course_context_uses_current_catalog_and_existing_visibility(
    ai_data: ApplicationData,
) -> None:
    async with ai_data.database.session() as session:
        course = Course(code="GE1394", name="AI리터러시와가치설계")
        session.add(course)
        await session.flush()
        session.add(
            ProfileCourse(account_id=ai_data.applicant_id, course_id=course.course_id)
        )
        await session.execute(
            update(Profile)
            .where(Profile.profile_id == ai_data.applicant_id)
            .values(is_public=False)
        )
        await session.commit()

    reader = SourceReader(
        ai_data.database,
        AgentContext(
            principal=principal(ai_data, ai_data.leader_id),
            purpose="applicant_review",
            application_id=ai_data.application_id,
        ),
    )
    first = await reader.get("application", ai_data.application_id)
    first_profile = first.facts["profile"]
    assert isinstance(first_profile, dict)
    assert first_profile["courses"] == [
        {"code": "GE1394", "name": "AI리터러시와가치설계"}
    ]
    public_reader = SourceReader(
        ai_data.database,
        AgentContext(principal=principal(ai_data, ai_data.leader_id), purpose="chat"),
    )
    with pytest.raises(AppError) as denied:
        await public_reader.get("person", ai_data.applicant_id)
    assert denied.value.status_code == 404

    async with ai_data.database.session() as session:
        await session.execute(
            update(Course).where(Course.code == "GE1394").values(name="AI리터러시")
        )
        await session.commit()
    current = await reader.get("application", ai_data.application_id)
    current_profile = current.facts["profile"]
    assert isinstance(current_profile, dict)
    assert current_profile["courses"][0]["name"] == "AI리터러시"
    assert current.reference.fingerprint != first.reference.fingerprint


@pytest.mark.parametrize("purpose", ["review", "recommendation"])
async def test_completed_applicant_result_is_stale_after_course_reimport(
    ai_data: ApplicationData, purpose: str
) -> None:
    catalog = CourseImport.model_validate(
        {
            "schema_version": "0.1.0",
            "courses": [
                {
                    "code": "GE1394",
                    "name": "AI리터러시와가치설계",
                    "aliases": [],
                    "departments": [],
                }
            ],
        }
    )
    async with ai_data.database.session() as session:
        await import_courses(session, catalog)
        course_id = await session.scalar(
            select(Course.course_id).where(Course.code == "GE1394")
        )
        assert course_id is not None
        session.add(ProfileCourse(account_id=ai_data.applicant_id, course_id=course_id))
        await session.commit()

    request_id = uuid4()
    endpoint = (
        f"/api/v1/applications/{ai_data.application_id}/ai-reviews/stream"
        if purpose == "review"
        else f"/api/v1/teams/{ai_data.team_id}/applicant-recommendations/stream"
    )
    async with client_for(ai_data, FakeDriver(ai_data), ai_data.leader_id) as client:
        response = await client.post(endpoint, json={"requestId": str(request_id)})
        stream = events(response.text)
        assert stream[-1]["event"] == "done", response.text
        result = stream[-2]["result"]
        assert isinstance(result, dict)
        validation_path = f"/api/v1/ai/requests/{request_id}/validation"
        validation_body = {"attempt": 1, "result": result}
        unchanged = await client.post(validation_path, json=validation_body)
        assert unchanged.json()["data"]["result"]["isStale"] is False

        catalog.courses[0].name = "AI리터러시"
        async with ai_data.database.session() as session:
            assert await import_courses(session, catalog) == {
                "created": 0,
                "updated": 1,
                "unchanged": 0,
            }
            assert (
                await session.scalar(
                    select(Profile.version).where(
                        Profile.profile_id == ai_data.applicant_id
                    )
                )
                == 1
            )

        validation = await client.post(validation_path, json=validation_body)
        assert validation.status_code == 200
        data = validation.json()["data"]
        assert data["valid"] is True
        assert data["result"]["isStale"] is True
        version = (
            data["result"]["profileVersions"][0]
            if purpose == "review"
            else data["result"]["candidates"][0]["profileVersion"]
        )
        assert version["usedVersion"] == version["currentVersion"] == "1"
