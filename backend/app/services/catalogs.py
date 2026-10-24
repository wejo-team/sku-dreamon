"""학사 조회와 같은 트랜잭션 안의 소속 검증·기준 데이터 쓰기를 처리한다."""

from pydantic import HttpUrl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.academic_units import AcademicUnit
from app.repositories import catalogs as catalogs_repository
from app.rules.catalogs import (
    AcademicStatusCode,
    CatalogCode,
    FieldCode,
    GradeCode,
    ProfileImageCode,
    RoleCode,
    SkillCode,
    WeeklyAvailabilityCode,
)
from app.schemas.catalogs import (
    AcademicUnitResponse,
    AvatarPreset,
    CatalogItem,
    Catalogs,
)


def _invalid_path() -> AppError:
    return AppError(409, "INVALID_ACADEMIC_PATH", "학사 소속을 다시 확인해 주세요.")


async def _locked_path(session: AsyncSession, unit_id: int) -> list[AcademicUnit]:
    seen: set[int] = set()
    current_id: int | None = unit_id
    while current_id is not None:
        if current_id in seen or len(seen) >= 3:
            raise _invalid_path()
        seen.add(current_id)
        row = await catalogs_repository.get_academic_parent(session, current_id)
        if row is None:
            raise _invalid_path()
        current_id = row[0]

    # 부모는 변경하지 않는 계약이다. 공유 잠금은 ID 순서로 얻어 같은
    # 조상의 동시 선택 및 여러 항목의 비활성화와 잠금 순서를 맞춘다.
    units = await catalogs_repository.lock_academic_path(session, seen)
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
    units = await catalogs_repository.list_academic_units(session)
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
    await catalogs_repository.add_academic_unit(session, unit)
    return unit


async def set_academic_selectable(
    session: AsyncSession, academic_unit_id: int, is_selectable: bool
) -> None:
    """신규 선택과 경합하는 변경을 행 잠금으로 직렬화하고 commit은 맡긴다."""
    unit = await catalogs_repository.lock_academic_unit(session, academic_unit_id)
    if unit is None:
        raise _invalid_path()
    unit.is_selectable = is_selectable
    await catalogs_repository.flush_academic_changes(session)


def _items(enum_type: type[CatalogCode]) -> list[CatalogItem]:
    return [
        CatalogItem(
            code=item.value,
            display_name=item.display_name,
            is_selectable=item.is_selectable,
            sort_order=item.sort_order,
        )
        for item in sorted(enum_type, key=lambda item: (item.sort_order, item.value))
    ]


def build_catalogs() -> Catalogs:
    return Catalogs(
        fields=_items(FieldCode),
        roles=_items(RoleCode),
        skills=_items(SkillCode),
        academic_statuses=_items(AcademicStatusCode),
        grades=_items(GradeCode),
        weekly_availability_ranges=_items(WeeklyAvailabilityCode),
        avatar_presets=[
            AvatarPreset(
                code=item.value,
                display_name=item.display_name,
                is_selectable=item.is_selectable,
                sort_order=item.sort_order,
                asset_url=HttpUrl(item.asset_url),
            )
            for item in sorted(
                ProfileImageCode, key=lambda item: (item.sort_order, item.value)
            )
        ],
    )
