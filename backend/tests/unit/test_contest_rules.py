"""공고의 접수 경계·원문 마감 해석과 공식 인원·대상 조합을 검증한다."""

from datetime import UTC, date, datetime, time, timedelta, timezone

import pytest

from app.core.exceptions import AppError
from app.rules.catalogs import FieldCode
from app.rules.contests import (
    CapacityKind,
    RegistrationStatus,
    get_registration_status,
    interpret_deadline,
    validate_audience_codes,
    validate_field_codes,
    validate_participation_capacity,
    validate_team_capacity,
)


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (datetime(2026, 10, 20, 23, 59, 59, tzinfo=UTC), "scheduled"),
        (datetime(2026, 10, 21, tzinfo=UTC), "open"),
        (datetime(2026, 10, 21, 23, 59, 59, tzinfo=UTC), "open"),
        (datetime(2026, 10, 22, tzinfo=UTC), "closed"),
    ],
)
def test_registration_includes_start_and_excludes_end(
    now: datetime, expected: str
) -> None:
    assert get_registration_status(
        starts_at=datetime(2026, 10, 21, tzinfo=UTC),
        ends_at=datetime(2026, 10, 22, tzinfo=UTC),
        now=now,
    ) == RegistrationStatus(expected)


def test_registration_compares_instants_across_timezones() -> None:
    assert (
        get_registration_status(
            starts_at=datetime(2026, 10, 21, tzinfo=UTC),
            ends_at=datetime(2026, 10, 22, tzinfo=UTC),
            now=datetime(2026, 10, 22, 9, tzinfo=timezone(timedelta(hours=9))),
        )
        == RegistrationStatus.CLOSED
    )


@pytest.mark.parametrize("invalid", ["naive", "equal", "reversed"])
def test_registration_rejects_unconfirmed_or_invalid_boundaries(invalid: str) -> None:
    start = datetime(2026, 10, 21, tzinfo=UTC)
    end = start + timedelta(days=1)
    if invalid == "naive":
        start = start.replace(tzinfo=None)
    elif invalid == "equal":
        end = start
    else:
        end = start - timedelta(days=1)
    with pytest.raises(ValueError):
        get_registration_status(starts_at=start, ends_at=end, now=end)


@pytest.mark.parametrize(
    ("source_time", "source_timezone", "expected", "time_assumed", "zone_assumed"),
    [
        (None, None, datetime(2026, 10, 21, 15, tzinfo=UTC), True, True),
        (time(17), None, datetime(2026, 10, 21, 8, tzinfo=UTC), False, True),
        (
            time(17),
            "America/New_York",
            datetime(2026, 10, 21, 21, tzinfo=UTC),
            False,
            False,
        ),
        (None, "America/New_York", datetime(2026, 10, 22, 4, tzinfo=UTC), True, False),
        (time(17), "+09:00", datetime(2026, 10, 21, 8, tzinfo=UTC), False, False),
        (time(17), "-04:30", datetime(2026, 10, 21, 21, 30, tzinfo=UTC), False, False),
    ],
)
def test_deadline_preserves_source_and_resolves_a_utc_exclusive_boundary(
    source_time: time | None,
    source_timezone: str | None,
    expected: datetime,
    time_assumed: bool,
    zone_assumed: bool,
) -> None:
    deadline = interpret_deadline(
        source_date=date(2026, 10, 21),
        source_time=source_time,
        source_timezone=source_timezone,
    )
    assert deadline.ends_at == expected
    assert deadline.ends_at.tzinfo is UTC
    assert deadline.source_date == date(2026, 10, 21)
    assert deadline.source_time == source_time
    assert deadline.source_timezone == source_timezone
    assert deadline.effective_timezone == (source_timezone or "Asia/Seoul")
    assert deadline.time_assumed is time_assumed
    assert deadline.timezone_assumed is zone_assumed


@pytest.mark.parametrize(
    ("source_date", "source_time", "source_timezone"),
    [
        (date(2026, 3, 8), time(2, 30), "America/New_York"),
        (date(2026, 11, 1), time(1, 30), "America/New_York"),
        (date(2026, 10, 21), time(17), "not/a/timezone"),
        (date(2026, 10, 21), time(17), "+24:00"),
        (date(2026, 10, 21), time(17, tzinfo=UTC), "Asia/Seoul"),
    ],
)
def test_deadline_does_not_guess_ambiguous_or_invalid_source_times(
    source_date: date, source_time: time, source_timezone: str
) -> None:
    with pytest.raises(ValueError):
        interpret_deadline(
            source_date=source_date,
            source_time=source_time,
            source_timezone=source_timezone,
        )


@pytest.mark.parametrize(
    ("kind", "minimum", "maximum"),
    [
        ("range", 1, 1),
        ("range", 3, 5),
        ("range", 9223372036854775807, 9223372036854775807),
        ("unlimited", None, None),
        ("unlimited", 2, None),
        ("unknown", None, None),
    ],
)
def test_capacity_keeps_numeric_unlimited_and_unknown_distinct(
    kind: str, minimum: int | None, maximum: int | None
) -> None:
    validate_participation_capacity(
        kind=CapacityKind(kind), minimum_members=minimum, maximum_members=maximum
    )


@pytest.mark.parametrize(
    ("kind", "minimum", "maximum"),
    [
        ("range", None, 3),
        ("range", 1, None),
        ("range", 4, 3),
        ("range", 0, 3),
        ("range", True, 3),
        ("range", 1, 9223372036854775808),
        ("unlimited", 0, None),
        ("unlimited", 1, 3),
        ("unknown", 1, None),
        ("unknown", None, 3),
        ("other", None, None),
    ],
)
def test_capacity_rejects_inconsistent_or_unrepresentable_conditions(
    kind: str, minimum: int | None, maximum: int | None
) -> None:
    with pytest.raises(ValueError):
        validate_participation_capacity(
            kind=kind, minimum_members=minimum, maximum_members=maximum
        )


@pytest.mark.parametrize(
    ("capacity", "kind", "minimum", "maximum", "valid"),
    [
        (1, "range", 1, 1, True),
        (2, "range", 1, 1, False),
        (3, "range", 3, 5, True),
        (2, "range", 3, 5, False),
        (6, "range", 3, 5, False),
        (2, "unlimited", 2, None, True),
        (1, "unlimited", 2, None, False),
        (1, "unlimited", None, None, True),
        (0, "unlimited", None, None, False),
        (True, "unlimited", None, None, False),
        (1, "unknown", None, None, False),
    ],
)
def test_team_capacity_obeys_official_bounds_without_inventing_a_default(
    capacity: int,
    kind: str,
    minimum: int | None,
    maximum: int | None,
    valid: bool,
) -> None:
    if valid:
        validate_team_capacity(
            capacity, kind=kind, minimum_members=minimum, maximum_members=maximum
        )
    else:
        with pytest.raises(ValueError):
            validate_team_capacity(
                capacity, kind=kind, minimum_members=minimum, maximum_members=maximum
            )


@pytest.mark.parametrize(
    "codes",
    [["student"], ["general"], ["student", "general"], ["unrestricted"], ["unknown"]],
)
def test_audience_combinations_are_preserved(codes: list[str]) -> None:
    assert [str(code) for code in validate_audience_codes(codes)] == codes


@pytest.mark.parametrize(
    "codes",
    [
        [],
        ["student", "student"],
        ["unknown", "student"],
        ["unrestricted", "general"],
        ["other"],
    ],
)
def test_audience_rejects_duplicates_and_exclusive_combinations(
    codes: list[str],
) -> None:
    with pytest.raises(ValueError):
        validate_audience_codes(codes)


def test_fields_use_the_shared_catalog_without_a_representative_field() -> None:
    assert validate_field_codes([]) == ()
    assert validate_field_codes(["design", "it_technology", "public"]) == (
        FieldCode.DESIGN,
        FieldCode.IT_TECHNOLOGY,
        FieldCode.PUBLIC,
    )
    with pytest.raises(ValueError):
        validate_field_codes(["design", "design"])
    with pytest.raises(ValueError):
        validate_field_codes(["design", "it_technology", "public", "education"])
    with pytest.raises(AppError, match="선택지"):
        validate_field_codes(["not_a_field"])


def test_fields_keep_existing_inactive_values_but_reject_new_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(FieldCode.DESIGN, "is_selectable", False)
    assert validate_field_codes(["design"], previous_codes=["design"]) == (
        FieldCode.DESIGN,
    )
    with pytest.raises(AppError):
        validate_field_codes(["design"])


@pytest.mark.parametrize(
    ("day", "clock_time"), [(date.max, None), (date.min, time.min)]
)
def test_deadline_rejects_dates_outside_the_resolvable_utc_range(
    day: date, clock_time: time | None
) -> None:
    with pytest.raises(ValueError):
        interpret_deadline(
            source_date=day, source_time=clock_time, source_timezone="Asia/Seoul"
        )
