"""학사 기준 데이터의 조회·행 잠금·flush를 수행한다."""

from collections.abc import Collection

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.academic_units import AcademicUnit


async def get_academic_parent(
    session: AsyncSession, academic_unit_id: int
) -> tuple[int | None] | None:
    """없는 항목과 parent_id가 NULL인 최상위 항목을 구분한다."""
    row = (
        await session.execute(
            select(AcademicUnit.parent_id).where(
                AcademicUnit.academic_unit_id == academic_unit_id
            )
        )
    ).one_or_none()
    return (row[0],) if row is not None else None


async def lock_academic_path(
    session: AsyncSession, academic_unit_ids: Collection[int]
) -> list[AcademicUnit]:
    """공유 잠금을 ID 오름차순으로 얻고 기존 ORM 상태도 다시 읽는다."""
    return list(
        await session.scalars(
            select(AcademicUnit)
            .where(AcademicUnit.academic_unit_id.in_(academic_unit_ids))
            .order_by(AcademicUnit.academic_unit_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )


async def list_academic_units(session: AsyncSession) -> list[AcademicUnit]:
    return list(
        await session.scalars(
            select(AcademicUnit).order_by(AcademicUnit.academic_unit_id)
        )
    )


async def add_academic_unit(session: AsyncSession, unit: AcademicUnit) -> None:
    session.add(unit)
    await session.flush()


async def lock_academic_unit(
    session: AsyncSession, academic_unit_id: int
) -> AcademicUnit | None:
    unit = await session.scalar(
        select(AcademicUnit)
        .where(AcademicUnit.academic_unit_id == academic_unit_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return unit


async def flush_academic_changes(session: AsyncSession) -> None:
    await session.flush()
