"""E2E 도구가 원본 DB를 거부하고 반복 가능한 격리 자료를 준비하는지 검사한다."""

from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy.engine import URL

from app.rules.catalogs import FieldCode
from app.rules.contests import get_registration_status
from scripts import prepare_mixed_e2e, seed_e2e_data

UNSAFE_TARGETS = (
    "postgresql+asyncpg://wejo:wejo@127.0.0.1:55432/wejo_dev",
    "postgresql+asyncpg://wejo:wejo@remote.example.test/quality_e2e",
    "postgresql+asyncpg://wejo:wejo@localhost/quality_e2e?host=remote.example.test",
    "postgresql+asyncpg://wejo:wejo@localhost/",
)


@pytest.mark.parametrize(
    ("validate", "error"),
    [
        (prepare_mixed_e2e.validate_target, prepare_mixed_e2e.CandidateError),
        (seed_e2e_data.validate_target, seed_e2e_data.FixtureError),
    ],
)
@pytest.mark.parametrize("value", UNSAFE_TARGETS)
def test_both_tools_reject_nonisolated_targets(
    validate: Callable[[str], URL], error: type[Exception], value: str
) -> None:
    with pytest.raises(error):
        validate(value)


@pytest.mark.parametrize(
    "validate", [prepare_mixed_e2e.validate_target, seed_e2e_data.validate_target]
)
@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "[::1]"])
def test_local_e2e_databases_can_use_another_development_port(
    validate: Callable[[str], URL], host: str
) -> None:
    target = validate(f"postgresql+asyncpg://wejo:wejo@{host}:6000/quality_e2e")
    assert target.database == "quality_e2e"
    assert target.port == 6000


async def test_seed_requires_apply_before_creating_a_database_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connect = Mock(side_effect=AssertionError("Database must not be accessed"))
    monkeypatch.setattr(seed_e2e_data, "create_database", connect)
    with pytest.raises(seed_e2e_data.FixtureError, match="Explicit --apply"):
        await seed_e2e_data.run(
            "postgresql+asyncpg://wejo:wejo@localhost/quality_e2e", apply=False
        )
    connect.assert_not_called()


@pytest.mark.parametrize("value", UNSAFE_TARGETS)
async def test_apply_cannot_bypass_database_target_guard(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    connect = Mock(side_effect=AssertionError("Database must not be accessed"))
    monkeypatch.setattr(seed_e2e_data, "create_database", connect)
    with pytest.raises(seed_e2e_data.FixtureError):
        await seed_e2e_data.run(value, apply=True)
    connect.assert_not_called()


def test_fixture_ids_are_stable_while_dates_follow_the_run_reference() -> None:
    first_run = datetime(2026, 12, 31, 23, 30, tzinfo=UTC)
    later_run = first_run + timedelta(days=367)
    first = seed_e2e_data.build_contests(first_run)
    later = seed_e2e_data.build_contests(later_run)
    first_ids = {contest.contest_id for contest, _ in first}
    assert len(first) == len(first_ids) == 8
    assert first_ids == {contest.contest_id for contest, _ in later}
    for reference, fixtures in [(first_run, first), (later_run, later)]:
        statuses = Counter(
            get_registration_status(
                starts_at=contest.registration_opens_at,
                ends_at=contest.registration_closes_at,
                now=reference,
            )
            for contest, _ in fixtures
        )
        assert statuses == {"open": 6, "closed": 1, "scheduled": 1}
        for contest, field in fixtures:
            assert field in FieldCode
            assert contest.member_limit_kind == "range"
            assert contest.min_members == 1 and contest.max_members == 4
            if contest.registration_closes_at > reference:
                assert contest.registration_closes_at > reference + timedelta(days=20)


def test_fixture_preserves_null_sources_and_time_default_cases() -> None:
    fixtures = seed_e2e_data.build_contests(datetime(2026, 10, 28, tzinfo=UTC))
    contests = [contest for contest, _ in fixtures]
    assert any(
        c.official_url is not None and c.verified_at is not None for c in contests
    )
    assert any(c.official_url is not None and c.verified_at is None for c in contests)
    collected = [c for c in contests if c.official_url is None]
    assert collected and all(c.source_url and c.verified_at is None for c in collected)

    date_only = next(c for c in contests if c.open_source_time is None)
    assert date_only.open_source_timezone is None and date_only.open_timezone_assumed
    assert date_only.close_source_time is None and date_only.close_time_assumed
    assert date_only.close_source_timezone is None and date_only.close_timezone_assumed
    local_open = date_only.registration_opens_at.astimezone(ZoneInfo("Asia/Seoul"))
    local_close = date_only.registration_closes_at.astimezone(ZoneInfo("Asia/Seoul"))
    assert local_open.date() == date_only.open_source_date
    assert local_open.time() == time.min
    assert local_close.date() == date_only.close_source_date + timedelta(days=1)
    assert local_close.time() == time.min
    assert any(
        c.open_source_time == time.min and not c.open_timezone_assumed for c in contests
    )
