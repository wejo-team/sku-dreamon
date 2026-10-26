/**
 * [참조 출처]
 * 1. docs/development/frontend.md - 「API와 query」 query key에 리소스와 조회 조건 포함, mutation 성공 시 영향받은 query 무효화
 * 2. docs/api/conventions.md#session-auth - 로그인 세션이 바뀌면 본인 데이터를 다시 조회
 * 3. docs/api/conventions.md#versioned-action - 다른 변경이 먼저 저장됐다면 409 후 다시 조회(자동 재전송 없음)
 *
 * 화면이 쓰는 TanStack Query key의 단일 원본입니다. 첫 요소는 리소스 범위이며 무효화 단위로 씁니다.
 */

import type { QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';

// [출처 1] 리소스별 key. 조회 조건 객체를 마지막 요소로 둡니다.
export const queryKeys = {
  me: ['auth', 'me'] as const,
  catalogs: ['catalogs'] as const,
  academicUnits: ['catalogs', 'academic-units'] as const,
  contests: (query: object) => ['contests', 'list', query] as const,
  contest: (id: string) => ['contests', 'detail', id] as const,
  openContestSearch: (q: string) => ['contests', 'open-search', q] as const,
  people: (query: object) => ['people', 'list', query] as const,
  person: (id: string) => ['people', 'detail', id] as const,
  myProfile: ['my', 'profile'] as const,
  teams: (query: object) => ['teams', 'list', query] as const,
  contestTeams: (contestId: string, query: object) =>
    ['teams', 'contest', contestId, query] as const,
  team: (id: string) => ['teams', 'detail', id] as const,
  teamSpace: (id: string) => ['teams', 'space', id] as const,
  myTeams: (query: object) => ['my', 'teams', query] as const,
  myApplications: (query: object) => ['my', 'applications', query] as const,
  application: (id: string) => ['applications', 'detail', id] as const,
  applicants: (teamId: string, query: object) =>
    ['applications', 'applicants', teamId, query] as const,
  applicant: (id: string) => ['applications', 'applicant', id] as const,
  notifications: (query: object) => ['my', 'notifications', query] as const,
};

// [출처 1] 팀·지원 상태가 바뀌면 목록·상세·내 활동·알림·공고의 팀 수가 함께 바뀝니다.
export const invalidateParticipation = (client: QueryClient) =>
  Promise.all(
    ['teams', 'applications', 'my', 'contests'].map((scope) =>
      client.invalidateQueries({ queryKey: [scope] }),
    ),
  );

// [출처 3] 버전 충돌(409)이면 화면이 최신 version으로 다시 시도할 수 있게 관련 query를 다시 받습니다.
export const isConflict = (error: unknown) =>
  error instanceof ApiError && error.status === 409;

// [출처 2] 세션 전환 뒤 선택지(catalogs)를 제외한 모든 데이터를 비우고 새 세션 기준으로 다시 받습니다.
// 팀·지원자·사람 응답은 보는 계정의 권한에 따라 달라지므로, 재조회가 403·404여도 이전 계정의 값이 남지 않게 합니다.
export const resetSessionData = (client: QueryClient) =>
  client.resetQueries({
    predicate: (query) => query.queryKey[0] !== 'catalogs',
  });
