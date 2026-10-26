/**
 * [참조 출처]
 * 1. docs/api/teams.md#values - recruitmentState open|closed, closedReason, isRecruiting은 서버가 계산한 공통 모집 가능 조건
 * 2. docs/api/contests.md#values - registrationStatus scheduled|open|closed
 * 3. docs/specs/team-recruitment.md#recruitment-reopening - 정원 충족 후 자동 재개 없음, 팀장만 재개
 * 4. docs/design/tokens.md - 「shadcn/ui 사용 맵」 TeamStatusBadge 문구
 *
 * 화면의 모집 상태 문구를 서버가 내려준 값(isRecruiting·recruitmentState·memberCount·registrationStatus)으로만 정합니다.
 * 시각 비교는 서버 계산을 따르며 화면에서 다시 계산하지 않습니다(기한 경과 재개는 서버의 409 RECRUITMENT_DEADLINE_PASSED로 안내).
 */

import type { ContestSummary } from '@/features/contests/api';
import type { TeamSummary } from '@/features/teams/api';

/** 목록 요약에 연결 공고 요약이 붙어 있을 수 있는 팀(TeamDetail은 contest 포함) */
export type TeamWithContest = TeamSummary & { contest?: ContestSummary };

const isFull = (team: TeamSummary) => team.memberCount >= Number(team.capacity);

// [출처 1, 2] 신규 지원이 막힌 이유(없으면 null)
export function recruitmentIssue(team: TeamWithContest): string | null {
  const contestStatus = team.contest?.registrationStatus;
  if (contestStatus === 'closed')
    return '공모전 접수가 마감되어 지원할 수 없어요.';
  if (contestStatus === 'scheduled')
    return '공모전 접수가 시작되면 지원할 수 있어요.';
  if (team.recruitmentState === 'closed')
    return '모집이 마감되어 지금은 지원할 수 없어요.';
  if (isFull(team)) return '팀 정원이 모두 찼어요.';
  if (!team.isRecruiting) return '팀 모집 기한이 지나 지원할 수 없어요.';
  return null;
}

// [출처 1, 4] 배지 문구. 색과 함께 문구로 구분
export function teamStatusLabel(team: TeamWithContest) {
  if (team.recruitmentState === 'closed') return '모집 마감';
  if (isFull(team)) return '정원 충족';
  if (team.contest?.registrationStatus === 'scheduled') return '모집 예정';
  return team.isRecruiting ? '모집 중' : '모집 마감';
}

// [출처 2, 3] 모집 재개 불가 사유(없으면 null). 팀장 여부는 화면이 확인합니다.
export function recruitmentReopeningIssue(team: TeamWithContest) {
  if (team.recruitmentState !== 'closed')
    return '마감된 모집만 다시 시작할 수 있어요.';
  if (isFull(team)) return '팀 정원이 모두 차서 다시 모집할 수 없어요.';
  const contestStatus = team.contest?.registrationStatus;
  if (contestStatus === 'closed')
    return '공모전 접수가 마감되어 다시 모집할 수 없어요.';
  if (contestStatus === 'scheduled')
    return '공모전 접수가 시작되면 다시 모집할 수 있어요.';
  return null;
}
