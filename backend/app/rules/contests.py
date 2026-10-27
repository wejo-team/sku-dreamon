"""공고의 확정된 접수 경계·인원·분류 규칙을 HTTP와 DB 없이 계산한다."""

import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.rules.catalogs import FieldCode, validate_catalog_selection

_MAX_BIGINT = 9223372036854775807


class RegistrationStatus(StrEnum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"


class CapacityKind(StrEnum):
    RANGE = "range"
    UNLIMITED = "unlimited"
    UNKNOWN = "unknown"


class AudienceCode(StrEnum):
    STUDENT = "student"
    GENERAL = "general"
    UNRESTRICTED = "unrestricted"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ResolvedDeadline:
    """원문 정보와 계산된 배타적 종료 경계를 함께 전달한다."""

    ends_at: datetime
    source_date: date
    source_time: time | None
    source_timezone: str | None
    effective_timezone: str
    time_assumed: bool
    timezone_assumed: bool


def _aware_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("Timezone-aware datetime is required")
    return value.astimezone(UTC)


def get_registration_status(
    *, starts_at: datetime, ends_at: datetime, now: datetime
) -> RegistrationStatus:
    """확인된 시작·종료 경계와 호출자가 고정한 현재 시각으로 상태를 계산한다."""
    start, end, current = map(_aware_utc, (starts_at, ends_at, now))
    if start >= end:
        raise ValueError("Registration must start before it ends")
    if current < start:
        return RegistrationStatus.SCHEDULED
    if current >= end:
        return RegistrationStatus.CLOSED
    return RegistrationStatus.OPEN


def _source_timezone(name: str) -> tzinfo:
    # 원문 정규화 식별자는 IANA 이름 또는 ±HH:MM 고정 오프셋을 사용한다.
    offset = re.fullmatch(r"([+-])([0-9]{2}):([0-9]{2})", name)
    if offset is not None:
        hours, minutes = int(offset[2]), int(offset[3])
        if hours >= 24 or minutes >= 60:
            raise ValueError("Invalid UTC offset")
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(delta if offset[1] == "+" else -delta)
    try:
        return ZoneInfo(name)
    except (ValueError, ZoneInfoNotFoundError) as exception:
        raise ValueError("Invalid source timezone") from exception


def interpret_deadline(
    *, source_date: date, source_time: time | None, source_timezone: str | None
) -> ResolvedDeadline:
    """마감만 보완한다. 시각 누락은 다음 날 00:00, 시간대 누락은 한국시간이다.

    서로 다른 UTC 시점이 가능한 중복 시각이나 존재하지 않는 현지 시각은
    임의로 고르지 않고 ValueError로 거부한다. 시작 시각 보완에는 쓰지 않는다.
    """
    if source_time is not None and source_time.tzinfo is not None:
        raise ValueError("Source time and timezone must be supplied separately")
    zone_name = "Asia/Seoul" if source_timezone is None else source_timezone
    zone = _source_timezone(zone_name)
    candidates: set[datetime] = set()
    try:
        day = (
            source_date if source_time is not None else source_date + timedelta(days=1)
        )
        local = datetime.combine(day, source_time or time.min)
        for fold in (0, 1):
            candidate = local.replace(tzinfo=zone, fold=fold).astimezone(UTC)
            if candidate.astimezone(zone).replace(tzinfo=None) == local:
                candidates.add(candidate)
    except OverflowError as exception:
        raise ValueError(
            "Deadline is outside the supported datetime range"
        ) from exception
    if len(candidates) != 1:
        raise ValueError("Source time does not identify one valid instant")
    return ResolvedDeadline(
        ends_at=candidates.pop(),
        source_date=source_date,
        source_time=source_time,
        source_timezone=source_timezone,
        effective_timezone=zone_name,
        time_assumed=source_time is None,
        timezone_assumed=source_timezone is None,
    )


def _positive_bigint(value: int) -> None:
    if type(value) is not int or not 1 <= value <= _MAX_BIGINT:
        raise ValueError("A positive signed 64-bit integer is required")


def interpret_opening(
    *, source_date: date, source_time: time | None, source_timezone: str | None
) -> ResolvedDeadline:
    """시작 시각 누락은 해당 날짜 00:00으로 보완하고 누락 사실을 보존한다."""
    resolved = interpret_deadline(
        source_date=source_date,
        source_time=source_time if source_time is not None else time.min,
        source_timezone=source_timezone,
    )
    return replace(resolved, source_time=source_time, time_assumed=source_time is None)


def validate_participation_capacity(
    *, kind: str, minimum_members: int | None, maximum_members: int | None
) -> None:
    """원문 인원의 숫자 범위·상한 없음·미확인을 혼동하지 않도록 검증한다."""
    capacity_kind = CapacityKind(kind)
    for value in (minimum_members, maximum_members):
        if value is not None:
            _positive_bigint(value)
    if capacity_kind == CapacityKind.RANGE:
        if (
            minimum_members is None
            or maximum_members is None
            or minimum_members > maximum_members
        ):
            raise ValueError("Numeric capacity requires ordered minimum and maximum")
    elif capacity_kind == CapacityKind.UNLIMITED:
        if maximum_members is not None:
            raise ValueError("Unlimited capacity has no maximum")
    elif minimum_members is not None or maximum_members is not None:
        raise ValueError("Unknown capacity has no confirmed bounds")


def validate_team_capacity(
    capacity: int,
    *,
    kind: str,
    minimum_members: int | None,
    maximum_members: int | None,
) -> None:
    """팀장이 명시한 목표 정원을 검사하며, 기본 정원이나 자격 판정을 만들지 않는다."""
    _positive_bigint(capacity)
    validate_participation_capacity(
        kind=kind, minimum_members=minimum_members, maximum_members=maximum_members
    )
    if kind == CapacityKind.UNKNOWN:
        raise ValueError("Official capacity must be confirmed before team creation")
    if minimum_members is not None and capacity < minimum_members:
        raise ValueError("Team capacity is below the official minimum")
    if maximum_members is not None and capacity > maximum_members:
        raise ValueError("Team capacity exceeds the official maximum")


def validate_audience_codes(codes: Sequence[str]) -> tuple[AudienceCode, ...]:
    audiences = tuple(AudienceCode(code) for code in codes)
    if not 1 <= len(audiences) <= 2 or len(set(audiences)) != len(audiences):
        raise ValueError("Audience must contain one or two distinct codes")
    if len(audiences) > 1 and any(
        code in (AudienceCode.UNRESTRICTED, AudienceCode.UNKNOWN) for code in audiences
    ):
        raise ValueError("Unrestricted and unknown audiences must stand alone")
    return audiences


def validate_field_codes(
    codes: Sequence[str], *, previous_codes: Collection[str] = ()
) -> tuple[FieldCode, ...]:
    """분야는 중복 없이 최대 세 개이며 기존 선택값의 활성 정책을 함께 적용한다."""
    if len(codes) > 3 or len(set(codes)) != len(codes):
        raise ValueError("Contest fields must be distinct and contain at most three")
    fields = []
    for code in codes:
        selected = validate_catalog_selection(
            FieldCode, code, previous_code=code if code in previous_codes else None
        )
        assert selected is not None
        fields.append(selected)
    return tuple(fields)
