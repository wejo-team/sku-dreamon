"""로컬 wejo_dev의 공고를 보존하며 버전이 있는 시연 데이터를 구성·검증한다."""

import argparse
import asyncio
import hashlib
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db.session import create_database
from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_NAMESPACE, DEV_TEAM_IDS
from app.models.academic_units import AcademicUnit
from app.models.ai_runs import AiRun
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account
from app.models.contests import Contest, ContestAudience, ContestField
from app.models.notifications import Notification
from app.models.profiles import (
    PortfolioLink,
    Profile,
    ProfileDesiredRole,
    ProfileInterest,
    ProfileSkill,
)
from app.models.teams import Team, TeamMembership, TeamRecruitmentRole
from app.repositories.recruitment_locks import lock_accounts, lock_teams
from app.repositories.team_create import insert_team
from app.rules.catalogs import RoleCode
from app.rules.contests import validate_team_capacity
from app.rules.requests import request_fingerprint
from app.schemas.application_create import ApplicationCreate
from app.schemas.auth import SignupCredentials
from app.schemas.profile_write import ProfileWrite
from app.schemas.team_create import TeamCreate
from app.security.passwords import hash_password
from app.services.application_create import submit_application
from app.services.application_review import change_review_status, select_application
from app.services.applications import cancel_application
from app.services.catalogs import create_academic_unit
from app.services.teams import close_recruitment
from scripts.dev_dataset import (
    DATASET_VERSION,
    RANDOM_SEED,
    ContestCandidate,
    DatasetPlan,
    build_plan,
    team_story,
)
from scripts.dev_dataset_report import contest_fingerprint, dataset_report
from scripts.seed_content import (
    legacy_profile_input,
    legacy_team_content,
)
from scripts.seed_content import (
    profile_input as profile_input,
)
from scripts.seed_content import (
    team_content as team_content,
)

# localhost의 개발 계정에만 쓰는 공개 예시 비밀번호다.
DEV_PASSWORD = "WejoDev2026!Demo"
ACADEMIC_SOURCE = (
    Path(__file__).resolve().parents[2] / "docs/specs/academic-structure.md"
)


def validate_target(url: str) -> None:
    target = make_url(url)
    if (
        target.drivername != "postgresql+asyncpg"
        or target.host not in {"127.0.0.1", "localhost", "::1"}
        or target.database != "wejo_dev"
        or target.query
    ):
        raise ValueError("로컬 wejo_dev만 적재할 수 있습니다.")


def academic_paths() -> list[tuple[str, ...]]:
    """문서의 이관 목록을 개발용으로 읽고 동명 학과의 부모 경로를 보존한다."""
    source = ACADEMIC_SOURCE.read_text(encoding="utf-8")
    section = source.split("## 대학·학부·전공 이관 목록\n", 1)[1].split("\n## ", 1)[0]
    paths: dict[tuple[str, ...], None] = {}
    for line in section.splitlines():
        if not line.startswith("| "):
            continue
        columns = [column.strip() for column in line.strip("|").split("|")]
        if columns[0] in {"단과대학", "---"}:
            continue
        college, department, majors = columns
        paths[(college,)] = None
        paths[(college, department)] = None
        for major in majors.split(" / "):
            if major not in {"—", "전공 미배정"}:
                paths[(college, department, major)] = None
    if not paths or any(not name for path in paths for name in path):
        raise ValueError("문서의 학사 이관 목록을 확인해주세요.")
    return list(paths)


async def seed_academics(
    session: AsyncSession, *, create_missing: bool = True
) -> list[int]:
    # 이 경로는 wejo_dev 전용이다. 문서의 검수 전 목록을 운영 원장으로 승인하지 않는다.
    ids: dict[tuple[str, ...], int] = {}
    for path in academic_paths():
        parent_id = ids[path[:-1]] if len(path) > 1 else None
        matches = list(
            await session.scalars(
                select(AcademicUnit).where(
                    AcademicUnit.name == path[-1], AcademicUnit.parent_id == parent_id
                )
            )
        )
        if len(matches) > 1:
            raise ValueError(
                "같은 학사 경로가 여러 개입니다. 기존 ID 대응을 확인해주세요."
            )
        if not matches and not create_missing:
            raise ValueError("기존 시드 학사 경로가 없어 콘텐츠 갱신을 중단합니다.")
        unit = (
            matches[0]
            if matches
            else await create_academic_unit(session, name=path[-1], parent_id=parent_id)
        )
        if not unit.is_selectable:
            raise ValueError("문서의 학사 경로에 비활성 항목이 있습니다.")
        ids[path] = unit.academic_unit_id
    return [unit_id for path, unit_id in ids.items() if len(path) > 1]


async def seed_users(session: AsyncSession) -> int:
    existing = {
        row.account_id: row.login_id_normalized
        for row in await session.scalars(
            select(Account).where(Account.account_id.in_(DEV_ACCOUNT_IDS))
        )
    }
    missing = [
        i for i, account_id in enumerate(DEV_ACCOUNT_IDS) if account_id not in existing
    ]
    for i, account_id in enumerate(DEV_ACCOUNT_IDS):
        if account_id in existing and existing[account_id] != f"devuser{i + 1:03d}":
            raise ValueError("개발 계정 UUID가 기존 계정과 충돌합니다.")
    if not missing:
        return 0
    academic_ids = await seed_academics(session)
    now = datetime.now(UTC)
    for i in missing:
        account_id = DEV_ACCOUNT_IDS[i]
        credentials = SignupCredentials.model_validate(
            {"loginId": f"devuser{i + 1:03d}", "password": DEV_PASSWORD}
        )
        created = now - timedelta(days=120 - i % 120, minutes=i)
        updated = min(now - timedelta(minutes=i), created + timedelta(days=1 + i % 30))
        session.add(
            Account(
                account_id=account_id,
                login_id_normalized=credentials.login_id,
                password_hash=await hash_password(credentials.password),
                created_at=created,
                credentials_updated_at=created,
            )
        )
        await session.flush()
        data = profile_input(i, academic_ids[i % len(academic_ids)])
        session.add(
            Profile(
                profile_id=account_id,
                real_name=data.real_name,
                is_public=i % 5 != 4,
                profile_image_code=data.profile_image_code,
                academic_status_code=data.academic_status_code,
                grade_code=data.grade_code,
                weekly_availability_code=data.weekly_availability_code,
                academic_unit_id=int(data.academic_unit_id)
                if data.academic_unit_id
                else None,
                experience_state=data.experience_state,
                experience_body=data.experience_body,
                introduction=data.introduction,
                created_at=created,
                updated_at=updated,
                version=1,
            )
        )
        await session.flush()
        session.add_all(
            ProfileInterest(account_id=account_id, field_code=c)
            for c in data.field_codes
        )
        session.add_all(
            ProfileDesiredRole(account_id=account_id, role_code=c)
            for c in data.role_codes
        )
        session.add_all(
            ProfileSkill(account_id=account_id, skill_code=c) for c in data.skill_codes
        )
        if data.portfolio:
            session.add(
                PortfolioLink(
                    portfolio_link_id=account_id,
                    url=str(data.portfolio.url),
                    title=data.portfolio.title,
                )
            )
        if (i + 1) % 50 == 0:
            print(f"사용자 {i + 1}/300 준비", flush=True)
    await session.flush()
    return len(missing)


async def seed_team(
    session: AsyncSession,
    index: int,
    contest: ContestCandidate,
    reference_at: datetime,
) -> Team:
    """신규 시드 팀의 고정 ID·정원·리더 소속을 한 트랜잭션으로 저장한다."""
    now = reference_at
    capacity = max(contest.min_members or 2, 3 + index % 4)
    if contest.max_members is not None:
        capacity = min(capacity, contest.max_members)
    validate_team_capacity(
        capacity,
        kind=contest.member_limit_kind,
        minimum_members=contest.min_members,
        maximum_members=contest.max_members,
    )
    deadline_at = min(
        contest.registration_closes_at, now + timedelta(days=28 + index % 15)
    ).replace(microsecond=0)
    name, introduction, roles = team_story(index, contest)
    body = TeamCreate.model_validate(
        {
            "requestId": str(uuid5(DEV_NAMESPACE, f"team-request:{index}")),
            "contestId": str(contest.contest_id),
            "name": name,
            "introduction": introduction,
            "capacity": str(capacity),
            "roleCodes": roles,
            "recruitmentDeadline": {
                "date": deadline_at.date().isoformat(),
                "time": deadline_at.time().isoformat(),
                "timeZone": "UTC",
            },
        }
    )
    deadline = body.recruitment_deadline.resolve()
    team = Team(
        team_id=DEV_TEAM_IDS[index],
        request_id=body.request_id,
        request_fingerprint=request_fingerprint(
            body.model_dump(mode="json", exclude={"request_id"})
        ),
        contest_id=contest.contest_id,
        leader_account_id=DEV_ACCOUNT_IDS[index],
        name=body.name,
        introduction=body.introduction,
        target_capacity=capacity,
        recruitment_state="open",
        closed_reason=None,
        recruitment_closes_at=deadline.ends_at,
        deadline_source_date=deadline.source_date,
        deadline_source_time=deadline.source_time,
        deadline_source_timezone=deadline.source_timezone,
        deadline_effective_timezone=deadline.effective_timezone,
        deadline_time_assumed=deadline.time_assumed,
        deadline_timezone_assumed=deadline.timezone_assumed,
        version=1,
        # 마지막 생성 구간에도 여러 공고가 섞이도록 계획 순서를 최신순에 반영한다.
        created_at=now - timedelta(minutes=len(DEV_TEAM_IDS) - index),
        updated_at=now,
    )
    membership = TeamMembership(
        team_membership_id=uuid5(DEV_NAMESPACE, f"leader-membership:{index}"),
        team_id=team.team_id,
        contest_id=contest.contest_id,
        account_id=team.leader_account_id,
        source_application_id=None,
        joined_at=now,
    )
    await insert_team(session, team, membership, body.role_codes)
    return team


async def seed_teams(session: AsyncSession, plan: DatasetPlan | None = None) -> int:
    if plan is None:
        plan = await load_plan(session, datetime.now(UTC))
    existing = set(
        await session.scalars(
            select(Team.team_id).where(Team.team_id.in_(DEV_TEAM_IDS))
        )
    )
    public_ids = list(
        await session.scalars(
            select(Profile.profile_id)
            .where(
                Profile.profile_id.in_(DEV_ACCOUNT_IDS[100:298]),
                Profile.is_public.is_(True),
            )
            .order_by(Profile.profile_id)
        )
    )
    added = 0
    for group, contest in enumerate(plan.assignments):
        indices = (group * 2, group * 2 + 1)
        if all(DEV_TEAM_IDS[i] in existing for i in indices):
            continue
        if any(DEV_TEAM_IDS[i] in existing for i in indices):
            raise ValueError(
                "시드 팀 쌍의 일부만 존재합니다. 기존 팀을 보존하기 위해 중단합니다."
            )
        busy = set(
            await session.scalars(
                select(TeamMembership.account_id).where(
                    TeamMembership.contest_id == contest.contest_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
        )
        candidates = [p for p in public_ids if p not in busy]
        random.Random(group + RANDOM_SEED).shuffle(candidates)
        candidates = candidates[:12]
        if any(DEV_ACCOUNT_IDS[i] in busy for i in indices) or len(candidates) < 8:
            raise ValueError("시연 팀장 소속 또는 공개 지원자 수를 확인해주세요.")
        teams = [
            await seed_team(session, i, contest, plan.reference_at) for i in indices
        ]
        await session.commit()
        application_ids: list[list[UUID]] = [[], []]
        for side, team in enumerate(teams):
            for j, candidate in enumerate(candidates):
                role = list(RoleCode)[(j + group) % 6]
                body = ApplicationCreate.model_validate(
                    {
                        "requestId": str(
                            uuid5(
                                DEV_NAMESPACE, f"application:{team.team_id}:{candidate}"
                            )
                        ),
                        "roleCode": role.value,
                        "message": (
                            f"{role.display_name} 역할로 지원합니다. "
                            f"{contest.title}의 주제에 관심이 있습니다. "
                            "모집글의 작업을 작은 단위로 나누어 진행하고 "
                            "초안과 조사 근거를 함께 검토하고 싶습니다. "
                            "구체적인 참여 시간은 팀원들과 조율하겠습니다."
                        ),
                    }
                )
                application, _ = await submit_application(
                    session, candidate, team.team_id, body
                )
                application_ids[side].append(application.id)
                if j % 6 in (2, 3):
                    await change_review_status(
                        session,
                        application.id,
                        team.leader_account_id,
                        1,
                        "reviewing" if j % 6 == 2 else "rejected",
                    )
                elif j % 6 == 4:
                    await cancel_application(session, application.id, candidate, 1)
        for side, team in enumerate(teams):
            selected: list[UUID] = []
            goal = team.target_capacity - 1 if group % 4 == 0 and side == 0 else 1
            for application_id in application_ids[side]:
                application_row = await session.get(
                    Application, application_id, populate_existing=True
                )
                assert application_row is not None
                if application_row.status not in ("submitted", "reviewing"):
                    continue
                await select_application(
                    session,
                    application_id,
                    team.leader_account_id,
                    application_row.version,
                )
                selected.append(application_id)
                if len(selected) >= goal:
                    break
            if group % 4 == 1 and side == 0 and selected:
                row = await session.get(
                    Application, selected[0], populate_existing=True
                )
                assert row is not None
                await cancel_application(
                    session, row.application_id, row.applicant_account_id, row.version
                )
            # 매 공고에 지원 가능한 팀을 남기고 첫 팀에만 종료 사례를 배치한다.
            if group % 4 == 2 and side == 0:
                await session.refresh(team)
                await close_recruitment(
                    session,
                    team.team_id,
                    team.leader_account_id,
                    expected_version=team.version,
                )
        notifications = list(
            await session.scalars(
                select(Notification)
                .join(
                    ApplicationEvent,
                    Notification.event_id == ApplicationEvent.application_event_id,
                )
                .where(ApplicationEvent.team_id.in_([t.team_id for t in teams]))
                .order_by(Notification.notification_id)
            )
        )
        for notification in notifications[::3]:
            notification.read_at = datetime.now(UTC)
        await session.commit()
        added += 2
        if added % 10 == 0:
            print(
                f"팀 {added}/{len(plan.assignments) * 2} 및 지원·알림 준비", flush=True
            )
    return added


PROFILE_FIELDS = (
    "real_name",
    "profile_image_code",
    "academic_status_code",
    "grade_code",
    "weekly_availability_code",
    "academic_unit_id",
    "experience_state",
    "experience_body",
    "introduction",
)


async def _matches_profile(
    session: AsyncSession, profile: Profile, index: int, expected: ProfileWrite
) -> bool:
    if profile.version != 1 or profile.is_public != (index % 5 != 4):
        return False
    values = expected.model_dump(by_alias=False)
    values["academic_unit_id"] = (
        int(expected.academic_unit_id) if expected.academic_unit_id else None
    )
    if any(getattr(profile, field) != values[field] for field in PROFILE_FIELDS):
        return False
    for model, column, codes in (
        (ProfileInterest, ProfileInterest.field_code, expected.field_codes),
        (ProfileDesiredRole, ProfileDesiredRole.role_code, expected.role_codes),
        (ProfileSkill, ProfileSkill.skill_code, expected.skill_codes),
    ):
        stored = set(
            await session.scalars(
                select(column).where(model.account_id == profile.profile_id)
            )
        )
        if stored != set(codes):
            return False
    portfolio = await session.scalar(
        select(PortfolioLink)
        .where(PortfolioLink.portfolio_link_id == profile.profile_id)
        .execution_options(populate_existing=True)
    )
    if expected.portfolio is None:
        return portfolio is None
    return portfolio is not None and (portfolio.url, portfolio.title) == (
        str(expected.portfolio.url),
        expected.portfolio.title,
    )


async def _legacy_team_input(
    session: AsyncSession, team: Team, index: int, contest_title: str
) -> TeamCreate | None:
    name, introduction = legacy_team_content(index, contest_title)
    if (
        team.request_id != uuid5(DEV_NAMESPACE, f"team-request:{index}")
        or team.leader_account_id != DEV_ACCOUNT_IDS[index]
        or team.name != name
        or team.introduction != introduction
    ):
        return None
    roles = [list(RoleCode)[index % 6].value, list(RoleCode)[(index + 1) % 6].value]
    stored = set(
        await session.scalars(
            select(TeamRecruitmentRole.role_code).where(
                TeamRecruitmentRole.team_id == team.team_id
            )
        )
    )
    if stored != set(roles):
        return None
    # 생성 시의 원문 해시로 정원·역할·기한 변경 여부도 확인한다.
    original = TeamCreate.model_validate(
        {
            "requestId": str(team.request_id),
            "contestId": str(team.contest_id),
            "name": name,
            "introduction": introduction,
            "capacity": str(team.target_capacity),
            "roleCodes": roles,
            "recruitmentDeadline": {
                "date": team.deadline_source_date.isoformat(),
                "time": team.deadline_source_time.isoformat()
                if team.deadline_source_time
                else None,
                "timeZone": team.deadline_source_timezone,
            },
        }
    )
    if team.request_fingerprint != request_fingerprint(
        original.model_dump(mode="json", exclude={"request_id"})
    ):
        return None
    return original


async def refresh_content(
    session: AsyncSession, *, users_only: bool = False
) -> dict[str, int]:
    """고정 시드의 구값이 그대로인 행만 교체한다. 생성·삭제·commit은 하지 않는다."""
    result = {
        "profilesUpdated": 0,
        "profilesSkipped": 0,
        "profilesMissing": 0,
        "teamsUpdated": 0,
        "teamsSkipped": 0,
        "teamsMissing": 0,
    }
    # 서비스와 같은 계정 선점으로 프로필 저장/선발과 경쟁하지 않는다.
    # NO KEY UPDATE는 알림 등 다른 업무의 계정 FK 참조를 막지 않는다.
    await lock_accounts(session, DEV_ACCOUNT_IDS)
    accounts = {
        account.account_id: account.login_id_normalized
        for account in await session.scalars(
            select(Account)
            .where(Account.account_id.in_(DEV_ACCOUNT_IDS))
            .execution_options(populate_existing=True)
        )
    }
    # 팀→프로필 순서로 잠그고 잠금 대기 중의 변경까지 다시 읽는다.
    teams = (
        []
        if users_only
        else list(
            await session.scalars(
                select(Team)
                .where(Team.team_id.in_(DEV_TEAM_IDS))
                .order_by(Team.team_id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        )
    )
    profiles = {
        profile.profile_id: profile
        for profile in await session.scalars(
            select(Profile)
            .where(Profile.profile_id.in_(DEV_ACCOUNT_IDS))
            .order_by(Profile.profile_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    }
    academic_ids = (
        await seed_academics(session, create_missing=False) if profiles else []
    )
    now = datetime.now(UTC)
    for index, account_id in enumerate(DEV_ACCOUNT_IDS):
        profile = profiles.get(account_id)
        if profile is None:
            result["profilesMissing"] += 1
            continue
        old = legacy_profile_input(index, academic_ids[index % len(academic_ids)])
        if accounts.get(
            account_id
        ) != f"devuser{index + 1:03d}" or not await _matches_profile(
            session, profile, index, old
        ):
            result["profilesSkipped"] += 1
            continue
        new = profile_input(index, academic_ids[index % len(academic_ids)])
        profile.real_name = new.real_name
        profile.experience_body = new.experience_body
        profile.introduction = new.introduction
        if new.portfolio is not None:
            portfolio = await session.get(PortfolioLink, account_id)
            assert portfolio is not None
            portfolio.title = new.portfolio.title
        profile.version += 1
        profile.updated_at = now
        result["profilesUpdated"] += 1
    if not users_only:
        result["teamsMissing"] = len(DEV_TEAM_IDS) - len(teams)
    for team in teams:
        index = DEV_TEAM_IDS.index(team.team_id)
        title = await session.scalar(
            select(Contest.title).where(Contest.contest_id == team.contest_id)
        )
        if (
            accounts.get(DEV_ACCOUNT_IDS[index]) != f"devuser{index + 1:03d}"
            or title is None
        ):
            result["teamsSkipped"] += 1
            continue
        original = await _legacy_team_input(session, team, index, title)
        if original is None:
            result["teamsSkipped"] += 1
            continue
        name, introduction = team_content(index, title)
        payload = original.model_dump(mode="json", by_alias=True)
        payload.update(name=name, introduction=introduction)
        updated = TeamCreate.model_validate(payload)
        team.name, team.introduction = updated.name, updated.introduction
        team.version += 1
        team.updated_at = now
        # request_id/fingerprint는 최초 생성 재시도 계약이므로 재작성하지 않는다.
        result["teamsUpdated"] += 1
    await session.flush()
    return result


async def counts(session: AsyncSession) -> dict[str, int]:
    models = (
        AcademicUnit,
        Account,
        Profile,
        ProfileInterest,
        ProfileDesiredRole,
        ProfileSkill,
        PortfolioLink,
        Contest,
        ContestField,
        ContestAudience,
        Team,
        TeamRecruitmentRole,
        TeamMembership,
        Application,
        ApplicationEvent,
        Notification,
        AiRun,
    )
    return {
        model.__tablename__: int(
            await session.scalar(select(func.count()).select_from(model)) or 0
        )
        for model in models
    }


async def validate_seed(session: AsyncSession) -> None:
    """교차 행 제약을 검사해 잘못된 지원·소속을 커밋하지 않는다."""
    queries = {
        "capacity": """
            SELECT count(*) FROM teams t
            WHERE t.team_id = ANY(CAST(:ids AS uuid[])) AND
                (SELECT count(*) FROM team_memberships m
                 WHERE m.team_id=t.team_id AND m.ended_at IS NULL) > t.target_capacity
        """,
        "leader": """
            SELECT count(*) FROM teams t
            WHERE t.team_id = ANY(CAST(:ids AS uuid[])) AND
                (SELECT count(*) FROM team_memberships m
                 WHERE m.team_id=t.team_id AND m.account_id=t.leader_account_id
                 AND m.source_application_id IS NULL AND m.ended_at IS NULL) <> 1
        """,
        "selected_membership": """
            SELECT count(*) FROM applications a
            WHERE a.team_id = ANY(CAST(:ids AS uuid[])) AND
                (a.status='selected') <> EXISTS (
                    SELECT 1 FROM team_memberships m
                    WHERE m.source_application_id=a.application_id
                    AND m.ended_at IS NULL)
        """,
        "event_history": """
            SELECT count(*) FROM applications a
            WHERE a.team_id = ANY(CAST(:ids AS uuid[])) AND (
                (SELECT count(*) FROM application_events e
                 WHERE e.application_id=a.application_id) <> a.version
                OR NOT EXISTS (SELECT 1 FROM application_events e
                    WHERE e.application_id=a.application_id
                    AND e.application_version=a.version AND e.to_status=a.status))
        """,
        "pending_membership": """
            SELECT count(*) FROM applications a
            WHERE a.team_id = ANY(CAST(:ids AS uuid[]))
                AND a.status IN ('submitted', 'reviewing') AND EXISTS (
                    SELECT 1 FROM team_memberships m
                    WHERE m.account_id=a.applicant_account_id
                    AND m.contest_id=a.contest_id AND m.ended_at IS NULL)
        """,
    }
    for name, query in queries.items():
        if await session.scalar(text(query), {"ids": list(DEV_TEAM_IDS)}):
            raise ValueError(f"시드 무결성 검사 실패: {name}")


async def load_plan(session: AsyncSession, reference_at: datetime) -> DatasetPlan:
    fields: dict[UUID, list[str]] = {}
    for contest_id, code in await session.execute(
        select(ContestField.contest_id, ContestField.field_code).order_by(
            ContestField.contest_id, ContestField.field_code
        )
    ):
        fields.setdefault(contest_id, []).append(code)
    candidates = [
        ContestCandidate(
            contest_id=contest.contest_id,
            title=contest.title,
            field_codes=tuple(fields.get(contest.contest_id, [])),
            created_at=contest.created_at,
            registration_opens_at=contest.registration_opens_at,
            registration_closes_at=contest.registration_closes_at,
            member_limit_kind=contest.member_limit_kind,
            min_members=contest.min_members,
            max_members=contest.max_members,
        )
        for contest in await session.scalars(select(Contest))
    ]
    return build_plan(candidates, reference_at)


async def clear_seed_teams(session: AsyncSession) -> int:
    """고정 시드 팀의 관계만 자식부터 제거하며 일반 계정이 연결됐으면 중단한다."""
    # 제품과 동일한 계정→공고→팀 순서로 잠가 검사 후 신규 지원이 끼지 않게 한다.
    await lock_accounts(session, DEV_ACCOUNT_IDS)
    contest_ids = select(Team.contest_id).where(Team.team_id.in_(DEV_TEAM_IDS))
    await session.execute(
        select(Contest.contest_id)
        .where(Contest.contest_id.in_(contest_ids))
        .order_by(Contest.contest_id)
        .with_for_update(read=True)
    )
    existing_teams = await lock_teams(session, DEV_TEAM_IDS)
    expected = dict(zip(DEV_TEAM_IDS, DEV_ACCOUNT_IDS, strict=False))
    for team in existing_teams:
        if team.leader_account_id != expected[team.team_id] or team.request_id != uuid5(
            DEV_NAMESPACE, f"team-request:{DEV_TEAM_IDS.index(team.team_id)}"
        ):
            raise ValueError("시드 팀의 고정 식별자가 기존 팀과 충돌합니다.")
    for model, account_column in (
        (Application, Application.applicant_account_id),
        (TeamMembership, TeamMembership.account_id),
        (ApplicationEvent, ApplicationEvent.actor_account_id),
    ):
        if await session.scalar(
            select(func.count())
            .select_from(model)
            .where(
                model.team_id.in_(DEV_TEAM_IDS), account_column.not_in(DEV_ACCOUNT_IDS)
            )
        ):
            raise ValueError("시드 팀에 일반 계정의 활동이 있어 재구성을 중단합니다.")
    event_ids = select(ApplicationEvent.application_event_id).where(
        ApplicationEvent.team_id.in_(DEV_TEAM_IDS)
    )
    if await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.event_id.in_(event_ids),
            Notification.recipient_account_id.not_in(DEV_ACCOUNT_IDS),
        )
    ):
        raise ValueError("시드 팀에 일반 계정의 알림이 있어 재구성을 중단합니다.")
    run_scope = or_(
        AiRun.team_id.in_(DEV_TEAM_IDS),
        AiRun.application_id.in_(
            select(Application.application_id).where(
                Application.team_id.in_(DEV_TEAM_IDS)
            )
        ),
    )
    if await session.scalar(
        select(func.count())
        .select_from(AiRun)
        .where(
            run_scope,
            or_(
                AiRun.account_id.not_in(DEV_ACCOUNT_IDS),
                AiRun.expires_at > datetime.now(UTC),
            ),
        )
    ):
        raise ValueError(
            "시드 팀의 AI 검토 메타데이터가 아직 만료되지 않았거나 "
            "일반 계정 소유입니다."
        )
    count = int(
        await session.scalar(
            select(func.count()).select_from(Team).where(Team.team_id.in_(DEV_TEAM_IDS))
        )
        or 0
    )
    await session.execute(
        delete(Notification).where(Notification.event_id.in_(event_ids))
    )
    # 제품의 메타데이터 보존 기한이 지난 해당 시드 팀 실행만 정리한다.
    # 별도 보존되는 일반 AI 대화·메시지에는 접근하지 않는다.
    await session.execute(delete(AiRun).where(run_scope))
    # 폐기 사건끼리의 자기 참조는 같은 DELETE 문에서 함께 지운다.
    for related_model in (
        ApplicationEvent,
        TeamMembership,
        Application,
        TeamRecruitmentRole,
        Team,
    ):
        await session.execute(
            delete(related_model).where(related_model.team_id.in_(DEV_TEAM_IDS))
        )
    await session.flush()
    return count


def generator_fingerprint() -> str:
    """제작 코드와 학사 입력이 같았는지 확인할 작은 식별자만 기록한다."""
    digest = hashlib.sha256()
    for path in (
        Path(__file__),
        Path(__file__).with_name("dev_dataset.py"),
        Path(__file__).with_name("dev_dataset_report.py"),
        Path(__file__).with_name("seed_content.py"),
        Path(__file__).parents[1] / "app/core/demo_data.py",
        ACADEMIC_SOURCE,
    ):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


async def run(
    *,
    apply: bool,
    users_only: bool,
    rebuild_teams: bool = False,
    check: bool = False,
    refresh: bool = False,
) -> dict[str, object]:
    if (
        (users_only and rebuild_teams)
        or (refresh and rebuild_teams)
        or (check and (apply or users_only or rebuild_teams or refresh))
    ):
        raise ValueError(
            "--check는 단독 사용하며 --users-only와 재구성은 함께 쓸 수 없습니다."
        )
    url = str(Settings().database_url)
    validate_target(url)
    reference_at = datetime.now(UTC).replace(microsecond=0)
    database = create_database(url)
    try:
        async with database.engine.connect() as connection:
            async with connection.begin() as transaction:
                if check:
                    await connection.execute(text("SET TRANSACTION READ ONLY"))
                if (
                    await connection.scalar(text("SELECT current_database()"))
                    != "wejo_dev"
                ):
                    raise ValueError("wejo_dev가 아닌 DB입니다.")
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(20261026, 300)")
                )
                schema_revision = await connection.scalar(
                    text("SELECT version_num FROM alembic_version")
                )
                # 서비스 commit은 savepoint만 확정한다. 전체 적재는 마지막에 확정한다.
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    before = await counts(session)
                    catalog_before = await contest_fingerprint(session)
                    plan = await load_plan(session, reference_at)
                    if rebuild_teams and not plan.assignments:
                        raise ValueError(
                            "배정 가능한 공모전이 없어 기존 팀을 보존합니다."
                        )
                    refreshed = None
                    added = teams_added = teams_removed = 0
                    if refresh:
                        refreshed = await refresh_content(
                            session, users_only=users_only
                        )
                    elif not check:
                        added = await seed_users(session)
                        teams_removed = (
                            await clear_seed_teams(session) if rebuild_teams else 0
                        )
                        await session.commit()
                        if not users_only:
                            teams_added = await seed_teams(session, plan)
                    await validate_seed(session)
                    await session.commit()
                    after = await counts(session)
                    report = await dataset_report(session, reference_at)
                    catalog_after = await contest_fingerprint(session)
                    if catalog_before != catalog_after:
                        raise ValueError("공모전 원본이 변경되어 적재를 중단합니다.")
                    await session.commit()
                if not apply:
                    await transaction.rollback()
                return {
                    "datasetVersion": DATASET_VERSION,
                    "schemaRevision": schema_revision,
                    "generatorSha256": generator_fingerprint(),
                    "catalogSha256": catalog_before,
                    "referenceAt": reference_at.isoformat(),
                    "status": "checked"
                    if check
                    else "applied"
                    if apply
                    else "rolled_back",
                    "rebuildTeams": rebuild_teams,
                    "usersCreated": added,
                    "teamsRemoved": teams_removed,
                    "teamsCreated": teams_added,
                    "before": before,
                    "after": after,
                    "usersOnly": users_only,
                    "contentRefresh": refreshed,
                    "plan": {
                        "contestIds": [str(c.contest_id) for c in plan.contests],
                        "teamCount": len(plan.assignments) * 2,
                        "warnings": list(plan.warnings),
                    },
                    "validation": report,
                }
    finally:
        await database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply", action="store_true", help="검증 후 실제 저장 (기본은 롤백)"
    )
    parser.add_argument(
        "--users-only", action="store_true", help="사용자·프로필만 준비"
    )
    parser.add_argument(
        "--refresh-content",
        action="store_true",
        help="생성 없이 구시드 원문과 일치하는 프로필·팀만 갱신 (기본은 롤백)",
    )
    parser.add_argument(
        "--rebuild-teams",
        action="store_true",
        help="고정 가상 팀·지원·알림을 v2 분포로 재구성 (계정·프로필·공고 유지)",
    )
    parser.add_argument(
        "--check", action="store_true", help="쓰기 없이 현재 시연 품질 검사"
    )
    parser.add_argument(
        "--report", type=Path, help="실행 보고서를 저장할 로컬 JSON 경로"
    )
    args = parser.parse_args()
    result = asyncio.run(
        run(
            apply=args.apply,
            users_only=args.users_only,
            rebuild_teams=args.rebuild_teams,
            check=args.check,
            refresh=args.refresh_content,
        )
    )
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    report_path = args.report or (
        Path(__file__).resolve().parents[2]
        / "data/reports/dev-dataset"
        / DATASET_VERSION
        / f"{datetime.now(UTC):%Y%m%dT%H%M%S%fZ}.json"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    print(f"보고서: {report_path.resolve()}")
    quality = result["validation"]
    if args.check and isinstance(quality, dict):
        assessment = quality["quality"]
        if not assessment["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
