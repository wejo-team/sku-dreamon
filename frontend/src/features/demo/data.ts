/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/data.ts - 변환 전 예시 데이터 원본
 * 2. docs/api/README.md - 화면과 서버가 같은 요청·응답 DTO를 사용
 * 3. docs/api/profiles.md#directory-endpoints - 공개 프로필만 사람 탐색에 노출
 * 4. docs/design/handoff.md - 공고·인물·팀은 화면 확인용 데이터
 *
 * 화면이 쓰는 API DTO 타입과 초기 목업 스냅샷을 한곳에서 내보냅니다. 레코드의 원본은 fixtures.ts입니다.
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import type { Profile } from '@/features/profiles/api';
import { createDemoRecords, demoIds } from '@/features/demo/fixtures';
import { allContests, allTeams } from '@/features/demo/team-state';

export type { Account } from '@/features/auth/api';
export type { ContestDetail, ContestSummary } from '@/features/contests/api';
export type {
  Profile,
  PersonSummary,
  ProfileWrite,
} from '@/features/profiles/api';
export type { TeamDetail, TeamSummary, TeamMember } from '@/features/teams/api';
export type {
  Application,
  ApplicationStatus,
  Applicant,
} from '@/features/applications/api';
export type { Notification } from '@/features/notifications/api';
export { demoIds };

// [출처 1] 초기 목업 스냅샷(목업 서버·테스트의 출발점)
const initial = createDemoRecords();
const archiveId = demoIds.contests.archive;

// [출처 4] 탐색 대상 공모전(마감 공고 예시는 별도)
export const contests = allContests(initial).filter(
  (contest) => contest.id !== archiveId,
);
export const archivedContest = allContests(initial).find(
  (contest) => contest.id === archiveId,
)!;
export const initialTeams = allTeams(initial);
export const initialApplications = initial.applications;
export const initialProfile: Profile = initial.profiles.find(
  (item) => item.accountId === initial.account.id,
)!;
export const initialAccount = initial.account;
export const initialProfiles = initial.profiles;

// [출처 3] 현재 공개 상태일 때만 다른 사람에게 보이는 프로필
export const getPublicProfile = (profile: Profile): Profile | null =>
  profile.isPublic ? profile : null;

// [출처 3] 사람 탐색 대상: 본인을 제외한 공개 프로필
export const people: Profile[] = initial.profiles.filter(
  (profile) => profile.isPublic && profile.accountId !== initial.account.id,
);
