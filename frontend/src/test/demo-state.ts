/**
 * [참조 출처]
 * 1. docs/development/testing.md - 「의미 있는 테스트」 컴포넌트 옆 테스트, 사용자 동작 검증
 * 2. docs/api/README.md - 화면 상태는 API DTO 모양
 *
 * 테스트용 DemoState 생성 도우미입니다. 목업 저장소(DTO)에서 읽기 값을 계산하고 동작은 vi.fn()으로 둡니다.
 */

import { vi } from 'vitest';
import type { DemoState } from '@/features/demo/demo-context';
import { deriveDemoState } from '@/features/demo/demo-state';
import {
  createDemoRecords,
  demoIds,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import type { Profile } from '@/features/profiles/api';

export { demoIds };
export const ME = demoIds.accounts.me;

/** 목업 저장소 → 테스트용 DemoState. overrides로 동작이나 읽기 값을 바꿀 수 있습니다. */
export function demoState(
  overrides: Partial<DemoState> & { db?: DemoDatabase } = {},
): DemoState {
  const { db = createDemoRecords(), signedIn = true, ...rest } = overrides;
  return {
    ...deriveDemoState(db, signedIn),
    markNotificationsRead: vi.fn(),
    signIn: vi.fn(),
    signOut: vi.fn(),
    saveProfile: vi.fn(),
    apply: vi.fn(() => ({ ok: true as const })),
    selectApplicant: vi.fn(() => ({ ok: true as const })),
    rejectApplicant: vi.fn(() => ({ ok: true as const })),
    cancelApplication: vi.fn(() => ({ ok: true as const })),
    closeRecruitment: vi.fn(() => ({ ok: true as const })),
    reopenRecruitment: vi.fn(() => ({ ok: true as const })),
    createTeam: vi.fn(() => 'new-team'),
    reset: vi.fn(),
    emptyWorkspace: vi.fn(),
    ...rest,
  };
}

/** 특정 계정의 프로필을 바꾼 저장소 사본 */
export function withProfile(
  db: DemoDatabase,
  accountId: string,
  patch: Partial<Profile>,
): DemoDatabase {
  return {
    ...db,
    profiles: db.profiles.map((item) =>
      item.accountId === accountId ? { ...item, ...patch } : item,
    ),
  };
}

/** 본인 프로필을 바꾼 새 목업 저장소 */
export const recordsWithMyProfile = (patch: Partial<Profile>) =>
  withProfile(createDemoRecords(), ME, patch);
