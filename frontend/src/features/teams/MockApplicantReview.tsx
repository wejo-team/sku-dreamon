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
import type { ApplicantAssessment as Assessment } from '@/features/ai/contract';
import type { Application } from '@/features/applications/api';
import type { Profile } from '@/features/profiles/api';
import type { Labels } from '@/features/catalogs/labels';
import { useLabels } from '@/features/catalogs/queries';
import {
  ApplicantReviewContext,
  type ApplicantReviewFacts,
} from '@/features/demo/applicant-review-state';
import { ApplicantAssessment } from './ApplicantAssessment';

type Review = ApplicantReviewFacts;

// 고정 시연 점수이며 모델의 평가 기준이 아닙니다. 없는 자료에는 점수를 만들지 않습니다.
function demoAssessment(
  application: Application,
  profile: Profile,
  { roleLabel, skillLabel }: Labels,
): Assessment {
  const hasExperience =
    profile.experienceState === 'provided' && !!profile.experienceBody?.trim();
  const noExperience = profile.experienceState === 'none';
  return {
    criteria: [
      {
        key: 'role',
        score: application.roleCode ? 85 : null,
        informationStatus: application.roleCode ? 'sufficient' : 'insufficient',
        summary: '등록한 지원 역할의 시연 점수입니다.',
        evidence: application.roleCode
          ? [
              {
                source: 'application.role',
                text: roleLabel(application.roleCode),
              },
            ]
          : [],
      },
      {
        key: 'skills',
        score: profile.skillCodes.length ? 75 : null,
        informationStatus: profile.skillCodes.length
          ? 'sufficient'
          : 'insufficient',
        summary: '등록한 역량의 시연 점수입니다.',
        evidence: profile.skillCodes.slice(0, 6).map((code) => ({
          source: 'profile.skillCodes',
          text: skillLabel(code),
        })),
      },
      {
        key: 'experience',
        score: noExperience ? 20 : hasExperience ? 65 : null,
        informationStatus:
          noExperience || hasExperience ? 'sufficient' : 'insufficient',
        summary: '경험 없음과 미입력을 구별하는 시연 점수입니다.',
        evidence: noExperience
          ? [{ source: 'profile.experienceState', text: '관련 경험 없음' }]
          : hasExperience
            ? [
                {
                  source: 'profile.experienceBody',
                  text: profile.experienceBody!,
                },
              ]
            : [],
      },
      {
        key: 'availability',
        // 전체 프로젝트 합산 시간만으로 팀 참여 시간의 적합성을 채점하지 않습니다.
        score: null,
        informationStatus: 'insufficient',
        summary: '팀에 배정할 시간을 판단할 자료가 없습니다.',
        evidence: [],
      },
    ],
    questions: [],
  };
}

// 원문은 화면에 반복하지 않고 검토 이후 등록 정보 변경 여부에만 사용합니다.
function reviewFacts(
  application: Application,
  profile: Profile,
  labels: Labels,
): Review {
  const { fieldLabel, roleLabel, skillLabel, weeklyAvailabilityLabel } = labels;
  const list = (codes: string[], label: (code: string) => string) =>
    codes.map(label).join(' · ') || '미입력';
  return {
    assessment: demoAssessment(application, profile, labels),
    facts: [
      { label: '지원 역할', value: roleLabel(application.roleCode) },
      { label: '현재 희망 역할', value: list(profile.roleCodes, roleLabel) },
      { label: '관심 분야', value: list(profile.fieldCodes, fieldLabel) },
      { label: '등록한 역량', value: list(profile.skillCodes, skillLabel) },
      {
        label: '관련 경험',
        value:
          profile.experienceState === 'none'
            ? '관련 경험 없음'
            : profile.experienceBody || '미입력',
      },
      {
        label: '주당 참여 가능 시간',
        value: profile.weeklyAvailabilityCode
          ? weeklyAvailabilityLabel(profile.weeklyAvailabilityCode)
          : '미입력',
      },
      { label: '팀에 전한 말', value: application.message || '미입력' },
    ],
  };
}

// [출처 2, 3] 권한이 있을 때만 결과·요청 UI 표시(모의 응답)
export function MockApplicantReview({
  application: applicant,
  profile,
  mayReviewExistingApplication,
}: {
  application: Application;
  profile: Profile;
  mayReviewExistingApplication: boolean;
}) {
  const [params] = useSearchParams();
  const labels = useLabels();
  const session = useContext(ApplicantReviewContext);
  const [localResult, setLocalResult] = useState<Review | null>(null);
  const result = session?.results[applicant.id] ?? localResult;
  const profileChanged =
    result !== null &&
    JSON.stringify(result) !==
      JSON.stringify(reviewFacts(applicant, profile, labels));
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState(false);
  const failedOnce = useRef(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const latest = useRef({
    applicant,
    profile,
    labels,
    mayReviewExistingApplication,
  });
  const isSelectionCandidate = ['submitted', 'reviewing'].includes(
    applicant.status,
  );

  useEffect(() => {
    latest.current = {
      applicant,
      profile,
      labels,
      mayReviewExistingApplication,
    };
  }, [applicant, profile, labels, mayReviewExistingApplication]);
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
      const next = reviewFacts(
        current.applicant,
        current.profile,
        current.labels,
      );
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
        네 가지 항목의 시연 점수를 한눈에 확인해요.
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
          {applicant.status === 'canceled'
            ? '취소된 지원은 새 선발 후보 추천에서 제외돼요.'
            : applicant.status === 'discarded'
              ? '다른 팀에서 선발되어 폐기된 지원은 새 선발 후보 추천에서 제외돼요.'
              : '결정이 끝난 지원은 새 선발 후보 추천에서 제외돼요.'}
        </p>
      )}
    </section>
  );
}
