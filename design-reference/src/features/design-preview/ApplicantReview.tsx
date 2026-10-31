/** 로컬 등록 사실을 구조화된 평가 시각화로 보여주는 독립 디자인 화면입니다. */
import { useContext, useEffect, useRef, useState } from 'react';
import { LoaderCircle, RotateCcw, Sparkles } from 'lucide-react';
import { useSearchParams } from 'react-router';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import type { Applicant, Person } from './data';
import {
  ApplicantReviewContext,
  type ApplicantReviewResult,
} from './applicant-review-state';

import { ApplicantAssessment } from './ApplicantAssessment';
import { createApplicantAssessment } from './applicant-assessment';

type Review = ApplicantReviewResult;

// 현재 등록 정보만 인용하는 로컬 예시이며 실제 모델의 평가를 대신하지 않습니다.
function reviewFacts(applicant: Applicant, profile: Person): Review {
  return {
    assessment: createApplicantAssessment(applicant, profile),
    facts: [
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
    ],
  };
}

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

  // 상위 화면이 현재 팀장·지원 관계를 검사합니다. 종결된 지원도 기존 검토는 허용합니다.
  if (!mayReviewExistingApplication) return null;

  return (
    <section
      className="preview-panel preview-stack"
      aria-labelledby="applicant-recommendation-title"
    >
      <div className="preview-row">
        <Sparkles size={20} aria-hidden="true" />
        <h2 id="applicant-recommendation-title">AI 검토 도움</h2>
        <span className="preview-muted">시연 점수</span>
      </div>
      <p className="preview-muted">
        네 가지 항목의 평가 점수를 한눈에 확인해요.
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
          <ApplicantAssessment assessment={result.assessment} />
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
