"""신규 지원·제출 사건·본인과 팀장 알림을 현재 조건 아래 원자적으로 저장한다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import Application, ApplicationEvent
from app.repositories import application_create as repository
from app.repositories.applications import add_event
from app.repositories.recruitment_locks import lock_accounts, lock_contest, lock_teams
from app.repositories.teams import count_current_members, get_current_membership
from app.rules.catalogs import RoleCode, validate_catalog_selection
from app.rules.requests import request_fingerprint
from app.schemas.application_create import ApplicationCreate
from app.schemas.applications import ApplicationResponse
from app.services.applications import get_application
from app.services.notifications import create_notification
from app.services.participation_profiles import require_profile


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def submit_application(
    session: AsyncSession, account_id: UUID, team_id: UUID, body: ApplicationCreate
) -> tuple[ApplicationResponse, bool]:
    fingerprint = request_fingerprint(
        {"teamId": str(team_id), **body.model_dump(mode="json", exclude={"request_id"})}
    )
    try:
        await lock_accounts(session, [account_id])
        previous = await repository.find_request(session, account_id, body.request_id)
        if previous is not None:
            if previous.request_fingerprint != fingerprint:
                raise AppError(
                    409, "REQUEST_ID_REUSED", "같은 요청 ID의 입력이 다릅니다."
                )
            result = await get_application(session, previous.application_id, account_id)
            await session.rollback()
            return result, False
        contest_id = await repository.get_team_contest(session, team_id)
        if contest_id is None:
            raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
        await require_profile(session, account_id, public=True)
        contest = await lock_contest(session, contest_id)
        assert contest is not None
        team = (await lock_teams(session, [team_id]))[0]
        now = _utcnow()
        validate_catalog_selection(RoleCode, body.role_code)
        if await get_current_membership(session, account_id, contest_id) is not None:
            raise AppError(
                409, "MEMBERSHIP_CONFLICT", "같은 공모전의 현재 소속이 있습니다."
            )
        if await repository.has_history(session, account_id, team_id, ("rejected",)):
            raise AppError(
                409,
                "REAPPLICATION_NOT_ALLOWED",
                "미선발된 팀에는 재지원할 수 없습니다.",
            )
        if await repository.has_history(
            session, account_id, team_id, ("submitted", "reviewing", "selected")
        ):
            raise AppError(409, "DUPLICATE_APPLICATION", "이미 이 팀에 지원했습니다.")
        if not contest.registration_opens_at <= now < contest.registration_closes_at:
            raise AppError(409, "CONTEST_NOT_OPEN", "현재 공고의 접수 기간이 아닙니다.")
        if await count_current_members(session, team_id) >= team.target_capacity:
            raise AppError(409, "TEAM_FULL", "팀 정원이 찼습니다.")
        if team.recruitment_state != "open":
            raise AppError(409, "RECRUITMENT_CLOSED", "팀 모집이 종료되었습니다.")
        if now >= team.recruitment_closes_at:
            raise AppError(
                409, "RECRUITMENT_DEADLINE_PASSED", "팀 모집 기한이 지났습니다."
            )
        application = Application(
            application_id=uuid4(),
            request_id=body.request_id,
            request_fingerprint=fingerprint,
            team_id=team_id,
            contest_id=contest_id,
            applicant_account_id=account_id,
            applied_role_code=body.role_code,
            message=body.message,
            status="submitted",
            version=1,
            submitted_at=now,
            status_changed_at=now,
        )
        await repository.insert_application(session, application)
        event = ApplicationEvent(
            application_event_id=uuid4(),
            application_id=application.application_id,
            team_id=team_id,
            contest_id=contest_id,
            applicant_account_id=account_id,
            application_version=1,
            from_status=None,
            to_status="submitted",
            actor_account_id=account_id,
            reason_code="submitted",
            occurred_at=now,
        )
        await add_event(session, event)
        await create_notification(
            session,
            event_id=event.application_event_id,
            recipient_id=account_id,
            kind="application_status_changed",
        )
        await create_notification(
            session,
            event_id=event.application_event_id,
            recipient_id=team.leader_account_id,
            kind="new_application",
        )
        result = await get_application(session, application.application_id, account_id)
        await session.commit()
        return result, True
    except IntegrityError as error:
        await session.rollback()
        constraint = getattr(
            getattr(error.orig, "__cause__", None), "constraint_name", None
        )
        if constraint == "uq_applications_current":
            raise AppError(
                409, "DUPLICATE_APPLICATION", "이미 이 팀에 지원했습니다."
            ) from error
        raise
    except Exception:
        await session.rollback()
        raise
