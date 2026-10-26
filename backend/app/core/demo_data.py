"""명시된 고정 UUID만 시연 데이터로 분류한다."""

from uuid import UUID, uuid5

# 개발 시드와 API가 같은 고정 식별자를 사용한다. 실제 공고는 시드하지 않는다.
DEV_NAMESPACE = UUID("9f10a245-4339-5b13-9f30-a988a9e5d063")
DEV_ACCOUNT_IDS = tuple(uuid5(DEV_NAMESPACE, f"account:{i}") for i in range(1, 301))
DEV_TEAM_IDS = tuple(uuid5(DEV_NAMESPACE, f"team:{i}") for i in range(1, 101))
ACCOUNT_IDS: frozenset[UUID] = frozenset(DEV_ACCOUNT_IDS)
CONTEST_IDS: frozenset[UUID] = frozenset()
TEAM_IDS: frozenset[UUID] = frozenset(DEV_TEAM_IDS)


def is_demo_account(account_id: UUID) -> bool:
    return account_id in ACCOUNT_IDS


def is_demo_contest(contest_id: UUID) -> bool:
    return contest_id in CONTEST_IDS


def is_demo_team(team_id: UUID) -> bool:
    return team_id in TEAM_IDS
