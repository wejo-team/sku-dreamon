/** 개별 지원자의 항목별 점수와 빈 점선 트랙만 간결하게 표시합니다. */
import { useId } from 'react';
import type { ApplicantAssessment as Assessment } from '@/features/ai/contract';
import { criterionKeys, criterionLabels } from './assessment-ui';
import {
  ApplicantScoreBar,
  AssessmentMissingPattern,
} from './ApplicantScoreBar';

export function ApplicantAssessment({
  assessment,
}: {
  assessment: Assessment;
}) {
  const patternId = `individual-missing-${useId().replace(/:/g, '')}`;
  return (
    <figure className="applicant-assessment" aria-label="항목별 평가 점수">
      <figcaption className="assessment-score-heading">
        <span>항목별 평가</span>
        <span>100점 기준</span>
      </figcaption>
      {criterionKeys.map((key) => {
        const criterion = assessment.criteria.find((item) => item.key === key);
        const score = criterion?.score ?? null;
        return (
          <div className="assessment-score-row" key={key}>
            <span>{criterionLabels[key]}</span>
            <svg viewBox="0 0 240 28" className="assessment-score-mini">
              <defs>
                <AssessmentMissingPattern id={`${patternId}-${key}`} />
              </defs>
              <ApplicantScoreBar
                x={1}
                y={6}
                width={(score ?? 0) * 2}
                height={16}
                trackWidth={200}
                score={score}
                color="var(--primary)"
                label={criterionLabels[key]}
                patternId={`${patternId}-${key}`}
              />
            </svg>
          </div>
        );
      })}
    </figure>
  );
}
