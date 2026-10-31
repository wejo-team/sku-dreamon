"""목적별 현재 권한으로 자료를 조회하고 모델 전송 필드를 제한한다."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.types import AgentContext, Reference, Resource, fingerprint
from app.core.db.session import Database
from app.core.exceptions import AppError
from app.repositories import ai_runs as run_repository
from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import RegistrationStatus
from app.schemas.application_review import ApplicantSearch
from app.schemas.contests import ContestSearch
from app.schemas.profiles import PeopleQuery, ProfileResponse
from app.schemas.teams import TeamSearch
from app.services import application_review, contests, profiles, teams
from app.services.sessions import IDLE_LIFETIME

_PROFILE_FIELDS = {
    "real_name",
    "introduction",
    "field_codes",
    "role_codes",
    "skill_codes",
    "experience_state",
    "experience_body",
    "weekly_availability_code",
    "courses",
}
_CONTEST_FIELDS = {
    "title",
    "organizer",
    "description",
    "field_codes",
    "registration_status",
    "starts_at",
    "ends_at",
    "eligibility_text",
    "capacity",
    "deliverables",
    "awards",
}
_TEAM_FIELDS = {
    "name",
    "introduction",
    "field_codes",
    "role_codes",
    "capacity",
    "member_count",
    "recruitment_ends_at",
    "is_recruiting",
    "contest_title",
}


def profile_facts(profile: ProfileResponse) -> dict[str, object]:
    return profile.model_dump(mode="json", include=_PROFILE_FIELDS)


class SourceReader:
    def __init__(
        self,
        database: Database,
        context: AgentContext,
        *,
        session: AsyncSession | None = None,
    ) -> None:
        self.database = database
        self.context = context
        self._provided_session = session

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[AsyncSession]:
        """전송 검사는 잠금을 보유한 연결을 재사용하고 도구 조회만 세션을 연다."""
        if self._provided_session is not None:
            yield self._provided_session
        else:
            async with self.database.session() as session:
                yield session

    async def require_session(self) -> None:
        async with self._session() as session:
            row = await run_repository.session_record(
                session, self.context.principal.auth_session_id
            )
            now = datetime.now(UTC)
            if (
                row is None
                or row.account_id != self.context.principal.account_id
                or row.revoked_at is not None
                or now >= row.expires_at
                or now >= row.last_seen_at + IDLE_LIFETIME
            ):
                raise AppError(401, "UNAUTHENTICATED", "로그인이 필요합니다.")

    async def get(self, kind: str, resource_id: UUID) -> Resource:
        await self.require_session()
        if self.context.purpose == "chat":
            if kind == "contest":
                return await self._contest(resource_id)
            if kind == "team":
                return await self._team(resource_id)
            if kind == "person":
                return await self._person(resource_id)
        elif kind == "application":
            if (
                self.context.application_id is not None
                and resource_id != self.context.application_id
            ):
                raise AppError(
                    404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다."
                )
            return await self._applicant(resource_id)
        raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")

    async def _contest(self, resource_id: UUID) -> Resource:
        async with self._session() as session:
            value = await contests.get_contest_detail(session, resource_id)
        facts = value.model_dump(mode="json", include=_CONTEST_FIELDS)
        return Resource(
            reference=Reference(
                kind="contest",
                resource_id=resource_id,
                contest_id=resource_id,
                fingerprint=fingerprint({"facts": facts, "version": value.version}),
            ),
            title=value.title,
            is_demo=value.is_demo,
            field_codes=[code.value for code in value.field_codes],
            facts=facts,
        )

    async def _team(self, resource_id: UUID) -> Resource:
        async with self._session() as session:
            value = await teams.get_team_detail(session, resource_id)
            eligible = value.is_recruiting and await run_repository.can_recommend_team(
                session, value.id, value.contest_id, self.context.principal.account_id
            )
        if not eligible:
            raise AppError(404, "RESOURCE_NOT_FOUND", "현재 추천 가능한 팀이 아닙니다.")
        facts = value.model_dump(mode="json", include=_TEAM_FIELDS)
        return Resource(
            reference=Reference(
                kind="team",
                resource_id=resource_id,
                team_id=resource_id,
                contest_id=value.contest_id,
                fingerprint=fingerprint({"facts": facts, "version": value.version}),
            ),
            title=value.name,
            is_demo=value.is_demo,
            field_codes=[code.value for code in value.field_codes],
            role_codes=[code.value for code in value.role_codes],
            facts=facts,
        )

    async def _person(self, resource_id: UUID) -> Resource:
        async with self._session() as session:
            value = (
                await profiles.get_public_profile(session, resource_id)
                if self._provided_session is None
                else await profiles.read_public_profile(session, resource_id)
            )
        facts = profile_facts(value)
        return Resource(
            reference=Reference(
                kind="person",
                resource_id=resource_id,
                account_id=resource_id,
                profile_version=value.version,
                fingerprint=fingerprint({"facts": facts, "version": value.version}),
            ),
            title=value.real_name,
            is_demo=value.is_demo,
            field_codes=[code.value for code in value.field_codes],
            role_codes=[code.value for code in value.role_codes],
            facts=facts,
        )

    async def _applicant(self, resource_id: UUID) -> Resource:
        async with self._session() as session:
            read = (
                application_review.get_applicant
                if self._provided_session is None
                else application_review.read_applicant
            )
            value = await read(session, resource_id, self.context.principal.account_id)
        application = value.application
        if (
            self.context.team_id is not None
            and application.team_id != self.context.team_id
        ):
            raise AppError(404, "RESOURCE_NOT_FOUND", "요청한 정보를 찾을 수 없습니다.")
        async with self._session() as session:
            team = await teams.get_team_detail(session, application.team_id)
        facts: dict[str, object] = {
            "profile": profile_facts(value.profile),
            "message": application.message,
            "role": application.role_code.value,
            "status": application.status,
            "team": team.model_dump(
                mode="json",
                include={"name", "introduction", "role_codes", "contest_title"},
            ),
            "isSelectionCandidate": value.is_selection_candidate,
        }
        return Resource(
            reference=Reference(
                kind="application",
                resource_id=resource_id,
                account_id=application.applicant_account_id,
                team_id=application.team_id,
                contest_id=application.contest_id,
                profile_version=value.profile.version,
                fingerprint=fingerprint(
                    {
                        "facts": facts,
                        "profileVersion": value.profile.version,
                        "applicationVersion": application.version,
                        "teamVersion": team.version,
                    }
                ),
            ),
            title=value.profile.real_name,
            is_demo=value.profile.is_demo,
            facts=facts,
            is_selection_candidate=value.is_selection_candidate,
        )

    async def search(
        self,
        kind: Literal["contest", "team", "person"],
        query: str,
        page: int,
        *,
        role_code: RoleCode | None = None,
        field_code: FieldCode | None = None,
        registration_status: RegistrationStatus | None = None,
    ) -> tuple[list[UUID], bool]:
        if self.context.purpose != "chat":
            raise AppError(403, "FORBIDDEN", "이 요청에서는 사용할 수 없는 조회입니다.")
        await self.require_session()
        async with self.database.session() as session:
            if kind == "contest":
                result = await contests.list_contests(
                    session,
                    ContestSearch.model_validate(
                        {
                            "q": query,
                            "page": page,
                            "pageSize": 8,
                            "sort": "deadline_asc",
                            "fieldCode": field_code,
                            "registrationStatus": registration_status,
                        }
                    ),
                )
                return [
                    item.id for item in result.data
                ], page < result.pagination.total_pages
            if kind == "team":
                team_result = await teams.list_teams(
                    session,
                    TeamSearch.model_validate(
                        {
                            "q": query,
                            "page": page,
                            "pageSize": 8,
                            "recruitingOnly": True,
                            "roleCode": role_code,
                        }
                    ),
                )
                return [
                    item.id for item in team_result.data
                ], page < team_result.pagination.total_pages
            people = await profiles.list_people(
                session,
                PeopleQuery.model_validate(
                    {
                        "q": query,
                        "page": page,
                        "pageSize": 8,
                        "roleCode": role_code,
                        "fieldCode": field_code,
                    }
                ),
            )
            return [
                person.account_id for person in people.data
            ], page < people.pagination.total_pages

    async def applicants(self, page: int) -> tuple[list[UUID], bool]:
        if (
            self.context.team_id is None
            or self.context.purpose != "applicant_recommendation"
        ):
            raise AppError(403, "FORBIDDEN", "지원자 조회 권한이 없습니다.")
        await self.require_session()
        async with self.database.session() as session:
            result = await application_review.list_applicants(
                session,
                self.context.team_id,
                self.context.principal.account_id,
                ApplicantSearch.model_validate({"page": page, "pageSize": 10}),
            )
        return [
            item.application.id for item in result.data if item.is_selection_candidate
        ], page < result.pagination.total_pages
