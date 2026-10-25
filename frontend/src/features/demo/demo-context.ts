/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/preview-context.ts - 상태 context 원본
 * 2. docs/design/handoff.md - 메모리 Provider·예시 타입을 서버 계약으로 사용하지 않음
 * 3. docs/api/README.md - 상태의 각 항목은 API DTO 모양(Account·Profile·Contest·Team·Application·Notification)
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { createContext, useContext } from 'react';
import type { Account } from '@/features/auth/api';
import type { Contest } from '@/features/contests/api';
import type { Profile } from '@/features/profiles/api';
import type { Team, TeamMember } from '@/features/teams/api';
import type { Application } from '@/features/applications/api';
import type { Notification } from '@/features/notifications/api';
import type { DemoDatabase } from '@/features/demo/fixtures';
import type { NewTeamInput, TransitionError } from '@/features/demo/team-state';

export type ActionResult = { ok: true } | { ok: false; error: TransitionError };

// [출처 1, 3] 화면이 읽고 쓰는 로컬 상태와 동작
export type DemoState = {
  signedIn: boolean;
  /** 목업 저장소 전체(서버 대신) */
  db: DemoDatabase;
  /** 데모 계정(로그인 여부와 관계없이 고정) */
  account: Account;
  /** 본인 현재 프로필 */
  profile: Profile;
  contests: Contest[];
  teams: Team[];
  applications: Application[];
  /** 본인에게 보이는 알림(최신순 아님, 화면에서 정렬) */
  notifications: Notification[];
  teamMembers: (teamId: string) => TeamMember[];
  markNotificationsRead: (ids: string[]) => void;
  signIn: () => void;
  signOut: () => void;
  saveProfile: (profile: Profile) => void;
  apply: (teamId: string, roleCode: string, message: string) => ActionResult;
  selectApplicant: (applicationId: string) => ActionResult;
  rejectApplicant: (applicationId: string) => ActionResult;
  cancelApplication: (applicationId: string) => ActionResult;
  closeRecruitment: (teamId: string) => ActionResult;
  reopenRecruitment: (teamId: string) => ActionResult;
  /** 성공하면 새 팀 ID, 실패하면 빈 문자열 */
  createTeam: (team: NewTeamInput) => string;
  reset: () => void;
  emptyWorkspace: () => void;
};
// [출처 1] 상태 공유 context
export const DemoContext = createContext<DemoState | null>(null);
// [출처 1] Provider 밖 사용 방지
export function useDemo() {
  const value = useContext(DemoContext);
  if (!value) throw new Error('DemoProvider가 필요합니다.');
  return value;
}
