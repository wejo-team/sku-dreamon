// docs/specs/matching.md AC-29~33: 기존 지원 검토는 선발 후보 여부와 구분합니다.
import type { Application } from '@/features/applications/api';
import type { Profile } from '@/features/profiles/api';
import { isMockApi } from '@/lib/clock';
import { MockApplicantReview } from './MockApplicantReview';
import { TargetAiPanel } from './TargetAiPanel';

export function ApplicantReview(props: {
  application: Application;
  profile: Profile;
  mayReviewExistingApplication: boolean;
}) {
  if (!props.mayReviewExistingApplication) return null;
  if (isMockApi) return <MockApplicantReview {...props} />;
  return (
    <TargetAiPanel
      purpose="applicant_review"
      targetId={props.application.id}
      revision={`${props.application.version}:${props.application.status}:${props.profile.version}`}
    />
  );
}
