"""학사 조회와 같은 트랜잭션 안의 소속 검증·기준 데이터 쓰기를 처리한다."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.domains.catalogs.models import AcademicUnit
from app.domains.catalogs.schemas import AcademicUnitResponse


def _invalid_path() -> AppError:
    return AppError(409, "INVALID_ACADEMIC_PATH", "학사 소속을 다시 확인해 주세요.")


async def _locked_path(session: AsyncSession, unit_id: int) -> list[AcademicUnit]:
    seen: set[int] = set()
    current_id: int | None = unit_id
    while current_id is not None:
        if current_id in seen or len(seen) >= 3:
            raise _invalid_path()
        seen.add(current_id)
        row = (
            await session.execute(
                select(AcademicUnit.parent_id).where(
                    AcademicUnit.academic_unit_id == current_id
                )
            )
        ).one_or_none()
        if row is None:
            raise _invalid_path()
        current_id = row.parent_id

    # 부모는 변경하지 않는 계약이다. 공유 잠금은 ID 순서로 얻어 같은
    # 조상의 동시 선택 및 여러 항목의 비활성화와 잠금 순서를 맞춘다.
    units = list(
        await session.scalars(
            select(AcademicUnit)
            .where(AcademicUnit.academic_unit_id.in_(seen))
            .order_by(AcademicUnit.academic_unit_id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
    )
    by_id = {unit.academic_unit_id: unit for unit in units}
    path: list[AcademicUnit] = []
    current_id = unit_id
    while current_id is not None:
        if current_id not in by_id or len(path) >= 3:
            raise _invalid_path()
        unit = by_id[current_id]
        path.append(unit)
        current_id = unit.parent_id
    return path


async def validate_academic_selection(
    session: AsyncSession,
    academic_unit_id: int | None,
    previous_academic_unit_id: int | None = None,
) -> None:
    """새 선택과 모든 조상을 잠그고 확인한다. commit은 프로필 서비스 소유다.

    같은 과거 소속의 유지는 허용한다. 공유 행 잠금은 다른 신규 선택을
    막지 않으며 비활성화 UPDATE와는 충돌하여 저장 중 유효성을 보장한다.
    """
    if academic_unit_id is None:
        return
    path = await _locked_path(session, academic_unit_id)
    if academic_unit_id != previous_academic_unit_id and any(
        not unit.is_selectable for unit in path
    ):
        raise _invalid_path()


async def list_academic_units(session: AsyncSession) -> list[AcademicUnitResponse]:
    units = await session.scalars(
        select(AcademicUnit).order_by(AcademicUnit.academic_unit_id)
    )
    return [
        AcademicUnitResponse(
            id=str(unit.academic_unit_id),
            name=unit.name,
            parent_id=str(unit.parent_id) if unit.parent_id is not None else None,
            is_selectable=unit.is_selectable,
        )
        for unit in units
    ]


async def create_academic_unit(
    session: AsyncSession,
    *,
    name: str,
    parent_id: int | None = None,
    is_selectable: bool = True,
) -> AcademicUnit:
    """검토한 원장만 등록하는 내부 함수이며 기존 부모를 수정하지 않는다.

    같은 이름도 서로 다른 항목일 수 있어 이름으로 병합하거나 재적재를
    판단하지 않는다. 실제 시드는 검토한 기존 ID 대응을 별도로 사용한다.
    """
    normalized_name = name.strip()
    if not normalized_name or len(normalized_name) > 100:
        raise ValueError("Academic names must contain between 1 and 100 characters")
    if parent_id is not None and len(await _locked_path(session, parent_id)) >= 3:
        raise _invalid_path()
    unit = AcademicUnit(
        name=normalized_name, parent_id=parent_id, is_selectable=is_selectable
    )
    session.add(unit)
    await session.flush()
    return unit


async def set_academic_selectable(
    session: AsyncSession, academic_unit_id: int, is_selectable: bool
) -> None:
    """신규 선택과 경합하는 변경을 행 잠금으로 직렬화하고 commit은 맡긴다."""
    unit = await session.scalar(
        select(AcademicUnit)
        .where(AcademicUnit.academic_unit_id == academic_unit_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if unit is None:
        raise _invalid_path()
    unit.is_selectable = is_selectable
    await session.flush()
