"""받은 팀장의 현재 지원자 조회와 명시적 검토 행동을 처리한다."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.domains.applications.models import Application, ApplicationEvent
from app.domains.applications.review_schemas import (
    ApplicantResponse,
    ApplicantSearch,
    SelectionResult,
)
from app.domains.applications.schemas import ApplicationResponse
from app.domains.applications.service import application_response
from app.domains.notifications.models import Notification
from app.domains.profiles.models import Profile
from app.domains.profiles.queries import build_profile_responses
from app.domains.teams.locks import (
    lock_accounts,
    lock_applications,
    lock_contest,
    lock_teams,
)
from app.domains.teams.models import Team, TeamMembership
from app.domains.teams.queries import get_team_summary


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _read_snapshot(session: AsyncSession) -> None:
    if session.in_transaction():
        raise RuntimeError("Applicant reads require a fresh request session")
    await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})


def _applicant_statement() -> Select[tuple[Application, Profile, bool, str]]:
    has_membership = (
        select(TeamMembership.team_membership_id)
        .where(
            TeamMembership.account_id == Application.applicant_account_id,
            TeamMembership.contest_id == Application.contest_id,
            TeamMembership.ended_at.is_(None),
        )
        .exists()
    )
    return (
        select(Application, Profile, has_membership, ApplicationEvent.reason_code)
        .join(Profile, Profile.profile_id == Application.applicant_account_id)
        .outerjoin(
            ApplicationEvent,
            and_(
                ApplicationEvent.application_id == Application.application_id,
                ApplicationEvent.application_version == Application.version,
            ),
        )
    )


async def list_applicants(
    session: AsyncSession, team_id: UUID, account_id: UUID, query: ApplicantSearch
) -> Page[ApplicantResponse]:
    await _read_snapshot(session)
    team = await session.get(Team, team_id)
    if team is None:
        raise AppError(404, "TEAM_NOT_FOUND", "팀을 찾을 수 없습니다.")
    if team.leader_account_id != account_id:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    conditions = [Application.team_id == team_id]
    if query.status is not None:
        conditions.append(Application.status == query.status.value)
    total = await session.scalar(
        select(func.count()).select_from(Application).where(*conditions)
    )
    assert total is not None
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    rows = (
        await session.execute(
            _applicant_statement()
            .where(*conditions)
            .order_by(
                Application.submitted_at.desc(), Application.application_id.desc()
            )
            .offset((page - 1) * query.page_size)
            .limit(query.page_size)
        )
    ).all()
    profiles = await build_profile_responses(session, [row[1] for row in rows])
    return Page(
        data=[
            ApplicantResponse(
                application=application_response(
                    application, viewer_id=account_id, reason=reason
                ),
                profile=profiles[profile.profile_id],
                is_selection_candidate=(
                    application.status in ("submitted", "reviewing")
                    and not has_membership
                ),
            )
            for application, profile, has_membership, reason in rows
        ],
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=total_pages
        ),
    )


async def get_applicant(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> ApplicantResponse:
    await _read_snapshot(session)
    identity = (
        await session.execute(
            select(Application.applicant_account_id, Team.leader_account_id)
            .join(Team, Team.team_id == Application.team_id)
            .where(Application.application_id == application_id)
        )
    ).one_or_none()
    if identity is None or account_id not in identity:
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity[1]:
        raise AppError(403, "FORBIDDEN", "팀장만 지원자를 확인할 수 있습니다.")
    application, profile, has_membership, reason = (
        await session.execute(
            _applicant_statement().where(Application.application_id == application_id)
        )
    ).one()
    profiles = await build_profile_responses(session, [profile])
    return ApplicantResponse(
        application=application_response(
            application, viewer_id=account_id, reason=reason
        ),
        profile=profiles[profile.profile_id],
        is_selection_candidate=(
            application.status in ("submitted", "reviewing") and not has_membership
        ),
    )


async def _leader_identity(
    session: AsyncSession, application_id: UUID, account_id: UUID
) -> tuple[UUID, UUID, UUID]:
    identity = (
        await session.execute(
            select(
                Application.applicant_account_id,
                Application.contest_id,
                Application.team_id,
                Team.leader_account_id,
            )
            .join(Team, Team.team_id == Application.team_id)
            .where(Application.application_id == application_id)
        )
    ).one_or_none()
    if identity is None or account_id not in (identity[0], identity[3]):
        raise AppError(404, "APPLICATION_NOT_FOUND", "지원을 찾을 수 없습니다.")
    if account_id != identity[3]:
        raise AppError(403, "FORBIDDEN", "지원받은 팀장만 처리할 수 있습니다.")
    return identity[0], identity[1], identity[2]


def _check_action(
    application: Application, team: Team, account_id: UUID, expected_version: int
) -> None:
    # 잠금 전 읽은 권한과 버전을 실제 처리 직전에 다시 확인한다.
    if team.leader_account_id != account_id:
        raise AppError(403, "FORBIDDEN", "지원받은 팀장만 처리할 수 있습니다.")
    if application.version != expected_version:
        raise AppError(409, "VERSION_CONFLICT", "최신 지원을 확인해 주세요.")


async def _record_change(
    session: AsyncSession,
    application: Application,
    *,
    status: str,
    actor_id: UUID | None,
    reason: str,
    now: datetime,
    cause_event_id: UUID | None = None,
) -> ApplicationEvent:
    previous = application.status
    application.status = status
    application.version += 1
    application.status_changed_at = now
    event = ApplicationEvent(
        application_event_id=uuid4(),
        application_id=application.application_id,
        team_id=application.team_id,
        contest_id=application.contest_id,
        applicant_account_id=application.applicant_account_id,
        application_version=application.version,
        from_status=previous,
        to_status=status,
        actor_account_id=actor_id,
        reason_code=reason,
        occurred_at=now,
        cause_event_id=cause_event_id,
    )
    session.add(event)
    await session.flush()
    session.add(
        Notification(
            event_id=event.application_event_id,
            recipient_account_id=application.applicant_account_id,
            kind="application_status_changed",
        )
    )
    return event


async def change_review_status(
    session: AsyncSession,
    application_id: UUID,
    account_id: UUID,
    expected_version: int,
    target: Literal["reviewing", "rejected"],
) -> ApplicationResponse:
    """검토 시작·미선발을 명시적으로 처리하며 동일 상태는 현재 버전에서만 성공한다."""
    try:
        applicant_id, contest_id, team_id = await _leader_identity(
            session, application_id, account_id
        )
        await lock_accounts(session, [applicant_id])
        await lock_contest(session, contest_id)
        team = (await lock_teams(session, [team_id]))[0]
        application = (await lock_applications(session, [application_id]))[0]
        _check_action(application, team, account_id, expected_version)
        if application.status == target:
            result = application_response(application, viewer_id=account_id)
            await session.rollback()
            return result
        permitted = (
            ("submitted",) if target == "reviewing" else ("submitted", "reviewing")
        )
        if application.status not in permitted:
            raise AppError(
                409,
                "INVALID_APPLICATION_STATE",
                "현재 지원 상태에서는 처리할 수 없습니다.",
            )
        await _record_change(
            session,
            application,
            status=target,
            actor_id=account_id,
            reason="reviewing_started" if target == "reviewing" else "rejected",
            now=datetime.now(UTC),
        )
        result = application_response(application, viewer_id=account_id)
        await session.commit()
        return result
    except BaseException:
        await session.rollback()
        raise


async def select_application(
    session: AsyncSession, application_id: UUID, account_id: UUID, expected_version: int
) -> SelectionResult:
    """현재 선발·소속 확정·같은 공모전 대기 지원 폐기를 함께 저장한다."""
    try:
        applicant_id, contest_id, team_id = await _leader_identity(
            session, application_id, account_id
        )
        await lock_accounts(session, [applicant_id])
        contest = await lock_contest(session, contest_id)
        assert contest is not None
        # 같은 지원자 계정 잠금이 신규 접수와 상태 변경을 직렬화한다.
        # 대상 팀만 먼저 잠그지 않고 폐기 대상 팀까지 모아 전체를 정렬한다.
        related = (
            await session.execute(
                select(Application.application_id, Application.team_id).where(
                    Application.applicant_account_id == applicant_id,
                    Application.contest_id == contest_id,
                    or_(
                        Application.application_id == application_id,
                        Application.status.in_(("submitted", "reviewing")),
                    ),
                )
            )
        ).all()
        teams = await lock_teams(session, sorted({row[1] for row in related}))
        applications = await lock_applications(session, [row[0] for row in related])
        team = next(item for item in teams if item.team_id == team_id)
        application = next(
            item for item in applications if item.application_id == application_id
        )
        _check_action(application, team, account_id, expected_version)
        membership = await session.scalar(
            select(TeamMembership).where(
                TeamMembership.account_id == applicant_id,
                TeamMembership.contest_id == contest_id,
                TeamMembership.ended_at.is_(None),
            )
        )
        if (
            application.status == "selected"
            and membership is not None
            and membership.source_application_id == application_id
        ):
            result = SelectionResult(
                application=application_response(application, viewer_id=account_id),
                team=await get_team_summary(session, team_id),
                membership_id=membership.team_membership_id,
            )
            await session.rollback()
            return result
        if application.status not in ("submitted", "reviewing"):
            raise AppError(
                409,
                "INVALID_APPLICATION_STATE",
                "현재 지원 상태에서는 선발할 수 없습니다.",
            )
        if membership is not None:
            raise AppError(
                409, "MEMBERSHIP_CONFLICT", "같은 공모전의 현재 소속이 있습니다."
            )
        now = _utcnow()
        if not contest.registration_opens_at <= now < contest.registration_closes_at:
            raise AppError(409, "CONTEST_NOT_OPEN", "현재 공고의 접수 기간이 아닙니다.")
        member_count = await session.scalar(
            select(func.count())
            .select_from(TeamMembership)
            .where(TeamMembership.team_id == team_id, TeamMembership.ended_at.is_(None))
        )
        assert member_count is not None
        if member_count >= team.target_capacity:
            raise AppError(409, "TEAM_FULL", "팀 정원이 모두 찼습니다.")
        team.version += 1
        team.updated_at = now
        if member_count + 1 == team.target_capacity:
            team.recruitment_state = "closed"
            team.closed_reason = "capacity_reached"
        selected_event = await _record_change(
            session,
            application,
            status="selected",
            actor_id=account_id,
            reason="selected",
            now=now,
        )
        membership = TeamMembership(
            team_membership_id=uuid4(),
            team_id=team_id,
            contest_id=contest_id,
            account_id=applicant_id,
            source_application_id=application_id,
            joined_at=now,
        )
        session.add(membership)
        for other in applications:
            if other.application_id != application_id and other.status in (
                "submitted",
                "reviewing",
            ):
                await _record_change(
                    session,
                    other,
                    status="discarded",
                    actor_id=None,
                    reason="selected_elsewhere",
                    now=now,
                    cause_event_id=selected_event.application_event_id,
                )
        await session.flush()
        result = SelectionResult(
            application=application_response(application, viewer_id=account_id),
            team=await get_team_summary(session, team_id, now=now),
            membership_id=membership.team_membership_id,
        )
        await session.commit()
        return result
    except IntegrityError as error:
        await session.rollback()
        constraint = getattr(error.orig, "constraint_name", None) or getattr(
            getattr(error.orig, "__cause__", None), "constraint_name", None
        )
        if constraint == "uq_memberships_active_contest":
            raise AppError(
                409, "MEMBERSHIP_CONFLICT", "같은 공모전의 현재 소속이 있습니다."
            ) from error
        raise
    except BaseException:
        await session.rollback()
        raise
