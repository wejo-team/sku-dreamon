"""격리 PostgreSQL에서 학사 계층·기존 소속 보존·동시 비활성화를 검증한다."""

import asyncio
from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.exceptions import AppError
from app.core.http.dependencies import get_session
from app.core.http.handlers import register_error_handlers
from app.domains.catalogs.models import AcademicUnit
from app.domains.catalogs.router import router
from app.domains.catalogs.service import (
    create_academic_unit,
    set_academic_selectable,
    validate_academic_selection,
)

pytestmark = [pytest.mark.integration, pytest.mark.database]


@pytest_asyncio.fixture
async def academic_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    schema = f"catalogs_test_{uuid4().hex}"
    engine = create_async_engine(database_url)
    try:
        async with engine.begin() as connection:
            await connection.execute(CreateSchema(schema))
            await connection.execution_options(schema_translate_map={None: schema})
            await connection.run_sync(
                AcademicUnit.metadata.tables["academic_units"].create
            )
        yield engine.execution_options(schema_translate_map={None: schema})
    finally:
        async with engine.begin() as connection:
            await connection.execute(DropSchema(schema, cascade=True))
        await engine.dispose()


async def test_academic_http_handles_empty_and_inactive_paths(
    academic_engine: AsyncEngine,
) -> None:
    async def session_dependency() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(academic_engine) as session:
            yield session

    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[get_session] = session_dependency
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/v1/catalogs/academic-units")
        assert response.status_code == 200
        assert response.json() == {"data": []}
        async with AsyncSession(academic_engine) as session:
            college = await create_academic_unit(session, name="검증용 대학")
            department = await create_academic_unit(
                session, name="검증용 학과", parent_id=college.academic_unit_id
            )
            department.is_selectable = False
            ids = [college.academic_unit_id, department.academic_unit_id]
            await session.commit()
        response = await client.get("/api/v1/catalogs/academic-units")
        assert response.json() == {
            "data": [
                {
                    "id": str(ids[0]),
                    "name": "검증용 대학",
                    "parentId": None,
                    "isSelectable": True,
                },
                {
                    "id": str(ids[1]),
                    "name": "검증용 학과",
                    "parentId": str(ids[0]),
                    "isSelectable": False,
                },
            ]
        }


async def test_new_selection_checks_all_ancestors_but_keeps_old_selection(
    academic_engine: AsyncEngine,
) -> None:
    async with AsyncSession(academic_engine) as session:
        college = await create_academic_unit(session, name="검증용 대학")
        department = await create_academic_unit(
            session, name="검증용 학부", parent_id=college.academic_unit_id
        )
        major = await create_academic_unit(
            session, name="검증용 전공", parent_id=department.academic_unit_id
        )
        await validate_academic_selection(session, major.academic_unit_id)
        await validate_academic_selection(session, None)
        await set_academic_selectable(session, college.academic_unit_id, False)
        with pytest.raises(AppError) as error:
            await validate_academic_selection(session, major.academic_unit_id)
        assert error.value.code == "INVALID_ACADEMIC_PATH"
        await validate_academic_selection(
            session,
            major.academic_unit_id,
            previous_academic_unit_id=major.academic_unit_id,
        )
        with pytest.raises(AppError):
            await validate_academic_selection(session, 99999)
        with pytest.raises(AppError):
            await create_academic_unit(
                session, name="깊이 초과", parent_id=major.academic_unit_id
            )
        # 같은 표시명은 다른 항목일 수 있으므로 이름으로 합치지 않는다.
        duplicate_name = await create_academic_unit(session, name="검증용 대학")
        assert duplicate_name.academic_unit_id != college.academic_unit_id


async def test_uncommitted_academic_changes_do_not_persist(
    academic_engine: AsyncEngine,
) -> None:
    async with AsyncSession(academic_engine) as session:
        await create_academic_unit(session, name="롤백 대학")
    async with AsyncSession(academic_engine) as session:
        assert await session.scalar(select(AcademicUnit)) is None


async def test_academic_invalid_writes_and_foreign_key_are_rejected(
    academic_engine: AsyncEngine,
) -> None:
    async with AsyncSession(academic_engine) as session:
        for name in ("   ", "가" * 101):
            with pytest.raises(ValueError):
                await create_academic_unit(session, name=name)
        with pytest.raises(AppError):
            await create_academic_unit(session, name="없는 부모", parent_id=99999)
        college = await create_academic_unit(session, name="검증용 대학")
        college.parent_id = college.academic_unit_id
        with pytest.raises(IntegrityError):
            await session.flush()
        await session.rollback()
        session.add(AcademicUnit(name="없는 부모", parent_id=99999))
        with pytest.raises(IntegrityError):
            await session.flush()


async def test_deactivation_waits_for_new_selection_transaction(
    academic_engine: AsyncEngine,
) -> None:
    async with AsyncSession(academic_engine) as session:
        college = await create_academic_unit(session, name="검증용 대학")
        department = await create_academic_unit(
            session, name="검증용 학과", parent_id=college.academic_unit_id
        )
        college_id, department_id = (
            college.academic_unit_id,
            department.academic_unit_id,
        )
        await session.commit()
    async with (
        AsyncSession(academic_engine) as selecting,
        AsyncSession(academic_engine) as editing,
    ):
        await validate_academic_selection(selecting, department_id)
        waiting = asyncio.create_task(
            set_academic_selectable(editing, college_id, False)
        )
        try:
            with pytest.raises(TimeoutError):
                await asyncio.wait_for(asyncio.shield(waiting), timeout=0.1)
            await selecting.commit()
            await asyncio.wait_for(waiting, timeout=2)
            await editing.commit()
            with pytest.raises(AppError):
                await validate_academic_selection(selecting, department_id)
        finally:
            if not waiting.done():
                waiting.cancel()
                await asyncio.gather(waiting, return_exceptions=True)
