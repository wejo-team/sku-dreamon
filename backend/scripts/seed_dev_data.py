"""로컬 wejo_dev에 공고를 변경하지 않는 재실행 가능한 시연 데이터를 넣는다."""

import argparse
import asyncio
import json
import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid5

from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.db.session import create_database
from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_NAMESPACE, DEV_TEAM_IDS
from app.models.academic_units import AcademicUnit
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
from app.repositories.team_create import insert_team
from app.rules.catalogs import (
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)
from app.rules.contests import validate_team_capacity
from app.rules.requests import request_fingerprint
from app.schemas.application_create import ApplicationCreate
from app.schemas.auth import Credentials
from app.schemas.profile_write import ProfileWrite
from app.schemas.team_create import TeamCreate
from app.security.passwords import hash_password
from app.services.application_create import submit_application
from app.services.application_review import change_review_status, select_application
from app.services.applications import cancel_application
from app.services.catalogs import create_academic_unit
from app.services.teams import close_recruitment

# localhost의 개발 계정에만 쓰는 공개 예시 비밀번호다.
DEV_PASSWORD = "WejoDev2026!Demo"
ACADEMIC_SOURCE = (
    Path(__file__).resolve().parents[2] / "docs/specs/academic-structure.md"
)
FAMILY_NAMES = tuple(
    "김 이 박 최 정 강 조 윤 장 임 한 오 서 신 권 황 안 송 전 홍".split()
)
GIVEN_NAMES = tuple(
    "민준 서연 지호 하은 도윤 수아 예준 지우 시우 서윤 유진 하준 은서 준서 채원".split()
)
ROLE_SKILLS = (
    ("service_planning", "document_writing", "market_research"),
    ("ui_ux", "graphic_design", "presentation_design"),
    ("programming", "data_analysis", "data_visualization"),
    ("social_media_marketing", "content_planning", "video_editing"),
    ("market_research", "data_analysis", "document_writing"),
    ("public_speaking", "presentation_design", "content_planning"),
)
TOPICS = (
    "캠퍼스 생활을 편리하게 만드는 서비스",
    "지역 상권을 연결하는 플랫폼",
    "일상 속 탄소 절감 프로젝트",
    "누구나 쉽게 배우는 교육 콘텐츠",
    "접근성을 고려한 모바일 경험",
    "데이터로 찾는 지역 문제 해결책",
    "청년의 건강한 생활 습관",
    "문화와 기술을 연결하는 전시",
    "작은 브랜드를 위한 콘텐츠",
    "지역 사회에 도움이 되는 공공 서비스",
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


def profile_input(index: int, academic_id: int) -> ProfileWrite:
    """실제 사람의 정보를 사용하지 않고 enum과 입력 DTO에 맞는 프로필을 만든다."""
    rng = random.Random(20261026 + index)
    role = list(RoleCode)[index % len(RoleCode)]
    fields = rng.sample(list(FieldCode), 1 + index % 3)
    roles = [role]
    if index % 2:
        roles.append(list(RoleCode)[(index + 1) % len(RoleCode)])
    skills = list(ROLE_SKILLS[index % len(RoleCode)])
    if index % 4 == 0:
        skills = []
    elif index % 3 == 0:
        skills = list(dict.fromkeys([*skills, rng.choice(list(SkillCode)).value]))
    state = (
        "unspecified" if index % 10 == 9 else "none" if index % 3 == 0 else "provided"
    )
    status = (
        "graduated"
        if index % 12 == 10
        else "on_leave"
        if index % 12 == 11
        else "enrolled"
    )
    sparse = index % 10 == 9
    name = (
        FAMILY_NAMES[index // len(GIVEN_NAMES)] + GIVEN_NAMES[index % len(GIVEN_NAMES)]
    )
    return ProfileWrite.model_validate(
        {
            "expectedVersion": "0",
            "realName": name,
            "profileImageCode": None
            if sparse
            else list(ProfileImageCode)[(index // 5) % 5].value,
            "academicStatusCode": None if sparse else status,
            "gradeCode": None
            if sparse
            else "not_applicable"
            if status == "graduated"
            else list(GradeCode)[index % 4].value,
            "weeklyAvailabilityCode": None
            if sparse
            else list(WeeklyAvailabilityCode)[index % 4].value,
            "academicUnitId": None if sparse else str(academic_id),
            "experienceState": state,
            "experienceBody": (
                f"{TOPICS[index % 10]}를 주제로 팀 프로젝트에 참여했습니다. "
                f"{role.display_name} 역할로 문제 정의부터 결과 발표까지 "
                "진행하고 회고를 정리했습니다."
            )
            if state == "provided"
            else None,
            "introduction": None
            if sparse
            else (
                f"{fields[0].display_name}에 관심이 있는 {name}입니다. "
                f"{role.display_name} 역할로 {TOPICS[index % 10]}를 "
                "함께 만들고 싶습니다. "
                + (
                    "주말 온라인 회의가 편합니다."
                    if index % 2
                    else "평일 저녁에 꾸준히 참여할 수 있습니다."
                )
            ),
            "fieldCodes": [c.value for c in fields],
            "roleCodes": [c.value for c in roles],
            "skillCodes": skills,
            "portfolio": None
            if sparse or index % 3 == 0
            else {
                "url": f"https://example.com/portfolio/devuser{index + 1:03d}",
                "title": f"{name}의 개발용 예시 포트폴리오",
            },
        }
    )


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


async def seed_academics(session: AsyncSession) -> list[int]:
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
        credentials = Credentials.model_validate(
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


async def seed_team(session: AsyncSession, index: int, contest: Contest) -> Team:
    """신규 시드 팀의 고정 ID·정원·리더 소속을 한 트랜잭션으로 저장한다."""
    now = datetime.now(UTC)
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
        contest.registration_closes_at, now + timedelta(days=7 + index % 21)
    ).replace(microsecond=0)
    roles = [list(RoleCode)[index % 6].value, list(RoleCode)[(index + 1) % 6].value]
    names = (
        "드림메이커",
        "캠퍼스랩",
        "넥스트스텝",
        "아이디어온",
        "함께도전",
        "그린웨이",
    )
    body = TeamCreate.model_validate(
        {
            "requestId": str(uuid5(DEV_NAMESPACE, f"team-request:{index}")),
            "contestId": str(contest.contest_id),
            "name": f"{names[index % 6]} {index + 1:02d}",
            "introduction": (
                f"[개발용 가상팀] {contest.title}에 함께 도전할 팀원을 찾습니다. "
                f"{TOPICS[index % 10]}에 관심이 있습니다. "
                "매주 진행 상황을 공유하고 역할별 결과물을 함께 검토합니다."
            ),
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
        created_at=now,
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


async def seed_teams(session: AsyncSession) -> int:
    now = datetime.now(UTC)
    contests = list(
        await session.scalars(
            select(Contest)
            .where(
                Contest.registration_opens_at <= now,
                Contest.registration_closes_at > now + timedelta(hours=1),
                Contest.member_limit_kind.in_(("range", "unlimited")),
                (Contest.max_members.is_(None) | (Contest.max_members >= 2)),
            )
            .order_by(Contest.contest_id)
        )
    )
    if not contests:
        print(
            "현재 접수 중이며 팀 인원이 확인된 공모전이 없어 팀 연결은 보류합니다.",
            flush=True,
        )
        return 0
    existing = set(
        await session.scalars(
            select(Team.team_id).where(Team.team_id.in_(DEV_TEAM_IDS))
        )
    )
    public_ids = list(
        await session.scalars(
            select(Profile.profile_id)
            .where(
                Profile.profile_id.in_(DEV_ACCOUNT_IDS[100:]),
                Profile.is_public.is_(True),
            )
            .order_by(Profile.profile_id)
        )
    )
    added = 0
    for group in range(50):
        indices = (group * 2, group * 2 + 1)
        if all(DEV_TEAM_IDS[i] in existing for i in indices):
            continue
        if any(DEV_TEAM_IDS[i] in existing for i in indices):
            raise ValueError(
                "시드 팀 쌍의 일부만 존재합니다. 기존 팀을 보존하기 위해 중단합니다."
            )
        contest = contests[group % len(contests)]
        busy = set(
            await session.scalars(
                select(TeamMembership.account_id).where(
                    TeamMembership.contest_id == contest.contest_id,
                    TeamMembership.ended_at.is_(None),
                )
            )
        )
        candidates = [p for p in public_ids if p not in busy]
        random.Random(group + 20261026).shuffle(candidates)
        candidates = candidates[:12]
        if any(DEV_ACCOUNT_IDS[i] in busy for i in indices) or len(candidates) < 8:
            continue
        teams = [await seed_team(session, i, contest) for i in indices]
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
                            f"{TOPICS[group % 10]}에 관심이 있고, "
                            f"주당 {5 + j % 4 * 5}시간 참여할 수 있습니다. "
                            "일정과 진행 상황을 팀원들과 꾸준히 공유하겠습니다."
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
            if group % 3 == 0 and side == 1:
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
            print(f"팀 {added}/100 및 지원·알림 준비", flush=True)
    return added


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


async def run(*, apply: bool, users_only: bool) -> dict[str, object]:
    url = str(Settings().database_url)
    validate_target(url)
    database = create_database(url)
    try:
        async with database.engine.connect() as connection:
            async with connection.begin() as transaction:
                if (
                    await connection.scalar(text("SELECT current_database()"))
                    != "wejo_dev"
                ):
                    raise ValueError("wejo_dev가 아닌 DB입니다.")
                await connection.execute(
                    text("SELECT pg_advisory_xact_lock(20261026, 300)")
                )
                # 서비스 commit은 savepoint만 확정한다. 전체 적재는 마지막에 확정한다.
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    before = await counts(session)
                    added = await seed_users(session)
                    await session.commit()
                    teams_added = 0 if users_only else await seed_teams(session)
                    await validate_seed(session)
                    await session.commit()
                    after = await counts(session)
                    await session.commit()
                if not apply:
                    await transaction.rollback()
                return {
                    "status": "applied" if apply else "rolled_back",
                    "usersCreated": added,
                    "teamsCreated": teams_added,
                    "before": before,
                    "after": after,
                    "usersOnly": users_only,
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
    args = parser.parse_args()
    result = asyncio.run(run(apply=args.apply, users_only=args.users_only))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
