"""빈 로컬 *_e2e DB에만 탐색·혼합 사용자 검증용 가상 자료를 원자적으로 넣는다."""

import argparse
import asyncio
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import create_database
from app.models.contests import Contest
from app.repositories.contest_import import insert_contest
from app.rules.catalogs import FieldCode
from app.rules.contests import interpret_deadline, interpret_opening
from scripts.seed_dev_data import (
    counts,
    load_plan,
    seed_teams,
    seed_users,
    validate_seed,
)


class FixtureError(Exception):
    """접속 정보나 자료 원문을 포함하지 않는 E2E 준비 실패."""


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    verified: bool = True
    official: bool = True
    opening_time: time | None = time(9)
    closing_time: time | None = time(18)
    timezone: str | None = "Asia/Seoul"
    starts_in_days: int = -5
    ends_in_days: int = 30


SCENARIOS = (
    Scenario("confirmed", "공식 원문 확인"),
    Scenario("unverified-official", "주최 링크 미확인", verified=False),
    Scenario("collected", "수집 출처만 존재", verified=False, official=False),
    Scenario(
        "date-only",
        "시작과 마감 날짜 보완",
        verified=False,
        official=False,
        opening_time=None,
        closing_time=None,
        timezone=None,
    ),
    Scenario("explicit-midnight", "명시된 자정", opening_time=time.min),
    Scenario("utc", "명시된 UTC 시간대", timezone="UTC"),
    Scenario("closed", "접수 마감", starts_in_days=-40, ends_in_days=-5),
    Scenario(
        "scheduled",
        "접수 예정",
        starts_in_days=5,
        ends_in_days=35,
    ),
    # 공모전 탐색의 12개 페이지와 마지막 1개 페이지를 실제 DB로 검증한다.
    *(Scenario(f"pagination-{index}", f"페이지 이동 {index}") for index in range(1, 6)),
)


def validate_target(value: str) -> URL:
    target = make_url(value)
    if (
        target.drivername != "postgresql+asyncpg"
        or target.host not in {"127.0.0.1", "localhost", "::1"}
        or not target.database
        or not target.database.endswith("_e2e")
        or target.query
    ):
        raise FixtureError("A loopback PostgreSQL *_e2e database is required")
    return target


def build_contests(now: datetime) -> list[tuple[Contest, str]]:
    if now.utcoffset() is None:
        raise ValueError("A timezone-aware fixture reference time is required")
    today = now.astimezone(ZoneInfo("Asia/Seoul")).date()
    fixtures = []
    for index, scenario in enumerate(SCENARIOS):
        opening = interpret_opening(
            source_date=today + timedelta(days=scenario.starts_in_days),
            source_time=scenario.opening_time,
            source_timezone=scenario.timezone,
        )
        closing = interpret_deadline(
            source_date=today + timedelta(days=scenario.ends_in_days),
            source_time=scenario.closing_time,
            source_timezone=scenario.timezone,
        )
        contest = Contest(
            contest_id=uuid5(
                NAMESPACE_URL, f"https://example.test/sku-dreamon/e2e/{scenario.key}"
            ),
            title=f"E2E 가상 공모전 {index + 1:02d} · {scenario.label}",
            organizer_name="통합테스트용 가상 기관",
            official_url=(
                f"https://organizer.example.test/{scenario.key}"
                if scenario.official
                else None
            ),
            source_url=f"https://collection.example.test/{scenario.key}",
            source_metadata={"fixture": "e2e", "scenario": scenario.key},
            eligibility_text="실제 모집이 아닌 격리 E2E 검증용 자료입니다.",
            description=f"{scenario.label}의 공개 상세 계약을 검증합니다.",
            submission_details="가상 결과물 안내",
            awards=None,
            contact_info=None,
            poster_url=None,
            member_limit_kind="range",
            min_members=1,
            max_members=4,
            verified_at=now - timedelta(days=1) if scenario.verified else None,
            registration_opens_at=opening.ends_at,
            registration_closes_at=closing.ends_at,
            open_source_date=opening.source_date,
            open_source_time=opening.source_time,
            open_source_timezone=opening.source_timezone,
            open_effective_timezone=opening.effective_timezone,
            open_timezone_assumed=opening.timezone_assumed,
            close_source_date=closing.source_date,
            close_source_time=closing.source_time,
            close_source_timezone=closing.source_timezone,
            close_effective_timezone=closing.effective_timezone,
            close_time_assumed=closing.time_assumed,
            close_timezone_assumed=closing.timezone_assumed,
            created_at=now - timedelta(minutes=index),
            updated_at=now,
        )
        fixtures.append((contest, list(FieldCode)[index % len(FieldCode)].value))
    return fixtures


async def run(url: str, *, apply: bool) -> dict[str, object]:
    if not apply:
        raise FixtureError("Explicit --apply is required; no database was accessed")
    target = validate_target(url)
    database = create_database(url)
    try:
        async with database.engine.connect() as connection:
            async with connection.begin():
                actual = await connection.scalar(text("SELECT current_database()"))
                if actual != target.database:
                    raise FixtureError(
                        "Connected database does not match the E2E target"
                    )
                # 빈 상태 확인과 적재 사이에 다른 writer가 끼어들지 못하게 한다.
                await connection.execute(
                    text(
                        "LOCK TABLE contests, accounts, teams "
                        "IN SHARE ROW EXCLUSIVE MODE"
                    )
                )
                occupied = await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM contests) "
                        "OR EXISTS (SELECT 1 FROM accounts) "
                        "OR EXISTS (SELECT 1 FROM teams)"
                    )
                )
                if occupied:
                    raise FixtureError("Contests, accounts and teams must all be empty")
                # 기존 seed/service의 commit은 savepoint만 확정하며, 실패하면
                # 외부 transaction이 공고·계정·팀·지원·알림 전체를 롤백한다.
                async with AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as session:
                    reference_at = datetime.now(UTC)
                    for contest, field in build_contests(reference_at):
                        await insert_contest(
                            session, contest, audiences=["unrestricted"], fields=[field]
                        )
                    await session.commit()
                    users_created = await seed_users(session)
                    await session.commit()
                    plan = await load_plan(session, reference_at)
                    expected_teams = len(plan.assignments) * 2
                    teams_created = await seed_teams(session, plan)
                    await validate_seed(session)
                    result = await counts(session)
                    if (
                        result["contests"] != len(SCENARIOS)
                        or users_created != 300
                        or expected_teams == 0
                        or teams_created != expected_teams
                        or result["teams"] != expected_teams
                    ):
                        raise FixtureError("The complete E2E fixture was not created")
                    await session.commit()
        return {"status": "applied", "counts": result}
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()
    try:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise FixtureError("DATABASE_URL is required")
        result = asyncio.run(run(url, apply=args.apply))
    except FixtureError as error:
        print(json.dumps({"error": str(error)}), file=sys.stderr)
        return 2
    except Exception as error:
        # DB 예외에는 접속 정보와 원문 값이 포함될 수 있어 종류만 출력한다.
        print(json.dumps({"error": type(error).__name__}), file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
