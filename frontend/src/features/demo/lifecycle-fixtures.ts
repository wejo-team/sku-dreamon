/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/lifecycle-fixtures.ts - 팀 수명주기 재현 데이터 원본
 * 2. docs/design/screens.md - 「재현 경로」 scenario=team-lifecycle
 * 3. docs/api/applications.md#application - discardReason·discardedByApplicationId 등 폐기 필드
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import {
  createDemoRecords,
  demoIds,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import { historyNotifications } from '@/features/demo/notification-state';

const { accounts, teams, applications, memberships } = demoIds;

/** A review scenario only; no persistence or production seeding contract. */
// [출처 2] 폐기·선발·재개 확인용 초기 상태
export function lifecycleReferenceDatabase(): DemoDatabase {
  const db = createDemoRecords();
  const green = db.teams.find((team) => team.id === teams.greenwave)!;
  const local = db.teams.find((team) => team.id === teams.localcrew)!;
  const seoyeonApplication = db.applications.find(
    (item) => item.id === applications.seoyeon,
  )!;
  const myLocalApplication = db.applications.find(
    (item) => item.id === applications.localcrew,
  )!;
  const base = db.profiles.find((item) => item.accountId === accounts.minjun)!;

  const next: DemoDatabase = {
    ...db,
    profiles: [
      ...db.profiles,
      { ...base, accountId: accounts.seojun, realName: '이서준' },
      {
        ...base,
        accountId: accounts.suhyun,
        realName: '이수현',
        fieldCodes: ['design'],
        roleCodes: ['design'],
      },
    ],
    teams: [
      // 그린웨이브: 팀장이 마감한 상태(재개 확인용)
      ...db.teams.map((team) =>
        team.id === green.id
          ? {
              ...team,
              recruitmentState: 'closed' as const,
              closedReason: 'leader_closed' as const,
              version: '2',
            }
          : team,
      ),
      {
        ...green,
        id: teams.greenmakers,
        name: '그린 메이커스',
        ownerAccountId: accounts.seojun,
        createdAt: '2026-10-06T12:00:00Z',
      },
      {
        ...local,
        id: teams.localstudio,
        name: '로컬 스튜디오',
        ownerAccountId: accounts.suhyun,
        recruitmentState: 'open',
        closedReason: null,
        version: '1',
        createdAt: '2026-10-05T12:00:00Z',
      },
    ],
    memberships: [
      ...db.memberships,
      {
        membershipId: memberships.greenmakersLeader,
        teamId: teams.greenmakers,
        accountId: accounts.seojun,
        membershipRole: 'leader',
        roleCode: null,
        joinedAt: '2026-10-06T12:00:00Z',
        endedAt: null,
      },
      {
        membershipId: memberships.greenmakersSeoyeon,
        teamId: teams.greenmakers,
        accountId: accounts.seoyeon,
        membershipRole: 'member',
        roleCode: 'development',
        joinedAt: '2026-10-16T12:00:00Z',
        endedAt: null,
      },
      {
        membershipId: memberships.localstudioLeader,
        teamId: teams.localstudio,
        accountId: accounts.suhyun,
        membershipRole: 'leader',
        roleCode: null,
        joinedAt: '2026-10-05T12:00:00Z',
        endedAt: null,
      },
    ],
    applications: [
      // [출처 3] 김서연이 그린 메이커스에 선발되어 그린웨이브 대기 지원은 폐기
      ...db.applications.map((item) =>
        item.id === seoyeonApplication.id
          ? {
              ...item,
              status: 'discarded' as const,
              discardReason: 'selected_elsewhere' as const,
              discardedByApplicationId: applications.greenmakersSeoyeon,
              version: '3',
              updatedAt: '2026-10-16T12:00:00Z',
            }
          : item,
      ),
      {
        ...seoyeonApplication,
        id: applications.greenmakersSeoyeon,
        teamId: teams.greenmakers,
        status: 'selected',
        version: '2',
        submittedAt: '2026-10-13T00:00:00Z',
        updatedAt: '2026-10-16T12:00:00Z',
      },
      // [출처 3] 내가 로컬 크루에 선발되어 로컬 스튜디오 대기 지원은 폐기
      {
        ...myLocalApplication,
        id: applications.discardedLocal,
        teamId: teams.localstudio,
        status: 'discarded',
        discardReason: 'selected_elsewhere',
        discardedByApplicationId: myLocalApplication.id,
        message: '지역의 이야기를 함께 발굴하고 싶어요.',
        version: '2',
        submittedAt: '2026-10-08T00:00:00Z',
        updatedAt: '2026-10-11T00:00:00Z',
      },
    ],
  };
  const notificationIds = [...Array(32).keys()].map(
    (index) =>
      `ffffffff-0000-4000-8000-${(0x100 + index).toString(16).padStart(12, '0')}`,
  );
  return {
    ...next,
    notifications: historyNotifications(
      next,
      (index) => notificationIds[index]!,
    ),
  };
}
