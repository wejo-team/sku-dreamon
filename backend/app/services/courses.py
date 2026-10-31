"""과목 원장 조회·등록과 프로필 선택의 유효성을 처리한다."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db.session import begin_read_snapshot
from app.core.exceptions import AppError
from app.core.http.schemas import Page, PageMeta
from app.models.courses import Course
from app.repositories import courses as repository
from app.schemas.catalogs import CourseCatalogItem, CoursesQuery
from app.schemas.course_import import CourseImport


async def list_courses(
    session: AsyncSession, query: CoursesQuery
) -> Page[CourseCatalogItem]:
    await begin_read_snapshot(session, read_only=True)
    search = query.q or ""
    total = await repository.count_courses(session, search)
    total_pages = (total + query.page_size - 1) // query.page_size
    page = min(query.page, max(total_pages, 1))
    courses = await repository.list_courses(
        session, search, page=page, page_size=query.page_size
    )
    return Page(
        data=[
            CourseCatalogItem(
                code=course.code,
                name=course.name,
                aliases=course.aliases,
                departments=course.departments,
            )
            for course in courses
        ],
        pagination=PageMeta(
            page=page, page_size=query.page_size, total=total, total_pages=total_pages
        ),
    )


async def validate_course_selection(
    session: AsyncSession, codes: Sequence[str]
) -> Sequence[Course]:
    courses = await repository.get_courses(session, codes, lock=True)
    if {course.code for course in courses} != set(codes):
        raise AppError(
            409, "INVALID_COURSE_SELECTION", "선택한 과목을 다시 확인해주세요."
        )
    return courses


async def import_courses(session: AsyncSession, data: CourseImport) -> dict[str, int]:
    """같은 학수번호를 갱신하고 입력에 없는 기존 과목·선택 관계는 보존한다."""
    try:
        await repository.lock_import(session)
        existing = {
            course.code: course
            for course in await repository.get_courses(
                session, [course.code for course in data.courses]
            )
        }
        changed: list[Course] = []
        created = updated = unchanged = 0
        for item in data.courses:
            course = existing.get(item.code)
            if course is None:
                course = Course(
                    code=item.code,
                    name=item.name,
                    aliases=item.aliases,
                    departments=item.departments,
                )
                created += 1
            elif (course.name, course.aliases, course.departments) != (
                item.name,
                item.aliases,
                item.departments,
            ):
                course.name, course.aliases, course.departments = (
                    item.name,
                    item.aliases,
                    item.departments,
                )
                updated += 1
            else:
                unchanged += 1
                continue
            changed.append(course)
        await repository.store_courses(session, changed)
        await session.commit()
        return {"created": created, "updated": updated, "unchanged": unchanged}
    except Exception:
        await session.rollback()
        raise
