"""접수 시작과 마감의 날짜 보완 경계를 구분한다."""

from datetime import UTC, date, datetime, time

from app.rules.contests import interpret_deadline, interpret_opening


def test_date_only_opening_starts_on_same_local_day() -> None:
    opening = interpret_opening(
        source_date=date(2026, 10, 26), source_time=None, source_timezone=None
    )
    closing = interpret_deadline(
        source_date=date(2026, 10, 26), source_time=None, source_timezone=None
    )
    assert opening.ends_at == datetime(2026, 10, 25, 15, tzinfo=UTC)
    assert closing.ends_at == datetime(2026, 10, 26, 15, tzinfo=UTC)
    assert opening.source_time is None
    assert opening.time_assumed and opening.timezone_assumed


def test_explicit_midnight_is_preserved_as_source_information() -> None:
    opening = interpret_opening(
        source_date=date(2026, 10, 26),
        source_time=time(0),
        source_timezone="Asia/Seoul",
    )
    assert opening.source_time == time(0)
    assert not opening.time_assumed and not opening.timezone_assumed


def test_observed_opening_time_is_not_shifted_to_day_end() -> None:
    opening = interpret_opening(
        source_date=date(2026, 10, 1),
        source_time=time(10),
        source_timezone="Asia/Seoul",
    )
    assert opening.ends_at == datetime(2026, 10, 1, 1, tzinfo=UTC)


def test_date_only_opening_keeps_an_explicit_source_timezone() -> None:
    opening = interpret_opening(
        source_date=date(2026, 10, 26), source_time=None, source_timezone="-05:00"
    )
    assert opening.ends_at == datetime(2026, 10, 26, 5, tzinfo=UTC)
    assert opening.source_timezone == opening.effective_timezone == "-05:00"
    assert opening.time_assumed and not opening.timezone_assumed


def test_opening_on_the_last_supported_date_does_not_add_an_extra_day() -> None:
    opening = interpret_opening(
        source_date=date.max, source_time=None, source_timezone="UTC"
    )
    assert opening.ends_at == datetime(9999, 12, 31, tzinfo=UTC)
