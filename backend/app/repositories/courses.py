"""과목 검색·원장 적재와 프로필 선택 과목의 저장 조회를 담당한다."""

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.courses import Course, ProfileCourse


def _filters(query: str) -> list[ColumnElement[bool]]:
    if not query:
        return []
    return [
        or_(
            Course.code.icontains(query, autoescape=True),
            Course.name.icontains(query, autoescape=True),
            func.array_to_string(Course.aliases, "\n").icontains(
                query, autoescape=True
            ),
        )
    ]


async def count_courses(session: AsyncSession, query: str) -> int:
    total = await session.scalar(
        select(func.count()).select_from(Course).where(*_filters(query))
    )
    assert total is not None
    return total


async def list_courses(
    session: AsyncSession, query: str, *, page: int, page_size: int
) -> Sequence[Course]:
    return (
        await session.scalars(
            select(Course)
            .where(*_filters(query))
            .order_by(Course.code)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).all()


async def get_courses(
    session: AsyncSession, codes: Sequence[str], *, lock: bool = False
) -> Sequence[Course]:
    if not codes:
        return []
    query = select(Course).where(Course.code.in_(codes)).order_by(Course.course_id)
    if lock:
        query = query.with_for_update(read=True)
    return (await session.scalars(query)).all()


async def profile_courses(
    session: AsyncSession, account_ids: Sequence[UUID]
) -> dict[UUID, list[Course]]:
    result: dict[UUID, list[Course]] = {}
    if not account_ids:
        return result
    rows = await session.execute(
        select(ProfileCourse.account_id, Course)
        .join(Course, Course.course_id == ProfileCourse.course_id)
        .where(ProfileCourse.account_id.in_(account_ids))
        .order_by(Course.code)
    )
    for account_id, course in rows:
        result.setdefault(account_id, []).append(course)
    return result


async def replace_profile_courses(
    session: AsyncSession, account_id: UUID, courses: Sequence[Course]
) -> None:
    await session.execute(
        delete(ProfileCourse).where(ProfileCourse.account_id == account_id)
    )
    session.add_all(
        [
            ProfileCourse(account_id=account_id, course_id=course.course_id)
            for course in courses
        ]
    )
    await session.flush()


async def lock_import(session: AsyncSession) -> None:
    # 동시 적재에서도 학수번호별 신규·갱신 판정을 직렬화한다.
    await session.execute(text("SELECT pg_advisory_xact_lock(70431020261031)"))


async def store_courses(session: AsyncSession, courses: Sequence[Course]) -> None:
    session.add_all(courses)
    await session.flush()
