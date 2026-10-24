"""공고 목록과 총원에 동일 검색·상태 조건을 적용한다."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import NamedTuple

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contests import Contest, ContestField
from app.models.teams import Team


@dataclass(frozen=True)
class ContestFilter:
    needle: str
    matching_fields: Sequence[str]
    field_code: str | None
    registration_status: str | None
    now: datetime


class ContestListRow(NamedTuple):
    contest: Contest
    field_codes: Sequence[str]
    team_count: int


def _conditions(query: ContestFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if query.field_code is not None:
        conditions.append(
            select(ContestField.contest_id)
            .where(
                ContestField.contest_id == Contest.contest_id,
                ContestField.field_code == query.field_code,
            )
            .exists()
        )
    if query.needle:
        conditions.append(
            or_(
                Contest.title.icontains(query.needle, autoescape=True),
                Contest.organizer_name.icontains(query.needle, autoescape=True),
                select(ContestField.contest_id)
                .where(
                    ContestField.contest_id == Contest.contest_id,
                    ContestField.field_code.in_(query.matching_fields),
                )
                .exists(),
            )
        )
    if query.registration_status == "scheduled":
        conditions.append(Contest.registration_opens_at > query.now)
    elif query.registration_status == "open":
        conditions.extend(
            [
                Contest.registration_opens_at <= query.now,
                Contest.registration_closes_at > query.now,
            ]
        )
    elif query.registration_status == "closed":
        conditions.append(Contest.registration_closes_at <= query.now)
    return conditions


async def count_contests(session: AsyncSession, filters: ContestFilter) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Contest).where(*_conditions(filters))
    )
    assert count is not None
    return count


async def list_contests(
    session: AsyncSession,
    filters: ContestFilter,
    *,
    sort: str,
    page: int,
    page_size: int,
) -> list[ContestListRow]:
    fields = (
        select(func.array_agg(ContestField.field_code))
        .where(ContestField.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    teams = (
        select(func.count())
        .select_from(Team)
        .where(Team.contest_id == Contest.contest_id)
        .correlate(Contest)
        .scalar_subquery()
    )
    order = (
        (Contest.registration_closes_at.asc(), Contest.contest_id.asc())
        if sort == "deadline_asc"
        else (Contest.created_at.desc(), Contest.contest_id.desc())
    )
    rows = await session.execute(
        select(Contest, fields, teams)
        .where(*_conditions(filters))
        .order_by(*order)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .execution_options(populate_existing=True)
    )
    return [
        ContestListRow(contest, codes or [], count) for contest, codes, count in rows
    ]
