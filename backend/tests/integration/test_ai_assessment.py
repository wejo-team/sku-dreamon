"""지원자 평가의 완성 JSON·권한·근거·취소·재시도 계약을 검사한다."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.agents.tools import SourceTools
from app.agents.tracing import AiTraceContext
from app.agents.types import ApplicantAssessmentPlan
from app.dependencies.csrf import CSRF_HEADER_NAME
from app.models.ai_chat import AiMessage
from app.models.ai_runs import AiRun
from app.models.applications import Application
from app.models.auth import AuthSession
from app.models.profiles import Profile
from app.routers.ai import json_response
from app.schemas.ai import TargetStart
from app.services.ai import AiService
from tests.integration import test_ai as ai_support
from tests.integration.application_review_support import review_data  # noqa: F401 -- pytest fixture
from tests.integration.application_support import (
    ApplicationData,
    application_data,  # noqa: F401 -- pytest fixture
)
from tests.integration.test_ai import (
    FakeDriver,
    client_for,
    events,
    payload,
    principal,
    settings,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]
ai_data = ai_support.ai_data


def endpoint(data: ApplicationData, purpose: str) -> str:
    if purpose == "review":
        return f"/api/v1/applications/{data.application_id}/ai-reviews"
    return f"/api/v1/teams/{data.team_id}/applicant-recommendations"


@pytest.mark.parametrize("purpose", ["review", "recommendation"])
async def test_applicant_json_is_complete_verified_and_not_archived(
    ai_data: ApplicationData, purpose: str
) -> None:
    driver = FakeDriver(ai_data)
    request_id = uuid4()
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        response = await client.post(
            endpoint(ai_data, purpose), json={"requestId": str(request_id)}
        )
        assert response.status_code == 200, response.text
        assert response.headers["content-type"].startswith("application/json")
        assert response.headers["cache-control"] == "no-store"
        data = response.json()["data"]
        assert data["requestId"] == str(request_id)
        assert data["attempt"] == 1 and data["status"] == "succeeded"
        result = data["result"]
        assert result["schemaVersion"] == 3
        candidate = result if purpose == "review" else result["candidates"][0]
        assessment = candidate["assessment"]
        assert {item["key"] for item in assessment["criteria"]} == {
            "role",
            "skills",
            "experience",
            "availability",
        }
        role = next(item for item in assessment["criteria"] if item["key"] == "role")
        assert role["score"] == 75
        assert role["informationStatus"] == "sufficient"
        assert role["evidence"][0]["source"] == "application.role"
        assert role["evidence"][0]["text"]
        assert assessment["questions"] == ["이번 프로젝트에서 어떤 역할을 맡고 싶나요?"]
        assert "state" not in str(assessment)
        assert all(
            item["score"] is None and item["informationStatus"] == "insufficient"
            for item in assessment["criteria"]
            if item["key"] != "role"
        )
        base = f"/api/v1/ai/requests/{request_id}"
        assert "result" not in (await client.get(base)).json()["data"]
        assert (
            await client.post(
                base + "/validation", json={"attempt": 1, "result": result}
            )
        ).json()["data"]["valid"] is True
        assert (
            await client.post(
                base + "/validation",
                json={"attempt": 1, "result": {**result, "schemaVersion": 2}},
            )
        ).status_code == 422
        role["evidence"][0]["text"] = "검증하지 않은 경력"
        assert (
            await client.post(
                base + "/validation", json={"attempt": 1, "result": result}
            )
        ).status_code == 409

    assert driver.assessment_calls == 1
    assert driver.write_calls == 0
    async with ai_data.database.session() as session:
        application = await session.get(Application, ai_data.application_id)
        assert application is not None and application.status == "submitted"
        assert list(await session.scalars(select(AiMessage))) == []
        run = await session.get(AiRun, request_id)
        assert run is not None and run.result_hash is not None
        assert "이번 프로젝트" not in str(run.references)


@pytest.mark.parametrize("purpose", ["review", "recommendation"])
async def test_applicant_stream_compatibility_never_emits_partial_text(
    ai_data: ApplicationData, purpose: str
) -> None:
    driver = FakeDriver(ai_data)
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        response = await client.post(
            endpoint(ai_data, purpose) + "/stream", json={"requestId": str(uuid4())}
        )
        stream = events(response.text)
        assert stream[-1]["event"] == "done", response.text
        result = stream[-2]["result"]
        assert isinstance(result, dict) and result["schemaVersion"] == 3
        candidate = result if purpose == "review" else result["candidates"][0]
        unknown = candidate["assessment"]["criteria"][1]
        assert unknown["score"] is None
        assert unknown["informationStatus"] == "insufficient"
        assert not any(item["event"] == "answer.delta" for item in stream)
    assert driver.assessment_calls == 1 and driver.write_calls == 0


@pytest.mark.parametrize("purpose", ["review", "recommendation"])
async def test_applicant_json_enforces_auth_csrf_and_team_owner(
    ai_data: ApplicationData, purpose: str
) -> None:
    driver = FakeDriver(ai_data)
    route = endpoint(ai_data, purpose)
    async with client_for(ai_data, driver, None) as client:
        assert (
            await client.post(route, json={"requestId": str(uuid4())})
        ).status_code == 401
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        client.headers[CSRF_HEADER_NAME] = "invalid"
        assert (
            await client.post(route, json={"requestId": str(uuid4())})
        ).status_code == 403
    async with client_for(ai_data, driver, ai_data.stranger_id) as client:
        assert (
            await client.post(route, json={"requestId": str(uuid4())})
        ).status_code == (404 if purpose == "review" else 403)
    assert driver.plan_calls == driver.assessment_calls == 0


async def test_applicant_json_retry_is_explicit_and_attempt_fenced(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.fail_once = True
    body = {"requestId": str(uuid4())}
    base = f"/api/v1/ai/requests/{body['requestId']}"
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        first = await client.post(endpoint(ai_data, "review"), json=body)
        assert first.status_code == 503, first.text
        assert "provider failure" not in first.text
        status = (await client.get(base)).json()["data"]
        assert status["status"] == "failed" and status["failure"]["retryable"] is True
        second = await client.post(
            base + "/retries", json={"expectedAttempt": 1, "input": body}
        )
        assert second.status_code == 200, second.text
        result = second.json()["data"]
        assert result["attempt"] == 2 and result["status"] == "succeeded"
        assert (
            await client.put(base + "/cancellation", json={"expectedAttempt": 1})
        ).status_code == 409
        assert (
            await client.post(
                base + "/retries", json={"expectedAttempt": 1, "input": body}
            )
        ).status_code == 409


async def test_chat_cannot_retry_through_applicant_json_endpoint(
    ai_data: ApplicationData,
) -> None:
    driver = FakeDriver(ai_data)
    driver.fail_once = True
    body = payload()
    base = f"/api/v1/ai/requests/{body['requestId']}"
    async with client_for(ai_data, driver, ai_data.applicant_id) as client:
        first = await client.post("/api/v1/ai/chat/stream", json=body)
        assert events(first.text)[-1]["event"] == "error"
        rejected = await client.post(
            base + "/retries", json={"expectedAttempt": 1, "input": body}
        )
        assert rejected.status_code == 409, rejected.text
        current = (await client.get(base)).json()["data"]
        assert current["status"] == "failed" and current["attempt"] == 1
    assert driver.plan_calls == 1 and driver.assessment_calls == 0


@pytest.mark.parametrize("change", ["cancel", "logout"])
async def test_applicant_json_interrupts_pending_model_without_result(
    ai_data: ApplicationData, change: str
) -> None:
    driver = FakeDriver(ai_data)
    driver.block = True
    request_id = uuid4()
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        pending = asyncio.create_task(
            client.post(
                endpoint(ai_data, "review"), json={"requestId": str(request_id)}
            )
        )
        try:
            await asyncio.wait_for(driver.entered.wait(), 3)
            if change == "cancel":
                response = await client.put(
                    f"/api/v1/ai/requests/{request_id}/cancellation",
                    json={"expectedAttempt": 1},
                )
                assert response.status_code == 200
            else:
                async with ai_data.database.session() as session:
                    await session.execute(
                        update(AuthSession)
                        .where(
                            AuthSession.auth_session_id
                            == ai_data.sessions[
                                ai_data.leader_id
                            ].session.auth_session_id
                        )
                        .values(revoked_at=datetime.now(UTC))
                    )
                    await session.commit()
            completed = await asyncio.wait_for(pending, 3)
            assert completed.status_code == 200, completed.text
            data = completed.json()["data"]
            assert data["status"] == (
                "canceled" if change == "cancel" else "invalidated"
            )
            assert data["result"] is None
            assert driver.cancelled.is_set()
            assert driver.assessment_calls == 1 and driver.write_calls == 0
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_unverified_assessment_evidence_is_rejected_without_result(
    ai_data: ApplicationData,
) -> None:
    class ForgedEvidenceDriver(FakeDriver):
        async def assess(
            self, sources: SourceTools, *, trace_context: AiTraceContext | None = None
        ) -> ApplicantAssessmentPlan:
            output = await super().assess(sources, trace_context=trace_context)
            output.assessments[0].criteria[0].evidence_refs = [
                "profile.roleCodes:invented"
            ]
            return output

    request_id = uuid4()
    driver = ForgedEvidenceDriver(ai_data)
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        response = await client.post(
            endpoint(ai_data, "review"), json={"requestId": str(request_id)}
        )
        assert response.status_code == 503, response.text
        assert "invented" not in response.text
        state = (await client.get(f"/api/v1/ai/requests/{request_id}")).json()["data"]
        assert state["status"] == "failed"
        assert state["failure"]["code"] == "invalid_output"
    assert driver.write_calls == 0
    async with ai_data.database.session() as session:
        run = await session.get(AiRun, request_id)
        assert run is not None and run.result_hash is None


async def test_cancellation_interrupts_structured_assessment_generation(
    ai_data: ApplicationData,
) -> None:
    assessment_started = asyncio.Event()
    assessment_stopped = asyncio.Event()

    class BlockedAssessmentDriver(FakeDriver):
        async def assess(
            self, sources: SourceTools, *, trace_context: AiTraceContext | None = None
        ) -> ApplicantAssessmentPlan:
            self.assessment_calls += 1
            assessment_started.set()
            try:
                await asyncio.Event().wait()
                raise AssertionError("차단된 모델이 취소 없이 완료되면 안 됩니다.")
            finally:
                assessment_stopped.set()

    driver = BlockedAssessmentDriver(ai_data)
    request_id = uuid4()
    async with client_for(ai_data, driver, ai_data.leader_id) as client:
        pending = asyncio.create_task(
            client.post(
                endpoint(ai_data, "review"), json={"requestId": str(request_id)}
            )
        )
        try:
            await asyncio.wait_for(assessment_started.wait(), 3)
            canceled = await client.put(
                f"/api/v1/ai/requests/{request_id}/cancellation",
                json={"expectedAttempt": 1},
            )
            assert canceled.status_code == 200
            response = await asyncio.wait_for(pending, 3)
            assert response.json()["data"]["status"] == "canceled"
            assert response.json()["data"]["result"] is None
            assert assessment_stopped.is_set()
            assert driver.assessment_calls == 1 and driver.write_calls == 0
        finally:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)


async def test_applicant_json_empty_candidates_remain_a_completed_result(
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
            endpoint(ai_data, "recommendation"), json={"requestId": str(uuid4())}
        )
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert data["status"] == "empty"
        assert data["result"]["candidates"] == []


async def test_json_disconnect_cancels_pending_model_and_run(
    ai_data: ApplicationData,
) -> None:
    from starlette.types import Message, Scope

    driver = FakeDriver(ai_data)
    driver.block = True
    service = AiService(ai_data.database, settings(), driver)
    owner = principal(ai_data, ai_data.leader_id)
    execution = await service.start(
        owner,
        "applicant_review",
        TargetStart(requestId=uuid4()),
        application_id=ai_data.application_id,
    )
    response = json_response(service, execution)
    sent: list[Message] = []

    async def receive() -> Message:
        await driver.entered.wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    await asyncio.wait_for(response(scope, receive, send), 3)
    assert (await service.runs.get(owner, execution.request_id)).status == "canceled"
    assert driver.cancelled.is_set()
    assert sent == []


async def test_json_send_failure_releases_current_profile_locks(
    ai_data: ApplicationData,
) -> None:
    from starlette.types import Message, Scope

    service = AiService(ai_data.database, settings(), FakeDriver(ai_data))
    owner = principal(ai_data, ai_data.leader_id)
    execution = await service.start(
        owner,
        "applicant_review",
        TargetStart(requestId=uuid4()),
        application_id=ai_data.application_id,
    )
    response = json_response(service, execution)

    async def receive() -> Message:
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}

    async def send(message: Message) -> None:
        raise OSError("client disconnected before JSON headers")

    scope: Scope = {"type": "http", "asgi": {"spec_version": "2.4"}}
    with pytest.raises(OSError):
        await asyncio.wait_for(response(scope, receive, send), 3)

    async def update_profile() -> None:
        async with ai_data.database.session() as session:
            await session.execute(
                update(Profile)
                .where(Profile.profile_id == ai_data.applicant_id)
                .values(version=2)
            )
            await session.commit()

    await asyncio.wait_for(update_profile(), 2)
    # 생성 완료 커밋과 클라이언트의 수신 성공은 별개의 상태다.
    assert (await service.runs.get(owner, execution.request_id)).status == "succeeded"
