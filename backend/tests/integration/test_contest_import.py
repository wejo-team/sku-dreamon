"""공고 입력 CLI의 무쓰기 검증과 DB 저장·분류 실패 롤백을 확인한다."""

import json
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.schema import CreateSchema

from app.cli.contests import run
from app.core.db.base import Base
from app.core.db.session import create_database
from app.models.contests import Contest, ContestAudience, ContestField
from app.repositories import contest_import as repository
from app.schemas.contest_import import ContestImport
from app.services import contest_import as service
from tests.unit.test_contest_import import payload

pytestmark = pytest.mark.integration


async def test_validation_does_not_open_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "contest.json"
    source.write_text(json.dumps(payload()))
    monkeypatch.setenv("DATABASE_URL", "deliberately-invalid")
    assert await run(source, apply=False) == {"status": "validated"}


@pytest_asyncio.fixture
async def session(database_url: str) -> AsyncIterator[AsyncSession]:
    database = create_database(database_url)
    try:
        async with database.engine.connect() as connection:
            transaction = await connection.begin()
            try:
                schema = f"contest_import_{uuid4().hex}"
                await connection.execute(CreateSchema(schema))
                await connection.execution_options(schema_translate_map={None: schema})
                await connection.run_sync(
                    lambda sync: Base.metadata.create_all(
                        sync,
                        tables=[
                            Base.metadata.tables[name]
                            for name in (
                                "contests",
                                "contest_audiences",
                                "contest_fields",
                            )
                        ],
                    )
                )
                async with AsyncSession(
                    connection,
                    expire_on_commit=False,
                    join_transaction_mode="create_savepoint",
                ) as value:
                    yield value
            finally:
                await transaction.rollback()
    finally:
        await database.engine.dispose()


@pytest.mark.database
async def test_import_persists_source_and_categories(session: AsyncSession) -> None:
    contest_id = await service.import_contest(
        session, ContestImport.model_validate(payload())
    )
    session.expire_all()
    contest = await session.get(Contest, contest_id)
    assert contest is not None
    assert contest.title == "공식 공고" and contest.version == 1
    assert contest.registration_closes_at.isoformat() == "2026-10-31T15:00:00+00:00"
    assert contest.close_source_time is None and contest.close_time_assumed
    assert list(await session.scalars(select(ContestAudience.audience_code))) == [
        "student"
    ]
    assert list(await session.scalars(select(ContestField.field_code))) == ["design"]


@pytest.mark.database
async def test_partial_insert_and_commit_failure_roll_back(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = repository.insert_contest

    async def fail_after_insert(
        session: AsyncSession,
        contest: Contest,
        *,
        audiences: Sequence[str],
        fields: Sequence[str],
    ) -> None:
        await original(session, contest, audiences=audiences, fields=fields)
        raise RuntimeError("storage failure")

    monkeypatch.setattr(repository, "insert_contest", fail_after_insert)
    with pytest.raises(RuntimeError, match="storage failure"):
        await service.import_contest(session, ContestImport.model_validate(payload()))
    for model in (Contest, ContestAudience, ContestField):
        assert await session.scalar(select(func.count()).select_from(model)) == 0
