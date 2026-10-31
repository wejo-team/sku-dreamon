/** 후보별 막대그래프·비교 선택·지원서 이동만 제공하고 평가 근거는 노출하지 않습니다. */
import { lazy, Suspense, useId, useState } from 'react';
import { Link } from 'react-router';
import { ArrowUpRight, Check, SlidersHorizontal } from 'lucide-react';
import { NativeSelect } from '@/components/ui/native-select';
import type { ApplicantRecommendation } from '@/features/ai/contract';
import { useLabels } from '@/features/catalogs/queries';
import { criterionKeys, criterionScoreDescription } from './assessment-ui';
import { ApplicantChartBoundary } from './ApplicantChartBoundary';

const ApplicantComparisonChart = lazy(
  () => import('./ApplicantComparisonChart'),
);

export function ApplicantCandidateResults({
  candidates,
}: {
  candidates: ApplicantRecommendation[];
}) {
  const id = useId();
  const labels = useLabels();
  const [skill, setSkill] = useState('');
  const [selection, setSelection] = useState<(string | null)[] | null>(null);
  const skills = [
    ...new Set(candidates.flatMap((candidate) => candidate.profile.skillCodes)),
  ];
  const activeSkill = skills.some((code) => code === skill) ? skill : '';
  const visible = candidates.filter(
    (candidate) =>
      !activeSkill ||
      candidate.profile.skillCodes.some((code) => code === activeSkill),
  );
  // 유지된 지원자의 색이 바뀌지 않도록 해제한 슬롯만 새 지원자에게 배정합니다.
  const slots = (
    selection ?? visible.slice(0, 3).map((item) => item.applicationId)
  ).map((applicationId) =>
    visible.some((candidate) => candidate.applicationId === applicationId)
      ? applicationId
      : null,
  );
  const selected = visible
    .filter((candidate) => slots.includes(candidate.applicationId))
    .slice(0, 3);
  const toggle = (applicationId: string, checked: boolean) => {
    const next = slots.map((value) => (value === applicationId ? null : value));
    if (checked) {
      const available = next.indexOf(null);
      if (available >= 0) next[available] = applicationId;
      else if (next.length < 3) next.push(applicationId);
    }
    setSelection(next);
  };
  return (
    <section className="applicant-comparison" aria-label="지원자 평가 비교">
      <div className="comparison-toolbar">
        <div>
          <h4>지원자 비교</h4>
          <span role="status">
            평가 {candidates.length}명 · 표시 {visible.length}명
          </span>
        </div>
        {skills.length > 0 && (
          <details className="comparison-filter">
            <summary>
              <SlidersHorizontal size={16} aria-hidden="true" />
              역량 필터
              {activeSkill && <span className="comparison-filter-dot" />}
            </summary>
            <div>
              <label htmlFor={`${id}-skill`}>등록 역량</label>
              <NativeSelect
                id={`${id}-skill`}
                value={activeSkill}
                onChange={(event) => {
                  setSkill(event.target.value);
                  setSelection(null);
                }}
              >
                <option value="">모든 역량</option>
                {skills.map((code) => (
                  <option key={code} value={code}>
                    {labels.skillLabel(code)}
                  </option>
                ))}
              </NativeSelect>
            </div>
          </details>
        )}
      </div>
      <div className="comparison-plot">
        <div className="comparison-plot-heading">
          <h5>항목별 평가</h5>
          <span>100점 기준</span>
        </div>
        <div className="comparison-legend" aria-label="차트 범례">
          {selected.map((candidate) => (
            <span
              key={candidate.applicationId}
              className={`comparison-legend-item comparison-color-${slots.indexOf(candidate.applicationId) + 1}`}
            >
              <i aria-hidden="true" />
              {candidate.title}
            </span>
          ))}
        </div>
        {selected.length > 0 ? (
          <figure
            aria-label="지원자별 항목 점수 막대그래프"
            className="comparison-chart"
            style={{ height: 180 + selected.length * 64 }}
          >
            <ApplicantChartBoundary>
              <Suspense
                fallback={
                  <div className="comparison-chart-loading" role="status">
                    차트를 준비하고 있어요…
                  </div>
                }
              >
                <ApplicantComparisonChart
                  candidates={selected}
                  colorSlots={selected.map(
                    (candidate) => slots.indexOf(candidate.applicationId) + 1,
                  )}
                />
              </Suspense>
            </ApplicantChartBoundary>
            <figcaption className="sr-only">
              <ul>
                {selected.map((candidate) => (
                  <li key={candidate.applicationId}>
                    {candidate.title}:{' '}
                    {criterionKeys
                      .flatMap((key) =>
                        candidate.assessment.criteria.filter(
                          (criterion) => criterion.key === key,
                        ),
                      )
                      .map(criterionScoreDescription)
                      .join(', ')}
                  </li>
                ))}
              </ul>
            </figcaption>
          </figure>
        ) : (
          <div className="comparison-chart-empty" role="status">
            비교할 지원자를 선택해 주세요.
          </div>
        )}
      </div>
      <div className="comparison-picker-heading">
        <span>비교할 지원자</span>
        <span>최대 3명</span>
      </div>
      <div className="comparison-candidates">
        {visible.map((candidate) => {
          const index = slots.indexOf(candidate.applicationId);
          const chosen = index >= 0;
          return (
            <div
              className={`comparison-candidate${chosen ? ` comparison-color-${index + 1} is-selected` : ''}`}
              key={candidate.applicationId}
            >
              <label>
                <input
                  type="checkbox"
                  checked={chosen}
                  disabled={!chosen && selected.length >= 3}
                  aria-label={`${candidate.title} 비교에 포함`}
                  onChange={(event) =>
                    toggle(candidate.applicationId, event.target.checked)
                  }
                />
                <span className="comparison-check" aria-hidden="true">
                  {chosen && <Check size={14} strokeWidth={2.5} />}
                </span>
                <span className="comparison-candidate-name">
                  {candidate.title}
                </span>
              </label>
              <Link
                to={`/applicants/${encodeURIComponent(candidate.applicationId)}`}
                aria-label={`${candidate.title} 지원서 보기`}
                title="지원서 보기"
              >
                <ArrowUpRight size={18} aria-hidden="true" />
              </Link>
            </div>
          );
        })}
      </div>
    </section>
  );
}
