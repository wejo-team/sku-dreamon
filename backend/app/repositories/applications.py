"""지원 조회와 사건 저장을 수행하고 내부 ORM 결과만 반환한다."""

from typing import NamedTuple
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.applications import Application, ApplicationEvent
from app.models.teams import Team, TeamMembership


class ApplicationDetailRecord(NamedTuple):
    application: Application
    leader_id: UUID
    reason: str | None
    source_application_id: UUID | None
    source_team_id: UUID | None


async def get_application_record(
    session: AsyncSession, application_id: UUID
) -> ApplicationDetailRecord | None:
    source_event = aliased(ApplicationEvent)
    source_membership = aliased(TeamMembership)
    row = (
        await session.execute(
            select(
                Application,
                Team.leader_account_id,
                ApplicationEvent.reason_code,
                source_event.application_id,
                source_membership.team_id,
            )
            .join(Team, Team.team_id == Application.team_id)
            .outerjoin(
                ApplicationEvent,
                and_(
                    ApplicationEvent.application_id == Application.application_id,
                    ApplicationEvent.application_version == Application.version,
                ),
            )
            .outerjoin(
                source_event,
                source_event.application_event_id == ApplicationEvent.cause_event_id,
            )
            .outerjoin(
                source_membership,
                source_membership.team_membership_id
                == ApplicationEvent.cause_membership_id,
            )
            .where(Application.application_id == application_id)
            .execution_options(populate_existing=True)
        )
    ).one_or_none()
    return ApplicationDetailRecord(*row) if row is not None else None
