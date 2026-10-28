// docs/specs/matching.md: 실제 모드의 현재 팀장에게만 지원자 후보 추천을 제공합니다.
import { isMockApi } from '@/lib/clock';
import { TargetAiPanel } from './TargetAiPanel';

export function TeamApplicantRecommendations({
  teamId,
  revision,
  isLeader,
}: {
  teamId: string;
  revision: string;
  isLeader: boolean;
}) {
  if (!isLeader || isMockApi) return null;
  return (
    <TargetAiPanel
      purpose="applicant_recommendation"
      targetId={teamId}
      revision={revision}
    />
  );
}
