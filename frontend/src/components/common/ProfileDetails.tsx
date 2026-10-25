/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ProfileDetails.tsx - 프로필 등록 항목 원본
 * 2. docs/design/screens.md - 공개 사람 상세·본인 미리보기·지원자 상세가 같은 정보 계층 사용
 * 3. docs/design/tokens.md - 키 13px·보조색, 값 16px·600 녹색, 긴 문단 16px·1.7
 * 4. docs/specs/profile.md#fields - 학사·관심·역량·경험·자기소개·주당 시간·포트폴리오
 */

import { ExternalLink } from 'lucide-react';
import type { Profile } from '@/features/profiles/api';
import { Badge } from '@/components/common/CommonUi';
import {
  academicPath,
  academicStatusLabel,
  fieldLabel,
  gradeLabel,
  roleLabel,
  skillLabel,
  weeklyAvailabilityLabel,
} from '@/features/demo/labels';
import { normalizeWebUrl } from '@/features/demo/profile-fields';

// 학사 경로 계층별 표시 이름(단과대학 → 학부·학과 → 전공)
const academicLevels = ['단과대학', '학과', '전공'];

// [출처 2, 3, 4] 등록 항목만 표시하고 인증 정보·미수집 연락처는 추가하지 않음
export function ProfileDetails({ profile }: { profile: Profile }) {
  const academics = [
    [
      '학적 상태',
      profile.academicStatusCode &&
        academicStatusLabel(profile.academicStatusCode),
    ],
    ['학년', profile.gradeCode && gradeLabel(profile.gradeCode)],
    ...academicPath(profile.academicUnitId).map(
      (unit, index) => [academicLevels[index] ?? '소속', unit.name] as const,
    ),
  ].filter(([, value]) => value) as [string, string][];
  // [출처 4] 저장·공개와 같은 기준으로 링크를 판단
  const portfolio = profile.portfolio
    ? normalizeWebUrl(profile.portfolio.url) || null
    : null;
  const experience =
    profile.experienceState === 'none'
      ? '관련 경험 없음'
      : (profile.experienceBody ?? '');

  return (
    <dl className="preview-profile-facts">
      <div>
        <dt>희망 역할</dt>
        <dd className="preview-row">
          {profile.roleCodes.map((code) => (
            <Badge key={code}>{roleLabel(code)}</Badge>
          ))}
        </dd>
      </div>
      {academics.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className="preview-info-value">{value}</dd>
        </div>
      ))}
      <div>
        <dt>보유 역량</dt>
        <dd>
          {profile.skillCodes.length ? (
            <div className="preview-row">
              {profile.skillCodes.map((code) => (
                <Badge key={code}>{skillLabel(code)}</Badge>
              ))}
            </div>
          ) : (
            <p className="preview-muted">아직 입력하지 않았어요.</p>
          )}
        </dd>
      </div>
      <div>
        <dt>관심 분야</dt>
        <dd>
          <div className="preview-row">
            {profile.fieldCodes.map((code) => (
              <Badge key={code}>{fieldLabel(code)}</Badge>
            ))}
          </div>
        </dd>
      </div>
      <div>
        <dt>경험</dt>
        <dd className="preview-info-copy">
          {experience || '아직 입력하지 않았어요.'}
        </dd>
      </div>
      <div>
        <dt>자기소개</dt>
        <dd className="preview-info-copy">
          {profile.introduction || '아직 입력하지 않았어요.'}
        </dd>
      </div>
      <div>
        <dt>주당 참여 가능 시간</dt>
        <dd className="preview-info-copy">
          {profile.weeklyAvailabilityCode
            ? weeklyAvailabilityLabel(profile.weeklyAvailabilityCode)
            : '미입력'}
          <p className="preview-muted">
            모든 참여 프로젝트를 합산한 예상 시간으로, 팀별 약속이나 남은 시간이
            아니에요.
          </p>
        </dd>
      </div>
      {portfolio && (
        <div>
          <dt>포트폴리오</dt>
          <dd>
            <a
              className="preview-text-link"
              href={portfolio}
              target="_blank"
              rel="noreferrer"
            >
              {profile.portfolio?.title || '포트폴리오 열기'}
              <ExternalLink size={16} aria-hidden="true" />
              <span className="sr-only"> (새 창)</span>
            </a>
          </dd>
        </div>
      )}
    </dl>
  );
}
