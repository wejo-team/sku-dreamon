"""확인된 공고와 분류의 신규 저장을 하나의 트랜잭션으로 확정한다."""

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contests import Contest
from app.repositories import contest_import as repository
from app.schemas.contest_import import ContestImport


async def import_contest(session: AsyncSession, data: ContestImport) -> UUID:
    """등록 후 조건 변경 정책은 확정하지 않으며 신규 자료만 저장한다."""
    try:
        opening, closing = data.opening.resolve(), data.closing.resolve()
        contest = Contest(
            contest_id=uuid4(),
            title=data.title,
            organizer_name=data.organizer,
            official_url=data.source_url,
            eligibility_text=data.eligibility_text,
            description=data.description,
            submission_details=data.deliverables,
            awards=data.awards,
            contact_info=data.contact,
            poster_url=data.poster_url,
            member_limit_kind=data.capacity.kind,
            min_members=None
            if data.capacity.minimum_members is None
            else int(data.capacity.minimum_members),
            max_members=None
            if data.capacity.maximum_members is None
            else int(data.capacity.maximum_members),
            verified_at=data.verified_at,
            registration_opens_at=opening.ends_at,
            registration_closes_at=closing.ends_at,
            open_source_date=opening.source_date,
            open_source_time=opening.source_time,
            open_source_timezone=opening.source_timezone,
            open_effective_timezone=opening.effective_timezone,
            open_timezone_assumed=opening.timezone_assumed,
            close_source_date=closing.source_date,
            close_source_time=closing.source_time,
            close_source_timezone=closing.source_timezone,
            close_effective_timezone=closing.effective_timezone,
            close_time_assumed=closing.time_assumed,
            close_timezone_assumed=closing.timezone_assumed,
        )
        await repository.insert_contest(
            session, contest, audiences=data.audience_codes, fields=data.field_codes
        )
        await session.commit()
        return contest.contest_id
    except Exception:
        await session.rollback()
        raise
