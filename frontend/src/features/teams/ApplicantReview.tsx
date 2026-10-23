/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ApplicantReview.tsx - 지원자 AI 검토 원본
 * 2. docs/specs/team-recruitment.md#recruitment-review - 최신 프로필 기반 검토 요청·실패·재시도, 마감 후에도 허용
 * 3. docs/specs/matching.md#open-questions - 실제 모델 입력 필드·보존은 미정
 */

import { useContext, useEffect, useRef, useState } from 'react';
import { LoaderCircle, RotateCcw, Sparkles } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type { Applicant, Person } from '@/features/demo/data';
import {
  ApplicantReviewContext,
  type ApplicantReviewResult,
} from '@/features/demo/applicant-review-state';

type Review = ApplicantReviewResult;

// Local reference output deliberately quotes current registered information;
// it is not a scoring model or a decision about a production LLM architecture.
function reviewFacts(applicant: Applicant, profile: Person): Review {
  return [
    { label: '지원 역할', value: applicant.role },
    { label: '현재 희망 역할', value: profile.roles.join(' · ') || '미입력' },
    { label: '관심 분야', value: profile.interests?.join(' · ') || '미입력' },
    { label: '등록한 역량', value: profile.skills?.join(' · ') || '미입력' },
    {
      label: '관련 경험',
      value:
        profile.experienceState === 'none'
          ? '관련 경험 없음'
          : profile.experience || '미입력',
    },
    { label: '주당 참여 가능 시간', value: profile.availability || '미입력' },
    { label: '팀에 전한 말', value: applicant.message || '미입력' },
  ];
}

// [출처 2, 3] 권한이 있을 때만 결과·요청 UI 표시(모의 응답)
export function ApplicantReview({
  applicant,
  profile,
  mayReviewExistingApplication,
}: {
  applicant: Applicant;
  profile: Person;
  mayReviewExistingApplication: boolean;
}) {
  const [params] = useSearchParams();
  const session = useContext(ApplicantReviewContext);
  const [localResult, setLocalResult] = useState<Review | null>(null);
  const result = session?.results[applicant.id] ?? localResult;
  const profileChanged =
    result !== null &&
    JSON.stringify(result) !== JSON.stringify(reviewFacts(applicant, profile));
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const failedOnce = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({ applicant, profile, mayReviewExistingApplication });
  const isSelectionCandidate = ['지원완료', '검토중'].includes(
    applicant.status,
  );

  useEffect(() => {
    latest.current = { applicant, profile, mayReviewExistingApplication };
  }, [applicant, profile, mayReviewExistingApplication]);
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  function requestReview() {
    if (!mayReviewExistingApplication || timer.current) return;
    setPending(true);
    setFailed(false);
    timer.current = setTimeout(() => {
      timer.current = null;
      setPending(false);
      const current = latest.current;
      if (!current.mayReviewExistingApplication) return;
      if (params.get('scenario') === 'review-error' && !failedOnce.current) {
        failedOnce.current = true;
        setFailed(true);
        return;
      }
      const next = reviewFacts(current.applicant, current.profile);
      if (session) session.save(current.applicant.id, next);
      else setLocalResult(next);
    }, 350);
  }

  // The parent rechecks the current signed-in leader and application relation.
  // A terminal application status removes candidacy, not this review permission.
  if (!mayReviewExistingApplication) return null;

  return (
    <section
      className="preview-panel preview-stack"
      aria-labelledby="applicant-recommendation-title"
    >
      <div className="preview-row">
        <Sparkles size={20} aria-hidden="true" />
        <h2 id="applicant-recommendation-title">AI 검토 도움</h2>
      </div>
      <p className="preview-muted">
        현재 지원서와 프로필로 검토해요. 모집이 마감되거나 정원이 차도 검토할 수
        있어요.
      </p>
      {result && (
        <div role="status" className="preview-stack">
          {profileChanged && (
            <Alert role="note">
              <AlertDescription>
                검토 이후 프로필 정보가 변경됐어요. 아래는 이전 검토 결과예요.
                {' 최신 정보로 다시 검토해 주세요.'}
              </AlertDescription>
            </Alert>
          )}
          <p>지원서와 현재 프로필에 등록된 정보예요.</p>
          <dl className="workspace-detail-facts">
            {result.map((fact) => (
              <div key={fact.label}>
                <dt>{fact.label}</dt>
                <dd className="whitespace-pre-wrap break-words">
                  {fact.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="preview-muted">
            주당 시간은 모든 프로젝트를 합친 참고값이에요. 실제 일정이나 참가
            자격을 보장하지 않아요. 이 검토로 지원 상태가 바뀌지는 않아요.
          </p>
        </div>
      )}
      {failed && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>
            검토 결과를 가져오지 못했어요. 다시 요청해 주세요.
          </AlertDescription>
        </Alert>
      )}
      <Button
        variant="outline"
        onClick={requestReview}
        disabled={pending}
        aria-busy={pending}
      >
        {pending ? (
          <LoaderCircle size={18} className="animate-spin" aria-hidden="true" />
        ) : result || failed ? (
          <RotateCcw size={18} aria-hidden="true" />
        ) : (
          <Sparkles size={18} aria-hidden="true" />
        )}
        {pending
          ? '검토하는 중…'
          : failed
            ? '검토 다시 시도'
            : result
              ? '다시 검토하기'
              : 'AI 검토 요청'}
      </Button>
      {!isSelectionCandidate && (
        <p className="preview-muted">
          {applicant.status === '지원취소'
            ? '취소된 지원은 새 선발 후보 추천에서 제외돼요.'
            : applicant.status === '폐기'
              ? '다른 팀에서 선발되어 폐기된 지원은 새 선발 후보 추천에서 제외돼요.'
              : '결정이 끝난 지원은 새 선발 후보 추천에서 제외돼요.'}
        </p>
      )}
    </section>
  );
}
