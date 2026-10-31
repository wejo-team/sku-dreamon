/** 항목별 점수는 작은 막대로, 자료 부족은 빈 점선으로 구분합니다. */
import { useId } from 'react';
import type { ApplicantAssessment as Assessment } from './applicant-assessment-types';
import { criterionKeys, criterionLabels } from './assessment-ui';
import './applicant-assessment.css';

export function ApplicantAssessment({
  assessment,
}: {
  assessment: Assessment;
}) {
  const id = useId();
  const criteria = criterionKeys.flatMap((key) =>
    assessment.criteria.filter((criterion) => criterion.key === key),
  );
  return (
    <figure className="applicant-assessment">
      <figcaption>
        <span>항목별 점수</span>
        <span className="assessment-scale">100점 기준</span>
      </figcaption>
      <dl className="assessment-scores" aria-label="항목별 평가 점수">
        {criteria.map((criterion) => {
          const label = criterionLabels[criterion.key];
          const title =
            criterion.score === null
              ? `${label}: 자료 부족으로 점수 없음`
              : `${label}: ${criterion.score}점`;
          return (
            <div key={criterion.key} className="assessment-score-row">
              <dt>{label}</dt>
              <dd>
                <svg
                  className="assessment-score-chart"
                  viewBox="0 0 100 10"
                  preserveAspectRatio="none"
                  role="img"
                  aria-labelledby={`${id}-${criterion.key}`}
                >
                  <title id={`${id}-${criterion.key}`}>{title}</title>
                  {criterion.score === null ? (
                    <line
                      className="assessment-score-missing"
                      x1={1}
                      x2={99}
                      y1={5}
                      y2={5}
                      strokeDasharray="2 2"
                    />
                  ) : (
                    <>
                      <rect
                        className="assessment-score-track"
                        width={100}
                        height={10}
                        rx={2}
                      />
                      <rect
                        className="assessment-score-bar"
                        width={criterion.score}
                        height={10}
                        rx={2}
                      />
                    </>
                  )}
                </svg>
                <span className="assessment-score-value" aria-hidden="true">
                  {criterion.score ?? '—'}
                </span>
              </dd>
            </div>
          );
        })}
      </dl>
    </figure>
  );
}
