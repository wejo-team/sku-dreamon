"""시연 데이터의 분포·현재 추천 후보와 공고 원본 보존 여부를 읽기 전용으로 진단한다."""

import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import TypedDict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_TEAM_IDS
from app.models.applications import Application, ApplicationEvent
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.notifications import Notification
from app.models.profiles import Profile
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.repositories.ai_runs import can_recommend_team
from app.rules.catalogs import RoleCode
from app.schemas.teams import TeamSearch, TeamSummary
from app.services.teams import build_team_summary, list_teams
from scripts.dev_dataset import (
    DATASET_VERSION,
    MAX_TEAMS_PER_CONTEST,
    MIN_RUNWAY_DAYS,
)


class RecommendationCheck(TypedDict):
    loginId: str
    candidateCount: int
    contestCount: int
    teamIds: list[str]
    paths: list[str]


class KeywordRecommendationCheck(RecommendationCheck):
    query: str
    roleMatchedCandidateCount: int
    roleMatchedContestCount: int


async def contest_fingerprint(session: AsyncSession) -> str:
    """공고의 모든 컬럼·분야·대상을 정렬해 해시하며 원본 내용은 반환하지 않는다."""
    payload: dict[str, object] = {}
    for model in (Contest, ContestField, ContestAudience):
        table = model.__table__
        rows = await session.execute(select(table).order_by(*table.primary_key))
        payload[model.__tablename__] = [dict(row) for row in rows.mappings()]
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def _seed_summaries(
    session: AsyncSession, reference_at: datetime
) -> list[TeamSummary]:
    rows = list(
        await session.execute(
            select(Team, Contest)
            .join(Contest, Contest.contest_id == Team.contest_id)
            .where(Team.team_id.in_(DEV_TEAM_IDS))
            .order_by(Team.created_at.desc(), Team.team_id.desc())
        )
    )
    member_counts = {
        team_id: count
        for team_id, count in await session.execute(
            select(TeamMembership.team_id, func.count())
            .where(
                TeamMembership.team_id.in_(DEV_TEAM_IDS),
                TeamMembership.ended_at.is_(None),
            )
            .group_by(TeamMembership.team_id)
        )
    }
    fields: dict[UUID, list[str]] = defaultdict(list)
    roles: dict[UUID, list[str]] = defaultdict(list)
    for contest_id, field_code in await session.execute(
        select(ContestField.contest_id, ContestField.field_code).where(
            ContestField.contest_id.in_({contest.contest_id for _, contest in rows})
        )
    ):
        fields[contest_id].append(field_code)
    for team_id, role_code in await session.execute(
        select(TeamRecruitmentRole.team_id, TeamRecruitmentRole.role_code).where(
            TeamRecruitmentRole.team_id.in_(DEV_TEAM_IDS)
        )
    ):
        roles[team_id].append(role_code)
    return [
        build_team_summary(
            team,
            contest,
            field_codes=fields[contest.contest_id],
            role_codes=roles[team.team_id],
            member_count=member_counts.get(team.team_id, 0),
            now=reference_at,
        )
        for team, contest in rows
    ]


async def _recommendation_check(
    session: AsyncSession, account_index: int, items: Sequence[TeamSummary]
) -> RecommendationCheck:
    allowed = [
        item
        for item in items
        if await can_recommend_team(
            session, item.id, item.contest_id, DEV_ACCOUNT_IDS[account_index]
        )
    ]
    return {
        "loginId": f"devuser{account_index + 1:03d}",
        "candidateCount": len(allowed),
        "contestCount": len({item.contest_id for item in allowed}),
        "teamIds": [str(item.id) for item in allowed],
        "paths": [f"/teams/{item.id}" for item in allowed],
    }


async def dataset_report(
    session: AsyncSession, reference_at: datetime
) -> dict[str, object]:
    """현재 제품의 모집·추천 조건을 사용한다. 진단 실패는 quality에 기록한다."""
    summaries = await _seed_summaries(session, reference_at)
    recruiting = [item for item in summaries if item.is_recruiting]
    grouped: dict[UUID, list[TeamSummary]] = defaultdict(list)
    for item in summaries:
        grouped[item.contest_id].append(item)
    distribution: list[dict[str, object]] = []
    errors: list[str] = []
    warnings: list[str] = []
    for contest_id, items in sorted(grouped.items(), key=lambda pair: str(pair[0])):
        open_items = [item for item in items if item.is_recruiting]
        distribution.append(
            {
                "contestId": str(contest_id),
                "title": items[0].contest_title,
                "teamCount": len(items),
                "recruitingTeams": len(open_items),
                "fieldCodes": sorted(code.value for code in items[0].field_codes),
                "minDeadline": min(
                    item.recruitment_ends_at for item in items
                ).isoformat(),
                "maxDeadline": max(
                    item.recruitment_ends_at for item in items
                ).isoformat(),
                "teamIds": [str(item.id) for item in items],
            }
        )
        if len(items) > MAX_TEAMS_PER_CONTEST:
            errors.append(
                f"공고 {contest_id}: 팀 {len(items)}개로 "
                f"분산 상한 {MAX_TEAMS_PER_CONTEST}개 초과"
            )
        if not open_items:
            errors.append(f"공고 {contest_id}: 현재 모집 가능한 시드 팀 없음")

    fields = sorted({code.value for item in recruiting for code in item.field_codes})
    roles = Counter(code.value for item in recruiting for code in item.role_codes)
    if not summaries:
        errors.append("시드 팀이 없습니다.")
    if len(fields) < 3:
        errors.append("모집 중인 팀의 공모전 분야가 3개 미만입니다.")
    missing_roles = sorted(set(RoleCode) - roles.keys())
    if missing_roles:
        errors.append(f"모집 중인 팀에 없는 역할: {', '.join(missing_roles)}")
    first_page = await list_teams(
        session,
        TeamSearch.model_validate({"pageSize": 8, "recruitingOnly": True}),
        now=reference_at,
    )
    account_checks = [
        await _recommendation_check(session, index, first_page.data)
        for index in (0, 100, 298, 299)
    ]
    explorer_check = account_checks[2]
    if explorer_check["contestCount"] < 3:
        errors.append("devuser299의 AI 첫 페이지 추천 가능 공고가 3개 미만입니다.")
    role_checks: dict[str, RecommendationCheck] = {}
    keyword_checks: dict[str, KeywordRecommendationCheck] = {}
    for role in RoleCode:
        page = await list_teams(
            session,
            TeamSearch.model_validate(
                {"pageSize": 8, "recruitingOnly": True, "roleCode": role.value}
            ),
            now=reference_at,
        )
        role_checks[role.value] = await _recommendation_check(session, 298, page.data)
        if not role_checks[role.value]["candidateCount"]:
            errors.append(f"devuser299의 {role.display_name} 역할 추천 후보 없음")
        # AI는 위 roleCode 필터를 사용한다. 아래는 탐색 화면의 자유 검색 진단이다.
        keyword_page = await list_teams(
            session,
            TeamSearch.model_validate(
                {"pageSize": 8, "recruitingOnly": True, "q": role.display_name}
            ),
            now=reference_at,
        )
        keyword_result = await _recommendation_check(session, 298, keyword_page.data)
        allowed_ids = set(keyword_result["teamIds"])
        matched = [
            item
            for item in keyword_page.data
            if str(item.id) in allowed_ids and role in item.role_codes
        ]
        keyword_checks[role.value] = {
            **keyword_result,
            "query": role.display_name,
            "roleMatchedCandidateCount": len(matched),
            "roleMatchedContestCount": len({item.contest_id for item in matched}),
        }
        if not matched:
            errors.append(
                f"devuser299의 '{role.display_name}' 키워드 첫 페이지에 "
                "해당 역할의 추천 가능 팀이 없습니다."
            )

    reserved_accounts: list[dict[str, object]] = []
    for index in (298, 299):
        account_id = DEV_ACCOUNT_IDS[index]
        applications = int(
            await session.scalar(
                select(func.count())
                .select_from(Application)
                .where(Application.applicant_account_id == account_id)
            )
            or 0
        )
        memberships = int(
            await session.scalar(
                select(func.count())
                .select_from(TeamMembership)
                .where(
                    TeamMembership.account_id == account_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
            or 0
        )
        public = await session.scalar(
            select(Profile.is_public).where(Profile.profile_id == account_id)
        )
        reserved_accounts.append(
            {
                "loginId": f"devuser{index + 1:03d}",
                "isPublic": public,
                "applications": applications,
                "activeMemberships": memberships,
            }
        )
        if applications or memberships:
            warnings.append(f"devuser{index + 1:03d}에 지원·소속 이력이 있습니다.")
        if index == 298 and (applications or memberships or public is not True):
            errors.append("예약 탐색 계정 devuser299의 공개·미지원·미소속 조건 불충족")
        if index == 299 and public is not False:
            warnings.append("devuser300의 비공개 프로필 시연 조건이 변경됐습니다.")

    application_states = {
        status: count
        for status, count in await session.execute(
            select(Application.status, func.count())
            .where(Application.team_id.in_(DEV_TEAM_IDS))
            .group_by(Application.status)
        )
    }
    notification_states = {
        "read" if read else "unread": count
        for read, count in await session.execute(
            select(Notification.read_at.is_not(None), func.count())
            .join(
                ApplicationEvent,
                Notification.event_id == ApplicationEvent.application_event_id,
            )
            .where(ApplicationEvent.team_id.in_(DEV_TEAM_IDS))
            .group_by(Notification.read_at.is_not(None))
        )
    }
    visibility = {
        "public" if public else "private": count
        for public, count in await session.execute(
            select(Profile.is_public, func.count())
            .where(Profile.profile_id.in_(DEV_ACCOUNT_IDS))
            .group_by(Profile.is_public)
        )
    }
    minimum_days = (
        min(
            (item.recruitment_ends_at - reference_at).total_seconds()
            for item in recruiting
        )
        / 86400
        if recruiting
        else None
    )
    if minimum_days is not None and minimum_days < MIN_RUNWAY_DAYS:
        warnings.append(
            f"가장 이른 모집 마감까지 {MIN_RUNWAY_DAYS}일 미만입니다. "
            "시연 전 재구성을 검토하세요."
        )
    return {
        "recipeVersion": DATASET_VERSION,
        "checkedAt": reference_at.isoformat(),
        "teamCount": len(summaries),
        "contestCount": len(grouped),
        "recruitingTeams": len(recruiting),
        "recruitingFieldCodes": fields,
        "recruitingRoleCounts": dict(sorted(roles.items())),
        "minimumRecruitmentDaysRemaining": minimum_days,
        "distribution": distribution,
        "applicationStates": application_states,
        "notificationReadStates": notification_states,
        "profileVisibility": visibility,
        "recruitmentStates": dict(
            Counter(item.recruitment_state for item in summaries)
        ),
        "closedReasons": dict(
            Counter(item.closed_reason for item in summaries if item.closed_reason)
        ),
        "reservedAccounts": reserved_accounts,
        "aiFirstPage": {
            "teamCount": len(first_page.data),
            "contestCount": len({item.contest_id for item in first_page.data}),
            "accounts": account_checks,
        },
        "roleFirstPages": role_checks,
        "keywordFirstPages": keyword_checks,
        "quality": {"passed": not errors, "errors": errors, "warnings": warnings},
    }
