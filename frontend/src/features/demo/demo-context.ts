/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/preview-context.ts - 상태 context 원본
 * 2. docs/design/handoff.md - 메모리 Provider·예시 타입을 서버 계약으로 사용하지 않음
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { createContext, useContext } from 'react';
import type {
  Applicant,
  Application,
  Profile,
  Team,
} from '@/features/demo/data';
import type { NewTeam } from '@/features/demo/team-state';
import type { PreviewNotification } from '@/features/demo/notification-state';

// [출처 1, 2] 화면이 읽고 쓰는 로컬 상태와 동작
export type DemoState = {
  signedIn: boolean;
  profile: Profile;
  teams: Team[];
  applications: Application[];
  applicants: Applicant[];
  notifications: PreviewNotification[];
  markNotificationsRead: (ids: string[]) => void;
  signIn: () => void;
  signOut: () => void;
  saveProfile: (profile: Profile) => void;
  apply: (teamId: string, role: string, message: string) => boolean;
  selectApplicant: (id: string) => boolean;
  cancelApplication: (id: string) => boolean;
  closeRecruitment: (id: string) => boolean;
  reopenRecruitment: (id: string) => boolean;
  createTeam: (team: NewTeam) => string;
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
