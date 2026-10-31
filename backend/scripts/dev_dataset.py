"""원본 공고를 바꾸지 않고 시연 팀의 공고 분산과 소개를 결정한다."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.rules.catalogs import FieldCode, RoleCode
from app.rules.contests import validate_participation_capacity

DATASET_VERSION = "2.1.1"
RANDOM_SEED = 20261031
TARGET_TEAMS = 100
MAX_TEAMS_PER_CONTEST = 6
MIN_RUNWAY_DAYS = 7
PREFERRED_RUNWAY_DAYS = 21
TARGET_CONTESTS = 25


@dataclass(frozen=True)
class ContestCandidate:
    contest_id: UUID
    title: str
    field_codes: tuple[str, ...]
    created_at: datetime
    registration_opens_at: datetime
    registration_closes_at: datetime
    member_limit_kind: str
    min_members: int | None
    max_members: int | None


@dataclass(frozen=True)
class DatasetPlan:
    reference_at: datetime
    contests: tuple[ContestCandidate, ...]
    # 한 항목은 같은 공고의 상태 시연 팀·모집 중 앵커 팀 한 쌍이다.
    assignments: tuple[ContestCandidate, ...]
    warnings: tuple[str, ...]


def _require_timezone(value: datetime) -> None:
    if value.utcoffset() is None:
        raise ValueError("계획의 모든 시각에는 시간대가 필요합니다.")


def _eligible(contest: ContestCandidate, reference_at: datetime) -> bool:
    for value in (
        contest.created_at,
        contest.registration_opens_at,
        contest.registration_closes_at,
    ):
        _require_timezone(value)
    try:
        validate_participation_capacity(
            kind=contest.member_limit_kind,
            minimum_members=contest.min_members,
            maximum_members=contest.max_members,
        )
    except ValueError:
        return False
    return (
        contest.member_limit_kind in {"range", "unlimited"}
        and (contest.max_members is None or contest.max_members >= 3)
        and contest.registration_opens_at <= reference_at
        and contest.registration_closes_at
        >= reference_at + timedelta(days=MIN_RUNWAY_DAYS)
    )


def _select_contests(
    candidates: Sequence[ContestCandidate], reference_at: datetime
) -> tuple[ContestCandidate, ...]:
    recent = sorted(
        candidates,
        key=lambda item: (item.created_at, item.contest_id.int),
        reverse=True,
    )
    long_runway = sorted(
        candidates,
        key=lambda item: (
            item.registration_closes_at,
            item.created_at,
            item.contest_id.int,
        ),
        reverse=True,
    )
    uncovered = {code for item in candidates for code in item.field_codes}
    selected: list[ContestCandidate] = []
    selected_ids: set[UUID] = set()
    preferred_end = reference_at + timedelta(days=PREFERRED_RUNWAY_DAYS)
    while len(selected) < min(TARGET_CONTESTS, len(candidates)):
        order = recent if len(selected) % 2 == 0 else long_runway
        remaining = [item for item in order if item.contest_id not in selected_ids]
        if uncovered:
            # 먼저 가능한 분야를 확보한다. 같은 분야 수를 늘리는 후보끼리는
            # 21일 여유를 우선하고, 그 안에서 최신 등록·마감 여유를 번갈아 본다.
            best_coverage = max(
                len(uncovered.intersection(item.field_codes)) for item in remaining
            )
            remaining = [
                item
                for item in remaining
                if len(uncovered.intersection(item.field_codes)) == best_coverage
            ]
            preferred = [
                item
                for item in remaining
                if item.registration_closes_at >= preferred_end
            ]
            if preferred:
                remaining = preferred
        chosen = remaining[0]
        selected.append(chosen)
        selected_ids.add(chosen.contest_id)
        uncovered.difference_update(chosen.field_codes)
    return tuple(selected)


def build_plan(
    candidates: Sequence[ContestCandidate], reference_at: datetime
) -> DatasetPlan:
    """같은 공고·기준 시각이면 입력 순서와 무관하게 동일한 계획을 만든다.

    공고당 팀 수 상한을 유지하며 후보 부족 시 전체 팀 수를 줄인다.
    입력 공고·DB·시계를 수정하거나 외부 자료를 읽지 않는다.
    """
    _require_timezone(reference_at)
    reference_at = reference_at.astimezone(UTC)
    ids = [item.contest_id for item in candidates]
    if len(ids) != len(set(ids)):
        raise ValueError("계획에 중복 공고 ID를 전달할 수 없습니다.")
    eligible = [item for item in candidates if _eligible(item, reference_at)]
    selected = _select_contests(eligible, reference_at)
    if not selected:
        return DatasetPlan(
            reference_at,
            (),
            (),
            (
                f"접수 중이며 마감이 {MIN_RUNWAY_DAYS}일 이상 남고 "
                "3명 이상 참가 인원이 확인된 공고가 없어 팀을 생성하지 않습니다.",
            ),
        )
    # 공고를 연달아 채우지 않는다. 최신순 첫 화면에서도 여러 공고가 보이도록
    # 매 회차 모든 선정 공고에 한 쌍씩 배정한 다음 다음 회차로 넘어간다.
    assignments = tuple(
        contest for _ in range(MAX_TEAMS_PER_CONTEST // 2) for contest in selected
    )[: TARGET_TEAMS // 2]
    warnings: list[str] = []
    if len(selected) < TARGET_CONTESTS:
        warnings.append(
            f"목표 {TARGET_CONTESTS}개보다 적은 {len(selected)}개 공고에 분산합니다."
        )
    if len(assignments) * 2 < TARGET_TEAMS:
        warnings.append(
            f"공고당 최대 {MAX_TEAMS_PER_CONTEST}팀을 유지하기 위해 "
            f"목표 {TARGET_TEAMS}팀을 {len(assignments) * 2}팀으로 줄입니다."
        )
    short_runway = sum(
        item.registration_closes_at
        < reference_at + timedelta(days=PREFERRED_RUNWAY_DAYS)
        for item in selected
    )
    if short_runway:
        warnings.append(
            f"선정 공고 {short_runway}개는 마감까지 "
            f"{PREFERRED_RUNWAY_DAYS}일 미만입니다. "
            "시연 전 모집 가능 상태를 다시 확인하세요."
        )
    return DatasetPlan(reference_at, selected, assignments, tuple(warnings))


# 공식 공고의 요구사항을 새로 만들지 않고, 가상 팀이 제안하는 활동만 표현한다.
_FIELD_STORIES: dict[str, tuple[str, str]] = {
    "it_technology": (
        "코드브릿지",
        "문제에 맞는 기술을 조사하고 작은 프로토타입으로 아이디어를 검증하려 합니다",
    ),
    "business_startup": (
        "넥스트벤처",
        "이용자와 시장을 조사해 실행 가능한 가치 제안과 사업 가설을 정리하려 합니다",
    ),
    "design": (
        "시각공방",
        "사용 맥락과 시각 자료를 살펴보고 디자인 대안을 비교하며 발전시키려 합니다",
    ),
    "society_culture": (
        "컬처커넥트",
        "사회와 문화의 다양한 사례를 조사하고 공감할 수 있는 제안을 만들려 합니다",
    ),
    "environment": (
        "그린액션",
        "환경 문제의 근거를 조사하고 실천 가능한 개선 아이디어를 구체화하려 합니다",
    ),
    "education": (
        "배움메이트",
        "학습자의 어려움을 조사하고 이해하기 쉬운 교육 아이디어를 발전시키려 합니다",
    ),
    "media_content": (
        "스토리메이커",
        "전달할 메시지와 대상 독자를 정리하고 "
        "콘텐츠의 구성과 표현을 함께 실험하려 합니다",
    ),
    "health_medical": (
        "헬스인사이트",
        "건강 관련 이용자의 요구와 공개 자료를 조사하고 제안의 근거를 정리하려 합니다",
    ),
    "policy": (
        "정책스튜디오",
        "기존 정책과 현장의 사례를 비교하고 개선 제안의 실행 조건을 정리하려 합니다",
    ),
    "public": (
        "공공메이트",
        "공공 문제의 이해관계자와 이용 경험을 조사하고 개선 아이디어를 제안하려 합니다",
    ),
}
_WORKFLOWS = (
    "먼저 자료를 함께 읽고 문제 정의와 역할별 할 일을 정리합니다.",
    "초안을 일찍 공유하고 서로의 피드백으로 결과물을 다듬습니다.",
    "중간 목표를 작게 나누고 진행 기록을 남기며 협업합니다.",
    "조사 근거와 아이디어를 함께 검토하고 발표 흐름까지 준비합니다.",
)
_MEETINGS = (
    "평일 저녁 온라인 회의를 중심으로 일정을 조율합니다.",
    "주말 온라인 회의와 문서 피드백을 함께 활용합니다.",
    "주 1회 진행 상황을 공유하고 나머지 작업은 비동기로 진행하려 합니다.",
)
_CONTENT_ROLES = (
    RoleCode.PLANNING,
    RoleCode.DESIGN,
    RoleCode.MARKETING,
    RoleCode.RESEARCH,
    RoleCode.PRESENTATION,
)
_RESEARCH_ROLES = (RoleCode.PLANNING, RoleCode.RESEARCH, RoleCode.PRESENTATION)
_ROLE_ACTIONS = {
    RoleCode.PLANNING: "문제와 대상 이용자 정리",
    RoleCode.DESIGN: "시각 자료와 결과물의 표현 개선",
    RoleCode.DEVELOPMENT: "작은 시제품 구현이나 반복 작업 자동화로 아이디어 검증",
    RoleCode.MARKETING: "대상 독자와 전달 메시지 조사",
    RoleCode.RESEARCH: "공개 근거와 유사 사례 비교",
    RoleCode.PRESENTATION: "제안의 핵심과 설명 흐름 정리",
}


def team_story(
    index: int, contest: ContestCandidate
) -> tuple[str, str, tuple[str, ...]]:
    """공고의 실제 분야·제목을 바탕으로 역할 검색이 가능한 가상팀 소개를 만든다."""
    if index < 0:
        raise ValueError("팀 인덱스는 0 이상이어야 합니다.")
    fields = sorted(
        {FieldCode(code) for code in contest.field_codes},
        key=lambda code: code.sort_order,
    )
    if fields:
        field = fields[(index // 2) % len(fields)]
        name, direction = _FIELD_STORIES[field.value]
        focus = (
            f"{' · '.join(item.display_name for item in fields)} 분야에 관심이 있고, "
        )
    else:
        name = "함께도전"
        direction = "공고의 주제와 참고 자료를 읽고 팀의 아이디어를 구체화하려 합니다"
        focus = ""
    if any(
        field in {FieldCode.IT_TECHNOLOGY, FieldCode.BUSINESS_STARTUP}
        for field in fields
    ):
        # 기술 공고의 모집 중 앵커에도 개발 역할을 남겨 실제 작업으로 추천한다.
        chosen_roles = (
            RoleCode.DEVELOPMENT,
            _CONTENT_ROLES[(index // 2 + index % 2) % len(_CONTENT_ROLES)],
        )
    else:
        roles = (
            _CONTENT_ROLES
            if any(
                field in {FieldCode.DESIGN, FieldCode.MEDIA_CONTENT} for field in fields
            )
            else _RESEARCH_ROLES
        )
        chosen_roles = (roles[index % len(roles)], roles[(index + 1) % len(roles)])
    role_names = "·".join(role.display_name for role in chosen_roles)
    role_actions = ", ".join(
        f"{role.display_name}: {_ROLE_ACTIONS[role]}" for role in chosen_roles
    )
    introduction = (
        f"[시연용 가상팀] {contest.title}에 함께 도전합니다. "
        f"{focus}{direction}. {_WORKFLOWS[index % len(_WORKFLOWS)]} "
        f"{role_names} 역할의 동료를 찾습니다. "
        f"팀이 제안하는 작업은 {role_actions}입니다. "
        f"{_MEETINGS[(index // 2) % len(_MEETINGS)]} "
        "공고 원문을 함께 확인하고 세부 주제와 제출 형식을 맞추겠습니다."
    )
    return (
        f"{name} [테스트 T{index + 1:03d}]",
        introduction,
        tuple(role.value for role in chosen_roles),
    )
