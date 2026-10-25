"""팀·팀장 소속·다른 대기 지원의 폐기 사건과 알림을 함께 저장한다."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.applications import ApplicationEvent
from app.models.teams import Team, TeamMembership
from app.repositories import team_create as repository
from app.repositories.applications import add_event
from app.repositories.recruitment_locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)
from app.repositories.teams import get_current_membership
from app.rules.catalogs import RoleCode, validate_catalog_selection
from app.rules.contests import validate_team_capacity
from app.rules.requests import request_fingerprint
from app.schemas.team_create import TeamCreate
from app.schemas.teams import TeamDetail
from app.services.notifications import create_notification
from app.services.participation_profiles import require_profile
from app.services.teams import get_team_detail


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def create_team(
    session: AsyncSession, account_id: UUID, body: TeamCreate
) -> tuple[TeamDetail, bool]:
    """재시도는 현재 팀을 반환하며 새 생성만 현재 조건을 검사한다."""
    fingerprint = request_fingerprint(
        body.model_dump(mode="json", exclude={"request_id"})
    )
    try:
        await lock_accounts(session, [account_id])
        previous = await repository.find_request(session, account_id, body.request_id)
        if previous is not None:
            if previous.request_fingerprint != fingerprint:
                raise AppError(
                    409, "REQUEST_ID_REUSED", "같은 요청 ID의 입력이 다릅니다."
                )
            result = await get_team_detail(session, previous.team_id)
            await session.rollback()
            return result, False
        await require_profile(session, account_id, public=False)
        contest = await lock_contest(session, body.contest_id)
        if contest is None:
            raise AppError(404, "CONTEST_NOT_FOUND", "공고를 찾을 수 없습니다.")
        pending = await repository.pending_ids(session, account_id, contest.contest_id)
        await lock_teams(session, sorted({team_id for _, team_id in pending}))
        applications = await lock_applications(
            session, [application_id for application_id, _ in pending]
        )
        now = _utcnow()
        if not contest.registration_opens_at <= now < contest.registration_closes_at:
            raise AppError(409, "CONTEST_NOT_OPEN", "현재 공고의 접수 기간이 아닙니다.")
        if (
            await get_current_membership(session, account_id, contest.contest_id)
            is not None
        ):
            raise AppError(
                409, "MEMBERSHIP_CONFLICT", "같은 공모전의 현재 소속이 있습니다."
            )
        capacity = int(body.capacity)
        try:
            validate_team_capacity(
                capacity,
                kind=contest.member_limit_kind,
                minimum_members=contest.min_members,
                maximum_members=contest.max_members,
            )
        except ValueError as error:
            raise AppError(
                409, "CAPACITY_OUT_OF_RANGE", "공식 참가 인원 조건을 확인해주세요."
            ) from error
        for code in body.role_codes:
            validate_catalog_selection(RoleCode, code)
        deadline = body.recruitment_deadline.resolve()
        team = Team(
            team_id=uuid4(),
            request_id=body.request_id,
            request_fingerprint=fingerprint,
            contest_id=contest.contest_id,
            leader_account_id=account_id,
            name=body.name,
            introduction=body.introduction,
            target_capacity=capacity,
            recruitment_state="closed" if capacity == 1 else "open",
            closed_reason="capacity_reached" if capacity == 1 else None,
            recruitment_closes_at=deadline.ends_at,
            deadline_source_date=deadline.source_date,
            deadline_source_time=deadline.source_time,
            deadline_source_timezone=deadline.source_timezone,
            deadline_effective_timezone=deadline.effective_timezone,
            deadline_time_assumed=deadline.time_assumed,
            deadline_timezone_assumed=deadline.timezone_assumed,
            created_at=now,
            updated_at=now,
            version=1,
        )
        membership = TeamMembership(
            team_membership_id=uuid4(),
            team_id=team.team_id,
            contest_id=contest.contest_id,
            account_id=account_id,
            source_application_id=None,
            joined_at=now,
        )
        await repository.insert_team(session, team, membership, body.role_codes)
        for application in applications:
            old_status = application.status
            application.status = "discarded"
            application.version += 1
            application.status_changed_at = now
            event = ApplicationEvent(
                application_event_id=uuid4(),
                application_id=application.application_id,
                team_id=application.team_id,
                contest_id=contest.contest_id,
                applicant_account_id=account_id,
                application_version=application.version,
                from_status=old_status,
                to_status="discarded",
                actor_account_id=None,
                reason_code="team_created_elsewhere",
                cause_membership_id=membership.team_membership_id,
                occurred_at=now,
            )
            await add_event(session, event)
            await create_notification(
                session,
                event_id=event.application_event_id,
                recipient_id=account_id,
                kind="application_status_changed",
            )
        result = await get_team_detail(session, team.team_id, now=now)
        await session.commit()
        return result, True
    except IntegrityError as error:
        await session.rollback()
        constraint = getattr(
            getattr(error.orig, "__cause__", None), "constraint_name", None
        )
        if constraint == "uq_memberships_active_contest":
            raise AppError(
                409, "MEMBERSHIP_CONFLICT", "같은 공모전의 현재 소속이 있습니다."
            ) from error
        raise
    except Exception:
        await session.rollback()
        raise
