"""실제 FK가 있는 격리 스키마에서 잔여물 정리와 보호·경합을 검증한다."""

import json
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.db.base import Base
from app.core.db.session import Database
from app.core.demo_data import DEV_ACCOUNT_IDS
from app.models.ai_chat import AiConversation, AiMessage
from app.models.ai_runs import AiRun
from app.models.applications import Application, ApplicationEvent
from app.models.auth import Account, AuthSession
from app.models.contests import Contest
from app.models.notifications import Notification
from app.models.profiles import Profile, ProfileInterest
from app.models.teams import Team, TeamMembership
from app.services import application_review
from scripts.cleanup_e2e_data import (
    CleanupError,
    Evidence,
    FileHash,
    Manifest,
    Resource,
    RetainedAccountApplication,
    apply_plan,
    build_plan,
    file_hash,
)
from tests.integration.team_management_support import (
    NOW,
    seed_account,
    seed_application,
    seed_contest,
    seed_team,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]
TARGET = "127.0.0.1:55432/wejo_dev"


@pytest_asyncio.fixture
async def cleanup_database(database_url: str) -> AsyncIterator[Database]:
    schema = f"e2e_cleanup_{uuid4().hex}"
    engine = create_async_engine(
        database_url,
        execution_options={"schema_translate_map": {None: schema}},
        connect_args={"server_settings": {"search_path": schema}},
    )
    database = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.run_sync(Base.metadata.create_all)
        yield database
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def setup_resources(
    database: Database, tmp_path: Path
) -> tuple[Manifest, FileHash]:
    async with database.session() as session:
        owner = await seed_account(session)
        member = await seed_account(session)
        contest = await seed_contest(session)
        team = await seed_team(session, contest, owner)
        application = await seed_application(session, team, member)
        event = ApplicationEvent(
            application_event_id=uuid4(),
            application_id=application.application_id,
            team_id=team.team_id,
            contest_id=contest.contest_id,
            applicant_account_id=member.account_id,
            application_version=1,
            from_status=None,
            to_status="submitted",
            actor_account_id=member.account_id,
            reason_code="submitted",
            cause_event_id=None,
            cause_membership_id=None,
            occurred_at=NOW,
        )
        session.add(event)
        await session.flush()
        session.add(
            Notification(
                event_id=event.application_event_id,
                recipient_account_id=owner.account_id,
                kind="new_application",
            )
        )
        preserved = await seed_account(session, real_name="보존할 수동 사용자")
        await seed_team(session, contest, preserved)
        await session.commit()
        candidates = [
            ("account", owner.account_id, owner.login_id_normalized),
            ("account", member.account_id, member.login_id_normalized),
            ("team", team.team_id, team.name),
        ]
    source = tmp_path / "resources.json"
    source.write_text(
        json.dumps(
            {
                "resources": [
                    {"kind": kind, "id": str(identity), "created": True}
                    for kind, identity, _label in candidates
                ]
            }
        )
    )
    manifest = Manifest(
        resources=[
            Resource(
                kind=kind,
                id=identity,
                expectedLabel=label,
                evidence=[
                    Evidence(
                        path=str(source),
                        sha256=file_hash(source),
                        pointer=f"/resources/{index}/id",
                        evidenceType="created-resource",
                    )
                ],
            )
            for index, (kind, identity, label) in enumerate(candidates)
        ]
    )
    backup = tmp_path / "backup.dump"
    backup.write_bytes(b"PGDMPtest-backup-placeholder")
    return manifest, FileHash(path=str(backup), sha256=file_hash(backup))


async def snapshot(database: Database) -> dict[str, list[tuple[object, ...]]]:
    async with database.session() as session:
        return {
            table.name: [
                tuple(row)
                for row in await session.execute(
                    select(table).order_by(*table.primary_key)
                )
            ]
            for table in Base.metadata.sorted_tables
        }


async def test_dry_run_then_apply_removes_exact_graph_and_keeps_manual_data(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    before = await snapshot(cleanup_database)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
        await session.rollback()
    assert await snapshot(cleanup_database) == before
    assert "password_hash" not in plan.model_dump_json()
    assert "test-only-not-a-real-password-hash" not in plan.model_dump_json()
    async with cleanup_database.session() as session:
        counts = await apply_plan(session, plan, TARGET)
        await session.commit()
    after = await snapshot(cleanup_database)
    assert counts["teams"] == 1 and counts["accounts"] == 2
    assert counts["application_events"] == 1 and counts["notifications"] == 1
    assert len(after["teams"]) == len(after["accounts"]) == 1
    assert after["contests"] == before["contests"]
    assert after["contest_fields"] == before["contest_fields"]
    assert after["contest_audiences"] == before["contest_audiences"]
    for name in (
        "accounts",
        "profiles",
        "teams",
        "team_memberships",
        "team_recruitment_roles",
    ):
        assert set(after[name]).issubset(before[name])


async def test_edit_between_plan_and_apply_aborts_without_partial_deletion(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
    async with cleanup_database.session() as session:
        profile = await session.get(Profile, manifest.resources[0].id)
        assert profile is not None
        profile.introduction = "계획을 만든 뒤 사용자가 수정한 소개"
        await session.commit()
    before = await snapshot(cleanup_database)
    async with cleanup_database.session() as session:
        with pytest.raises(CleanupError, match="rows_changed_since_plan"):
            await apply_plan(session, plan, TARGET)
        await session.rollback()
    assert await snapshot(cleanup_database) == before


async def test_new_external_applicant_protects_all_candidates(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
    async with cleanup_database.session() as session:
        outsider = await seed_account(session)
        team = await session.get(Team, manifest.resources[-1].id)
        assert team is not None
        await seed_application(session, team, outsider)
        await session.commit()
    before = await snapshot(cleanup_database)
    async with cleanup_database.session() as session:
        with pytest.raises(CleanupError, match="application_crosses_cleanup_boundary"):
            await apply_plan(session, plan, TARGET)
        await session.rollback()
    assert await snapshot(cleanup_database) == before


async def test_later_delete_failure_rolls_back_earlier_deletes(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
    before = await snapshot(cleanup_database)
    # DB의 예상하지 못한 추가 참조도 FK를 우회하지 않고 전체 롤백한다.
    async with cleanup_database.session() as session:
        await session.execute(
            text(
                "CREATE TABLE external_reference "
                "(account_id uuid REFERENCES accounts(account_id))"
            )
        )
        await session.execute(
            text("INSERT INTO external_reference VALUES (:id)"),
            {"id": manifest.resources[0].id},
        )
        await session.commit()
    async with cleanup_database.session() as session:
        with pytest.raises(Exception, match="ForeignKeyViolationError"):
            await apply_plan(session, plan, TARGET)
        await session.rollback()
    assert await snapshot(cleanup_database) == before


async def test_wrong_target_or_tampered_plan_has_no_writes(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
    before = await snapshot(cleanup_database)
    async with cleanup_database.session() as session:
        with pytest.raises(CleanupError, match="plan_target_or_checksum_changed"):
            await apply_plan(session, plan, "localhost:9999/wejo_dev")
        plan.rows["teams"] = []
        with pytest.raises(CleanupError, match="plan_target_or_checksum_changed"):
            await apply_plan(session, plan, TARGET)
    assert await snapshot(cleanup_database) == before


async def test_selection_cause_events_and_membership_delete_without_fk_bypass(
    cleanup_database: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    monkeypatch.setattr(application_review, "_utcnow", lambda: NOW)
    async with cleanup_database.session() as session:
        team = await session.get(Team, manifest.resources[-1].id)
        member = await session.get(Account, manifest.resources[1].id)
        assert team is not None and member is not None
        contest = await session.get(Contest, team.contest_id)
        assert contest is not None
        owner_two = await seed_account(session)
        team_two = await seed_team(session, contest, owner_two)
        await seed_application(session, team_two, member)
        await session.commit()
        application = await session.scalar(
            select(Application).where(
                Application.team_id == team.team_id,
            )
        )
        assert application is not None
        await application_review.select_application(
            session,
            application.application_id,
            team.leader_account_id,
            1,
        )
        extra = [
            ("account", owner_two.account_id, owner_two.login_id_normalized),
            ("team", team_two.team_id, team_two.name),
        ]
    evidence_path = tmp_path / "extra-resources.json"
    evidence_path.write_text(
        json.dumps(
            {
                "resources": [
                    {"kind": kind, "id": str(identity), "created": True}
                    for kind, identity, _label in extra
                ]
            }
        )
    )
    for index, (kind, identity, label) in enumerate(extra):
        manifest.resources.append(
            Resource(
                kind=kind,
                id=identity,
                expectedLabel=label,
                evidence=[
                    Evidence(
                        path=str(evidence_path),
                        sha256=file_hash(evidence_path),
                        pointer=f"/resources/{index}/id",
                        evidenceType="created-resource",
                    )
                ],
            )
        )
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
        assert len(plan.rows["application_events"]) == 3
        counts = await apply_plan(session, plan, TARGET)
        await session.commit()
    assert counts["team_memberships"] == 3
    assert counts["application_events"] == 3
    after = await snapshot(cleanup_database)
    assert len(after["accounts"]) == len(after["teams"]) == 1
    assert after["applications"] == after["application_events"] == []


async def add_retained_account_application(
    database: Database,
    manifest: Manifest,
) -> RetainedAccountApplication:
    async with database.session() as session:
        retained = Account(
            account_id=DEV_ACCOUNT_IDS[0],
            login_id_normalized="devuser001",
            password_hash="retained-secret-hash",
        )
        session.add(retained)
        await session.flush()
        session.add_all(
            [
                Profile(
                    profile_id=retained.account_id,
                    real_name="직접 편집한 프로필",
                    introduction="보존할 소개",
                    is_public=True,
                ),
                ProfileInterest(account_id=retained.account_id, field_code="design"),
                AuthSession(
                    account_id=retained.account_id,
                    token_hash=b"s" * 32,
                    created_at=NOW,
                    last_seen_at=NOW,
                    expires_at=NOW + timedelta(days=1),
                ),
            ]
        )
        conversation = AiConversation(
            account_id=retained.account_id, created_at=NOW, updated_at=NOW
        )
        session.add(conversation)
        await session.flush()
        session.add(
            AiMessage(
                ai_conversation_id=conversation.ai_conversation_id,
                client_message_id=uuid4(),
                request_id=uuid4(),
                role="user",
                content="보존할 수동 대화",
                attempt=1,
                model=None,
                source_references=[],
                created_at=NOW,
            )
        )
        team = await session.get(Team, manifest.resources[-1].id)
        assert team is not None
        application = await seed_application(session, team, retained)
        event = ApplicationEvent(
            application_id=application.application_id,
            team_id=team.team_id,
            contest_id=team.contest_id,
            applicant_account_id=retained.account_id,
            application_version=1,
            from_status=None,
            to_status="submitted",
            actor_account_id=retained.account_id,
            reason_code="submitted",
            cause_event_id=None,
            cause_membership_id=None,
            occurred_at=NOW,
        )
        session.add(event)
        await session.flush()
        for recipient in (team.leader_account_id, retained.account_id):
            session.add(
                Notification(
                    event_id=event.application_event_id,
                    recipient_account_id=recipient,
                    kind="new_application",
                )
            )
        await session.commit()
        return RetainedAccountApplication(
            id=application.application_id,
            accountId=retained.account_id,
            teamId=team.team_id,
        )


async def test_explicit_single_application_is_deleted_and_seed_account_is_preserved(
    cleanup_database: Database,
    tmp_path: Path,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    approved = await add_retained_account_application(cleanup_database, manifest)
    before = await snapshot(cleanup_database)
    async with cleanup_database.session() as session:
        with pytest.raises(CleanupError, match="application_crosses_cleanup_boundary"):
            await build_plan(session, manifest, backup, TARGET)
    manifest.retainedAccountApplications.append(approved)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
        assert all(
            str(approved.accountId) not in row.key for row in plan.rows["accounts"]
        )
        counts = await apply_plan(session, plan, TARGET)
        await session.commit()
    after = await snapshot(cleanup_database)
    assert counts["applications"] == counts["application_events"] == 2
    assert counts["notifications"] == 3
    assert len(after["accounts"]) == len(after["profiles"]) == 2
    for name in ("accounts", "profiles", "profile_interests"):
        assert set(after[name]).issubset(before[name])
    for name in ("auth_sessions", "ai_conversations", "ai_messages", "contests"):
        assert after[name] == before[name]
    async with cleanup_database.session() as session:
        retained = await session.get(Account, approved.accountId)
        assert retained is not None and retained.password_hash == "retained-secret-hash"
        assert await session.get(Application, approved.id) is None


@pytest.mark.parametrize(
    "change",
    ["status", "unapproved_application", "wrong_account", "membership", "ai_reference"],
)
async def test_application_exception_cannot_expand_or_accept_changed_state(
    cleanup_database: Database,
    tmp_path: Path,
    change: str,
) -> None:
    manifest, backup = await setup_resources(cleanup_database, tmp_path)
    approved = await add_retained_account_application(cleanup_database, manifest)
    manifest.retainedAccountApplications.append(approved)
    async with cleanup_database.session() as session:
        plan = await build_plan(session, manifest, backup, TARGET)
    if change == "wrong_account":
        approved.accountId = uuid4()
        async with cleanup_database.session() as session:
            with pytest.raises(
                CleanupError, match="approved_application_missing_or_changed"
            ):
                await build_plan(session, manifest, backup, TARGET)
        return
    async with cleanup_database.session() as session:
        application = await session.get(Application, approved.id)
        assert application is not None
        if change == "status":
            application.status = "reviewing"
            application.version = 2
        elif change == "membership":
            session.add(
                TeamMembership(
                    team_id=approved.teamId,
                    contest_id=application.contest_id,
                    account_id=approved.accountId,
                    source_application_id=approved.id,
                    joined_at=NOW,
                )
            )
        elif change == "ai_reference":
            auth_session = AuthSession(
                account_id=manifest.resources[0].id,
                token_hash=b"t" * 32,
                created_at=NOW,
                last_seen_at=NOW,
                expires_at=NOW + timedelta(days=1),
            )
            session.add(auth_session)
            await session.flush()
            session.add(
                AiRun(
                    account_id=manifest.resources[0].id,
                    auth_session_id=auth_session.auth_session_id,
                    purpose="applicant_review",
                    scope_key="test-review",
                    team_id=approved.teamId,
                    application_id=approved.id,
                    request_fingerprint="a" * 64,
                    attempt=1,
                    status="failed",
                    failure_code="model_error",
                    references=[],
                    selected_keys=[],
                    created_at=NOW,
                    updated_at=NOW,
                    deadline_at=NOW + timedelta(minutes=1),
                    expires_at=NOW + timedelta(minutes=2),
                )
            )
        else:
            outsider = await seed_account(session)
            team = await session.get(Team, approved.teamId)
            assert team is not None
            await seed_application(session, team, outsider)
        await session.commit()
    before = await snapshot(cleanup_database)
    expected = {
        "status": "approved_application_missing_or_changed",
        "membership": "membership_crosses_cleanup_boundary",
        "ai_reference": "ai_run_active_or_crosses_cleanup_boundary",
        "unapproved_application": "application_crosses_cleanup_boundary",
    }[change]
    async with cleanup_database.session() as session:
        with pytest.raises(CleanupError, match=expected):
            await apply_plan(session, plan, TARGET)
        await session.rollback()
    assert await snapshot(cleanup_database) == before
