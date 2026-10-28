"""생성 근거와 백업이 있는 개발 E2E 잔여물만 검토한 계획에 따라 제거한다."""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Table, delete, or_, select, text, tuple_
from sqlalchemy.engine import RowMapping, make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.db.base import Base
from app.core.db.session import create_database
from app.core.demo_data import ACCOUNT_IDS, TEAM_IDS
from app.models import (
    academic_units,
    ai_chat,
    ai_runs,
    applications,
    auth,
    contests,
    notifications,
    profiles,
    teams,
)

# 모든 FK 대상 모델을 등록한다. 모델 변경을 자동 삭제 정책으로 해석하지 않는다.
_MODELS = (
    academic_units,
    ai_chat,
    ai_runs,
    applications,
    auth,
    contests,
    notifications,
    profiles,
    teams,
)
DELETE_ORDER = (
    "ai_messages",
    "ai_conversations",
    "ai_runs",
    "notifications",
    "application_events",
    "team_memberships",
    "applications",
    "team_recruitment_roles",
    "teams",
    "portfolio_links",
    "profile_interests",
    "profile_desired_roles",
    "profile_skills",
    "profiles",
    "auth_sessions",
    "accounts",
)


class CleanupError(Exception):
    """개인 자료·인증 정보 없이 중단 원인만 전달한다."""


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Evidence(Record):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    pointer: str
    evidenceType: Literal["created-resource", "reviewed-legacy"]
    reason: str | None = None


class Resource(Record):
    kind: Literal["account", "team"]
    id: UUID
    expectedLabel: str = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)


class RetainedAccountApplication(Record):
    """사람이 삭제를 지정한 초기 지원만 허용하며 지원자 계정은 보존한다."""

    id: UUID
    accountId: UUID
    teamId: UUID


class Manifest(Record):
    format: Literal["e2e-cleanup-evidence-v1"] = "e2e-cleanup-evidence-v1"
    resources: list[Resource] = Field(min_length=1)
    retainedAccountApplications: list[RetainedAccountApplication] = Field(
        default_factory=list
    )


class FileHash(Record):
    path: str
    sha256: str


class RowHash(Record):
    key: list[str]
    sha256: str


class Plan(Record):
    format: Literal["e2e-cleanup-plan-v1"] = "e2e-cleanup-plan-v1"
    created_at: datetime
    target: str
    backup: FileHash
    manifest: Manifest
    rows: dict[str, list[RowHash]]
    sha256: str = ""


def digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def target_identity(value: str) -> str:
    try:
        url = make_url(value)
        if (
            url.drivername != "postgresql+asyncpg"
            or url.host not in {"localhost", "127.0.0.1", "::1"}
            or url.database != "wejo_dev"
            or url.query
        ):
            raise CleanupError("explicit_local_wejo_dev_required")
        return f"{url.host}:{url.port or 5432}/{url.database}"
    except (ValueError, TypeError, ArgumentError) as error:
        raise CleanupError("explicit_local_wejo_dev_required") from error


def json_pointer(document: object, pointer: str) -> tuple[object, object]:
    if not pointer.startswith("/"):
        raise CleanupError("invalid_evidence_pointer")
    current = document
    parent = document
    try:
        for piece in pointer.split("/")[1:]:
            key = piece.replace("~1", "/").replace("~0", "~")
            parent = current
            if isinstance(current, dict):
                current = current[key]
            elif isinstance(current, list):
                current = current[int(key)]
            else:
                raise CleanupError("invalid_evidence_pointer")
    except (KeyError, IndexError, ValueError) as error:
        raise CleanupError("invalid_evidence_pointer") from error
    return current, parent


def validate_manifest(manifest: Manifest) -> None:
    seen: set[tuple[str, UUID]] = set()
    for resource in manifest.resources:
        key = (resource.kind, resource.id)
        if key in seen:
            raise CleanupError("duplicate_resource")
        seen.add(key)
        protected = ACCOUNT_IDS if resource.kind == "account" else TEAM_IDS
        if resource.id in protected:
            raise CleanupError("seed_resource_is_protected")
        for evidence in resource.evidence:
            path = Path(evidence.path)
            if not path.is_absolute() or file_hash(path) != evidence.sha256:
                raise CleanupError("evidence_file_changed")
            value, parent = json_pointer(json.loads(path.read_text()), evidence.pointer)
            if value != str(resource.id):
                raise CleanupError("evidence_id_mismatch")
            if evidence.evidenceType == "created-resource":
                if (
                    not isinstance(parent, dict)
                    or parent.get("created") is not True
                    or parent.get("kind") != resource.kind
                ):
                    raise CleanupError("created_resource_evidence_required")
            elif not evidence.reason or not evidence.reason.strip():
                raise CleanupError("legacy_evidence_review_required")
    approved_ids: set[UUID] = set()
    for application in manifest.retainedAccountApplications:
        if (
            application.id in approved_ids
            or ("account", application.accountId) in seen
            or ("team", application.teamId) not in seen
        ):
            raise CleanupError("invalid_retained_account_application")
        approved_ids.add(application.id)


def validate_backup(backup: FileHash) -> None:
    path = Path(backup.path)
    if not path.is_absolute() or file_hash(path) != backup.sha256:
        raise CleanupError("backup_file_changed")
    with path.open("rb") as stream:
        if stream.read(5) != b"PGDMP":
            raise CleanupError("custom_format_pg_dump_required")


def table(name: str) -> Table:
    return Base.metadata.tables[name]


async def collect_rows(
    session: AsyncSession,
    manifest: Manifest,
) -> dict[str, list[RowMapping]]:
    """선택한 계정·팀의 연결 자료를 모으고 경계를 넘는 관계는 거부한다."""
    account_ids = {row.id for row in manifest.resources if row.kind == "account"}
    team_ids = {row.id for row in manifest.resources if row.kind == "team"}
    result: dict[str, list[RowMapping]] = {}

    async def read(name: str, condition: ColumnElement[bool]) -> list[RowMapping]:
        rows = list(
            (
                await session.execute(
                    select(table(name))
                    .where(condition)
                    .order_by(*table(name).primary_key)
                )
            ).mappings()
        )
        result[name] = rows
        return rows

    accounts = table("accounts")
    account_rows = await read("accounts", accounts.c.account_id.in_(account_ids))
    team = table("teams")
    team_rows = await read(
        "teams",
        or_(team.c.team_id.in_(team_ids), team.c.leader_account_id.in_(account_ids)),
    )
    for resource in manifest.resources:
        rows = account_rows if resource.kind == "account" else team_rows
        pk = "account_id" if resource.kind == "account" else "team_id"
        label = "login_id_normalized" if resource.kind == "account" else "name"
        matched = [row for row in rows if row[pk] == resource.id]
        if len(matched) != 1 or matched[0][label] != resource.expectedLabel:
            raise CleanupError("resource_missing_or_label_changed")
    if any(
        row["team_id"] not in team_ids or row["leader_account_id"] not in account_ids
        for row in team_rows
    ):
        raise CleanupError("team_crosses_cleanup_boundary")

    application = table("applications")
    application_rows = await read(
        "applications",
        or_(
            application.c.team_id.in_(team_ids),
            application.c.applicant_account_id.in_(account_ids),
        ),
    )
    approved_applications = {
        item.id: item for item in manifest.retainedAccountApplications
    }
    for approved in approved_applications.values():
        matched = [
            row for row in application_rows if row["application_id"] == approved.id
        ]
        if (
            len(matched) != 1
            or matched[0]["applicant_account_id"] != approved.accountId
            or matched[0]["team_id"] != approved.teamId
            or matched[0]["status"] != "submitted"
            or matched[0]["version"] != 1
        ):
            raise CleanupError("approved_application_missing_or_changed")
    if any(
        row["team_id"] not in team_ids
        or (
            row["applicant_account_id"] not in account_ids
            and row["application_id"] not in approved_applications
        )
        for row in application_rows
    ):
        raise CleanupError("application_crosses_cleanup_boundary")
    application_ids = {row["application_id"] for row in application_rows}
    membership = table("team_memberships")
    membership_rows = await read(
        "team_memberships",
        or_(
            membership.c.team_id.in_(team_ids), membership.c.account_id.in_(account_ids)
        ),
    )
    if any(
        row["team_id"] not in team_ids
        or row["account_id"] not in account_ids
        or (
            row["source_application_id"] is not None
            and row["source_application_id"] not in application_ids
        )
        for row in membership_rows
    ):
        raise CleanupError("membership_crosses_cleanup_boundary")
    membership_ids = {row["team_membership_id"] for row in membership_rows}
    event = table("application_events")
    event_rows = await read(
        "application_events",
        or_(
            event.c.application_id.in_(application_ids),
            event.c.team_id.in_(team_ids),
            event.c.actor_account_id.in_(account_ids),
            event.c.applicant_account_id.in_(account_ids),
            event.c.cause_membership_id.in_(membership_ids),
        ),
    )
    event_ids = {row["application_event_id"] for row in event_rows}
    approved_events: dict[UUID, UUID] = {}
    for row in event_rows:
        event_approval = approved_applications.get(row["application_id"])
        if event_approval is None:
            continue
        if (
            row["applicant_account_id"] != event_approval.accountId
            or row["actor_account_id"] != event_approval.accountId
            or row["team_id"] != event_approval.teamId
            or row["application_version"] != 1
            or row["reason_code"] != "submitted"
            or row["from_status"] is not None
            or row["to_status"] != "submitted"
            or row["cause_event_id"] is not None
            or row["cause_membership_id"] is not None
        ):
            raise CleanupError("approved_application_event_changed")
        approved_events[row["application_event_id"]] = event_approval.accountId
    external_causes = await session.scalar(
        select(event.c.application_event_id)
        .where(
            event.c.cause_event_id.in_(event_ids),
            event.c.application_event_id.not_in(event_ids),
        )
        .limit(1)
    )
    if external_causes is not None or any(
        row["application_id"] not in application_ids
        or row["team_id"] not in team_ids
        or (
            row["applicant_account_id"] not in account_ids
            and row["application_event_id"] not in approved_events
        )
        or (
            row["actor_account_id"] is not None
            and row["actor_account_id"] not in account_ids
            and row["application_event_id"] not in approved_events
        )
        or (
            row["cause_event_id"] is not None and row["cause_event_id"] not in event_ids
        )
        or (
            row["cause_membership_id"] is not None
            and row["cause_membership_id"] not in membership_ids
        )
        for row in event_rows
    ):
        raise CleanupError("event_crosses_cleanup_boundary")
    notification = table("notifications")
    notification_rows = await read(
        "notifications",
        or_(
            notification.c.event_id.in_(event_ids),
            notification.c.recipient_account_id.in_(account_ids),
        ),
    )
    if any(
        row["event_id"] not in event_ids
        or (
            row["recipient_account_id"] not in account_ids
            and approved_events.get(row["event_id"]) != row["recipient_account_id"]
        )
        for row in notification_rows
    ):
        raise CleanupError("notification_crosses_cleanup_boundary")

    for name, column in (
        ("profiles", "profile_id"),
        ("profile_interests", "account_id"),
        ("profile_desired_roles", "account_id"),
        ("profile_skills", "account_id"),
        ("portfolio_links", "portfolio_link_id"),
        ("auth_sessions", "account_id"),
        ("ai_conversations", "account_id"),
    ):
        await read(name, table(name).c[column].in_(account_ids))
    await read(
        "team_recruitment_roles",
        table("team_recruitment_roles").c.team_id.in_(team_ids),
    )
    conversation_ids = {row["ai_conversation_id"] for row in result["ai_conversations"]}
    await read(
        "ai_messages", table("ai_messages").c.ai_conversation_id.in_(conversation_ids)
    )
    session_ids = {row["auth_session_id"] for row in result["auth_sessions"]}
    run = table("ai_runs")
    run_rows = await read(
        "ai_runs",
        or_(
            run.c.account_id.in_(account_ids),
            run.c.auth_session_id.in_(session_ids),
            run.c.team_id.in_(team_ids),
            run.c.application_id.in_(application_ids),
        ),
    )
    if any(
        row["account_id"] not in account_ids
        or row["auth_session_id"] not in session_ids
        or (row["team_id"] is not None and row["team_id"] not in team_ids)
        or (
            row["application_id"] is not None
            and row["application_id"] not in application_ids
        )
        or row["status"] == "pending"
        or row["application_id"] in approved_applications
        for row in run_rows
    ):
        raise CleanupError("ai_run_active_or_crosses_cleanup_boundary")
    return result


def row_hashes(rows: dict[str, list[RowMapping]]) -> dict[str, list[RowHash]]:
    return {
        name: [
            RowHash(
                key=[str(row[col.name]) for col in table(name).primary_key],
                sha256=digest(dict(row)),
            )
            for row in values
        ]
        for name, values in rows.items()
    }


def plan_checksum(plan: Plan) -> str:
    return digest(plan.model_dump(mode="json", exclude={"sha256"}))


async def build_plan(
    session: AsyncSession,
    manifest: Manifest,
    backup: FileHash,
    target: str,
) -> Plan:
    validate_manifest(manifest)
    validate_backup(backup)
    plan = Plan(
        created_at=datetime.now(UTC),
        target=target,
        backup=backup,
        manifest=manifest,
        rows=row_hashes(await collect_rows(session, manifest)),
    )
    plan.sha256 = plan_checksum(plan)
    return plan


async def apply_plan(session: AsyncSession, plan: Plan, target: str) -> dict[str, int]:
    """호출자가 commit한다. 잠금 뒤 근거·연결·행 전체를 다시 확인한다."""
    if plan.target != target or plan.sha256 != plan_checksum(plan):
        raise CleanupError("plan_target_or_checksum_changed")
    validate_manifest(plan.manifest)
    validate_backup(plan.backup)
    await session.execute(text("SET LOCAL lock_timeout = '3s'"))
    # 한 번의 정리 동안 새 연결이 생기는 것을 막으며 일반 SELECT는 계속 허용한다.
    names = ", ".join(f'"{name}"' for name in sorted(DELETE_ORDER))
    await session.execute(text(f"LOCK TABLE {names} IN SHARE ROW EXCLUSIVE MODE"))
    current = await collect_rows(session, plan.manifest)
    if row_hashes(current) != plan.rows:
        raise CleanupError("rows_changed_since_plan")
    counts: dict[str, int] = {}
    for name in DELETE_ORDER:
        values = current[name]
        counts[name] = len(values)
        if values:
            relation = table(name)
            columns = list(relation.primary_key)
            keys = [tuple(row[col.name] for col in columns) for row in values]
            await session.execute(delete(relation).where(tuple_(*columns).in_(keys)))
    return counts


def write_private(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=str)
        stream.write("\n")


async def run(args: argparse.Namespace) -> None:
    url = os.environ.get("DATABASE_URL", "")
    target = target_identity(url)
    database = create_database(url)
    try:
        async with database.session() as session:
            if not args.apply:
                await session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
                )
            if await session.scalar(text("SELECT current_database()")) != "wejo_dev":
                raise CleanupError("unexpected_connected_database")
            if args.apply:
                plan = Plan.model_validate_json(args.apply.read_text())
                counts = await apply_plan(session, plan, target)
                # 디스크 쓰기 실패 시에도 DB가 삭제되지 않도록 커밋 전에 기록한다.
                receipt = args.apply.with_name(args.apply.stem + "-receipt.json")
                write_private(
                    receipt,
                    {
                        "planSha256": plan.sha256,
                        "counts": counts,
                        "status": "transaction_ready",
                    },
                )
                await session.commit()
                print(json.dumps({"applied": counts, "receipt": str(receipt)}))
            else:
                if not args.manifest or not args.backup or not args.output:
                    raise CleanupError("manifest_backup_and_output_required")
                backup_path = args.backup.resolve()
                backup = FileHash(path=str(backup_path), sha256=file_hash(backup_path))
                manifest = Manifest.model_validate_json(args.manifest.read_text())
                plan = await build_plan(session, manifest, backup, target)
                write_private(args.output, plan.model_dump(mode="json"))
                await session.rollback()
                print(
                    json.dumps(
                        {
                            "dryRun": True,
                            "plan": str(args.output),
                            "counts": {
                                key: len(rows) for key, rows in plan.rows.items()
                            },
                        }
                    )
                )
    finally:
        await database.engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", type=Path)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as error:
        # DB 예외에는 쿼리 인자·인증 자료가 포함될 수 있다.
        code = str(error) if isinstance(error, CleanupError) else type(error).__name__
        raise SystemExit(f"cleanup_aborted:{code}") from None


if __name__ == "__main__":
    main()
