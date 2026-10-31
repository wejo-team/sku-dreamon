/**
 * [참조 출처]
 * 1. docs/design/tokens.md - 작은 팀 카드의 정보 계층과 긴 소개 표시
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
      <div className="preview-team-card-heading">
        <div className="preview-team-card-title">
          <h3>{team.name}</h3>
          <DemoBadge isDemo={team.isDemo} kind="team" />
        </div>
        <TeamStatusBadge team={team} />
      </div>
      <p className="preview-card-description">{team.introduction}</p>
      <div className="preview-team-card-meta">
        <div className="preview-row preview-team-card-roles">
          {team.roleCodes.map((code) => (
            <Badge key={code}>{roleLabel(code)}</Badge>
          ))}
        </div>
        <span className="preview-muted preview-team-card-members">
          {team.memberCount}명 활동 중
          {!showContest && <ChevronRight size={18} aria-hidden="true" />}
        </span>
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
