"""시연 공고 선정·분산 계획과 검색 가능한 가상팀 소개를 검증한다."""

from collections import Counter
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.rules.catalogs import FieldCode, RoleCode
from scripts.dev_dataset import (
    MAX_TEAMS_PER_CONTEST,
    TARGET_CONTESTS,
    TARGET_TEAMS,
    ContestCandidate,
    build_plan,
    team_story,
)

REFERENCE = datetime(2026, 10, 31, 12, tzinfo=UTC)


def candidate(index: int, *, days_left: int = 40) -> ContestCandidate:
    return ContestCandidate(
        contest_id=UUID(int=index + 1),
        title=f"개발용 공고 {index + 1}",
        field_codes=(list(FieldCode)[index % len(FieldCode)].value,),
        created_at=REFERENCE - timedelta(days=index),
        registration_opens_at=REFERENCE - timedelta(days=10),
        registration_closes_at=REFERENCE + timedelta(days=days_left),
        member_limit_kind="range",
        min_members=2,
        max_members=5,
    )


def test_eighteen_contests_get_balanced_teams_and_diverse_latest_pages() -> None:
    plan = build_plan([candidate(i) for i in range(18)], REFERENCE)
    counts = Counter(item.contest_id for item in plan.assignments)

    assert len(plan.assignments) * 2 == TARGET_TEAMS
    assert len(counts) == 18
    assert {pairs * 2 for pairs in counts.values()} == {4, 6}
    assert max(counts.values()) * 2 <= MAX_TEAMS_PER_CONTEST
    assert len({item.contest_id for item in plan.assignments[:4]}) == 4
    assert len({item.contest_id for item in plan.assignments[-4:]}) == 4
    assert plan.reference_at == REFERENCE


def test_selection_keeps_rare_fields_and_recent_and_long_runway_contests() -> None:
    candidates = [
        replace(candidate(i), field_codes=(FieldCode.IT_TECHNOLOGY.value,))
        for i in range(40)
    ]
    rare = replace(
        candidate(99),
        field_codes=(FieldCode.HEALTH_MEDICAL.value, FieldCode.PUBLIC.value),
    )
    long_runway = replace(
        candidate(80), registration_closes_at=REFERENCE + timedelta(days=120)
    )
    plan = build_plan([*candidates, rare, long_runway], REFERENCE)
    chosen = {item.contest_id for item in plan.contests}

    assert len(chosen) == TARGET_CONTESTS
    assert rare.contest_id in chosen
    assert candidates[0].contest_id in chosen
    assert long_runway.contest_id in chosen
    assert {code for item in plan.contests for code in item.field_codes} == {
        code for item in [*candidates, rare, long_runway] for code in item.field_codes
    }


def test_equal_registration_time_uses_uuid_to_break_ties() -> None:
    candidates = [
        replace(
            candidate(i),
            field_codes=(FieldCode.IT_TECHNOLOGY.value,),
            created_at=REFERENCE - timedelta(days=1),
        )
        for i in range(30)
    ]
    plan = build_plan(candidates, REFERENCE)

    assert plan.contests[0].contest_id == candidates[-1].contest_id


def test_plan_is_independent_of_input_order() -> None:
    candidates = [candidate(i, days_left=7 + i) for i in range(35)]

    assert build_plan(candidates, REFERENCE) == build_plan(
        list(reversed(candidates)), REFERENCE
    )


def test_opening_and_minimum_runway_boundaries_are_inclusive() -> None:
    eligible = replace(candidate(0, days_left=7), registration_opens_at=REFERENCE)
    too_short = replace(
        candidate(1, days_left=7),
        registration_closes_at=REFERENCE + timedelta(days=7, microseconds=-1),
    )
    scheduled = replace(
        candidate(2), registration_opens_at=REFERENCE + timedelta(microseconds=1)
    )
    closed = replace(candidate(3), registration_closes_at=REFERENCE)
    plan = build_plan([eligible, too_short, scheduled, closed], REFERENCE)

    assert plan.contests == (eligible,)
    assert len(plan.assignments) == MAX_TEAMS_PER_CONTEST // 2
    assert plan.warnings


def test_only_confirmed_capacity_with_room_for_three_is_eligible() -> None:
    unknown = replace(
        candidate(0), member_limit_kind="unknown", min_members=None, max_members=None
    )
    small = replace(candidate(1), max_members=2)
    unlimited = replace(
        candidate(2), member_limit_kind="unlimited", min_members=None, max_members=None
    )
    invalid_range = replace(candidate(3), min_members=5, max_members=3)
    invalid_kind = replace(candidate(4), member_limit_kind="unexpected")
    plan = build_plan(
        [unknown, small, unlimited, invalid_range, invalid_kind], REFERENCE
    )

    assert plan.contests == (unlimited,)


def test_sparse_inputs_reduce_team_count_instead_of_concentrating() -> None:
    plan = build_plan([candidate(i) for i in range(3)], REFERENCE)

    assert len(plan.assignments) * 2 == 18
    assert set(Counter(item.contest_id for item in plan.assignments).values()) == {3}
    assert any("100" in warning and "18" in warning for warning in plan.warnings)


def test_no_candidates_produces_empty_plan_with_warning() -> None:
    plan = build_plan([], REFERENCE)

    assert plan.contests == ()
    assert plan.assignments == ()
    assert plan.warnings


def test_naive_reference_and_candidate_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="시간대"):
        build_plan([candidate(0)], REFERENCE.replace(tzinfo=None))
    with pytest.raises(ValueError, match="시간대"):
        build_plan(
            [replace(candidate(0), created_at=REFERENCE.replace(tzinfo=None))],
            REFERENCE,
        )


def test_duplicate_contest_ids_do_not_silently_multiply_assignments() -> None:
    with pytest.raises(ValueError, match="중복"):
        build_plan([candidate(0), candidate(0)], REFERENCE)


def test_team_stories_use_contest_fields_and_cover_searchable_roles() -> None:
    stories = [team_story(i, candidate(i)) for i in range(100)]

    assert len({name for name, _, _ in stories}) == 100
    assert {role for _, _, roles in stories for role in roles} == set(RoleCode)
    for i, (name, introduction, roles) in enumerate(stories):
        contest = candidate(i)
        assert name
        assert contest.title in introduction
        assert FieldCode(contest.field_codes[0]).display_name in introduction
        assert len(roles) == len(set(roles)) == 2
        assert all(RoleCode(role).display_name in introduction for role in roles)
        assert "시연용 가상팀" in introduction


def test_unclassified_contest_has_neutral_story_without_inventing_a_field() -> None:
    contest = replace(candidate(0), field_codes=())
    _, introduction, roles = team_story(0, contest)

    assert contest.title in introduction
    assert "공고 원문" in introduction
    assert "캠퍼스" not in introduction
    assert len(roles) == 2
    assert set(roles) <= {"planning", "research", "presentation"}


@pytest.mark.parametrize("field_code", ["it_technology", "business_startup"])
def test_technical_contests_keep_development_in_both_teams_with_concrete_work(
    field_code: str,
) -> None:
    contest = replace(candidate(0), field_codes=(field_code,))
    for index in range(12):
        _, introduction, roles = team_story(index, contest)
        assert "development" in roles
        assert len(set(roles)) == 2
        assert "시제품 구현" in introduction
        assert "팀이 제안하는 작업" in introduction


@pytest.mark.parametrize("field_code", ["design", "media_content"])
def test_content_contests_cover_relevant_roles_without_development(
    field_code: str,
) -> None:
    contest = replace(candidate(0), title="콘텐츠 공모전", field_codes=(field_code,))
    stories = [team_story(index, contest) for index in range(10)]
    assert {role for _, _, roles in stories for role in roles} == {
        "planning",
        "design",
        "marketing",
        "research",
        "presentation",
    }
    # 시연 표시 문구가 AI의 '개발' 검색에 모든 비개발 팀을 끌어오면 안 된다.
    assert all("개발" not in introduction for _, introduction, _ in stories)


@pytest.mark.parametrize("field_codes", [(), ("policy",)])
def test_policy_and_unclassified_contests_use_research_roles(
    field_codes: tuple[str, ...],
) -> None:
    contest = replace(
        candidate(0), title="정책 아이디어 공모전", field_codes=field_codes
    )
    stories = [team_story(index, contest) for index in range(12)]
    assert {role for _, _, roles in stories for role in roles} == {
        "planning",
        "research",
        "presentation",
    }
    assert all("개발" not in introduction for _, introduction, _ in stories)
