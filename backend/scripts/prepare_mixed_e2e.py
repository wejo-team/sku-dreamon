"""복제한 *_e2e DB에서 혼합 사용자 검증 후보만 읽어 JSON으로 반환한다."""

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import URL, RowMapping, make_url
from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.db.session import create_database
from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_TEAM_IDS
from app.security.passwords import verify_password
from scripts.seed_dev_data import DEV_PASSWORD


class CandidateError(Exception):
    """연결 정보나 원문 데이터를 포함하지 않는 준비 실패."""


def validate_target(value: str) -> URL:
    target = make_url(value)
    if (
        target.drivername not in {"postgresql", "postgresql+asyncpg"}
        or target.host not in {"localhost", "127.0.0.1", "::1"}
        or not target.database
        or not target.database.endswith("_e2e")
        or target.query
    ):
        raise CandidateError(
            "A loopback PostgreSQL database ending in _e2e is required"
        )
    return target


async def candidates(
    connection: AsyncConnection, contest_id: UUID, team_id: UUID | None
) -> Sequence[RowMapping]:
    result = await connection.execute(
        text("""
        SELECT a.account_id, a.login_id_normalized, a.password_hash
        FROM accounts a JOIN profiles p ON p.profile_id=a.account_id
        WHERE a.account_id=ANY(CAST(:ids AS uuid[]))
          AND p.is_public AND btrim(p.real_name)<>''
          AND EXISTS (SELECT 1 FROM profile_interests i WHERE i.account_id=a.account_id)
          AND EXISTS (
            SELECT 1 FROM profile_desired_roles r WHERE r.account_id=a.account_id
          )
          AND NOT EXISTS (
            SELECT 1 FROM team_memberships m
            WHERE m.account_id=a.account_id AND m.contest_id=:contest_id
              AND m.ended_at IS NULL
          )
          AND NOT EXISTS (
            SELECT 1 FROM applications ap
            WHERE ap.applicant_account_id=a.account_id AND ap.contest_id=:contest_id
              AND (ap.status IN ('submitted', 'reviewing')
                   OR ap.team_id=CAST(:team_id AS uuid))
          )
        ORDER BY a.account_id LIMIT 2
        """),
        {"ids": list(DEV_ACCOUNT_IDS), "contest_id": contest_id, "team_id": team_id},
    )
    return result.mappings().all()


async def account_record(row: RowMapping) -> dict[str, str]:
    if not await verify_password(row["password_hash"], DEV_PASSWORD):
        raise CandidateError("A selected seed account no longer uses the seed password")
    return {"accountId": str(row["account_id"]), "loginId": row["login_id_normalized"]}


async def prepare(target: URL, contest_id: UUID | None) -> dict[str, object]:
    database = create_database(
        target.set(drivername="postgresql+asyncpg").render_as_string(
            hide_password=False
        )
    )
    try:
        async with database.engine.connect() as connection, connection.begin():
            await connection.execute(
                text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            )
            result: dict[str, object] = {
                "database": target.database,
                "checkedAt": datetime.now(UTC).isoformat(),
            }
            team = None
            choices: Sequence[RowMapping] = ()
            if contest_id is None:
                teams = await connection.execute(
                    text("""
                    SELECT t.team_id, t.contest_id, t.name, t.leader_account_id,
                           t.target_capacity, t.recruitment_closes_at,
                           (SELECT count(*) FROM team_memberships m
                            WHERE m.team_id=t.team_id AND m.ended_at IS NULL) AS members
                    FROM teams t JOIN contests c USING(contest_id)
                    WHERE t.team_id=ANY(CAST(:team_ids AS uuid[]))
                      AND t.leader_account_id=ANY(CAST(:account_ids AS uuid[]))
                      AND t.recruitment_state='open'
                      AND t.recruitment_closes_at>now()+interval '10 minutes'
                      AND c.registration_opens_at<=now()
                      AND c.registration_closes_at>now()+interval '10 minutes'
                    ORDER BY t.team_id
                    """),
                    {
                        "team_ids": list(DEV_TEAM_IDS),
                        "account_ids": list(DEV_ACCOUNT_IDS),
                    },
                )
                for possible in teams.mappings():
                    # 한 명 선발로 원래 팀이 정원 마감되지 않게 여석을 남긴다.
                    if possible["target_capacity"] - possible["members"] < 2:
                        continue
                    choices = await candidates(
                        connection, possible["contest_id"], possible["team_id"]
                    )
                    if len(choices) == 2:
                        team = possible
                        contest_id = team["contest_id"]
                        break
                if team is None:
                    raise CandidateError(
                        "No eligible demo team with two free slots and accounts"
                    )
            else:
                active = await connection.scalar(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM contests WHERE contest_id=:id "
                        "AND registration_opens_at<=now() "
                        "AND registration_closes_at>now()+interval '10 minutes')"
                    ),
                    {"id": contest_id},
                )
                if not active:
                    raise CandidateError(
                        "The selected contest is not open in this clone"
                    )
                choices = await candidates(connection, contest_id, None)
                if len(choices) != 2:
                    raise CandidateError(
                        "No two eligible demo accounts for the selected contest"
                    )
            result["contestId"] = str(contest_id)
            result["demoAccounts"] = [await account_record(row) for row in choices]
            if team is not None:
                leaders = await connection.execute(
                    text(
                        "SELECT account_id, login_id_normalized, password_hash "
                        "FROM accounts WHERE account_id=:id"
                    ),
                    {"id": team["leader_account_id"]},
                )
                leader = leaders.mappings().one()
                result["team"] = {
                    "id": str(team["team_id"]),
                    "name": team["name"],
                    "memberCount": team["members"],
                    "capacity": str(team["target_capacity"]),
                    "recruitmentClosesAt": team["recruitment_closes_at"].isoformat(),
                    "leader": await account_record(leader),
                }
            return result
    finally:
        await database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contest-id", type=UUID)
    args = parser.parse_args()
    try:
        value = os.environ.get("E2E_MIXED_DATABASE_URL")
        if not value:
            raise CandidateError("E2E_MIXED_DATABASE_URL is required")
        result = asyncio.run(prepare(validate_target(value), args.contest_id))
    except CandidateError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    except Exception as error:
        # DB 예외에 접속 주소·비밀값·원문 행이 포함될 수 있어 그대로 출력하지 않는다.
        print(
            f"Mixed E2E candidate lookup failed ({type(error).__name__})",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
