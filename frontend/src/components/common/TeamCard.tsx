/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/TeamCard.tsx - 팀 카드 원본
 * 2. docs/design/screens.md - 탐색과 공모전 상세가 공유하는 TeamCard, 상세에서는 공모전명 생략
 * 3. docs/specs/team-recruitment.md#acceptance-criteria - 모집 역할·정원·상태
 * 4. docs/design/assets/contest-teams-390.png - 공모전 상세의 팀 카드
 */

import { ChevronRight } from 'lucide-react';
import { Link } from 'react-router';
import type { TeamWithContest } from '@/features/teams/status';
import {
  Badge,
  DemoBadge,
  TeamStatusBadge,
} from '@/components/common/CommonUi';

// [출처 2, 3, 4] 카드 전체 링크, 모집 상태·역할·인원 요약
export function TeamCard({
  team,
  to,
  roleLabel,
  showContest = true,
}: {
  team: TeamWithContest;
  to: string;
  /** 역할 코드 → 표시명(GET /catalogs). 공통 UI는 API를 직접 조회하지 않습니다. */
  roleLabel: (code: string) => string;
  showContest?: boolean;
}) {
  return (
    <Link className="preview-card preview-team-card" to={to}>
      <div className="preview-row preview-split">
        <TeamStatusBadge team={team} />
        <span className="preview-muted">{team.memberCount}명 활동 중</span>
      </div>
      <div className="preview-row">
        <h3>{team.name}</h3>
        <DemoBadge isDemo={team.isDemo} kind="team" />
      </div>
      <p className="preview-card-description">{team.introduction}</p>
      <div className="preview-row preview-team-card-roles">
        {team.roleCodes.map((code) => (
          <Badge key={code}>{roleLabel(code)}</Badge>
        ))}
        {!showContest && <ChevronRight size={20} aria-hidden="true" />}
      </div>
      {showContest && (
        <div className="preview-card-footer">
          <span>{team.contestTitle}</span>
          <ChevronRight size={20} aria-hidden="true" />
        </div>
      )}
    </Link>
  );
}
