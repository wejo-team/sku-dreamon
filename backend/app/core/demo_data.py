"""명시된 고정 UUID만 시연 데이터로 분류한다."""

from uuid import UUID

# 아직 운영·시연 시드가 선택되거나 적재되지 않았다. #117에서 실제 시드를
# 추가할 때 적재 코드와 이 목록을 함께 변경하며, 이름으로 추측하지 않는다.
ACCOUNT_IDS: frozenset[UUID] = frozenset()
CONTEST_IDS: frozenset[UUID] = frozenset()
TEAM_IDS: frozenset[UUID] = frozenset()


def is_demo_account(account_id: UUID) -> bool:
    return account_id in ACCOUNT_IDS


def is_demo_contest(contest_id: UUID) -> bool:
    return contest_id in CONTEST_IDS


def is_demo_team(team_id: UUID) -> bool:
    return team_id in TEAM_IDS
