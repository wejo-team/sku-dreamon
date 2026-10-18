import { ExternalLink } from 'lucide-react';
import type { Person } from './data';
import { Badge } from './PreviewUi';

function portfolioUrl(value?: string) {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : null;
  } catch {
    return null;
  }
}

export function ProfileDetails({
  profile,
}: {
  profile: Omit<Person, 'id' | 'name'>;
}) {
  const academics = [
    ['학적 상태', profile.academicStatus],
    ['학년', profile.grade],
    ['단과대학', profile.college],
    ['학과', profile.department],
    ['전공', profile.major],
  ].filter(([, value]) => value);
  const portfolio = portfolioUrl(profile.portfolio);
  const experience =
    profile.experienceState === 'none' ? '관련 경험 없음' : profile.experience;

  return (
    <dl className="preview-profile-facts">
      <div>
        <dt>희망 역할</dt>
        <dd className="preview-row">
          {profile.roles.map((role) => (
            <Badge key={role}>{role}</Badge>
          ))}
        </dd>
      </div>
      {academics.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd className="preview-info-value">{value}</dd>
        </div>
      ))}
      {profile.skills !== undefined && (
        <div>
          <dt>보유 역량</dt>
          <dd>
            {profile.skills.length ? (
              <div className="preview-row">
                {profile.skills.map((skill) => (
                  <Badge key={skill}>{skill}</Badge>
                ))}
              </div>
            ) : (
              <p className="preview-muted">아직 입력하지 않았어요.</p>
            )}
            {profile.skillOther && (
              <p className="preview-info-copy">{profile.skillOther}</p>
            )}
          </dd>
        </div>
      )}
      {profile.interests !== undefined && (
        <div>
          <dt>관심 분야</dt>
          <dd>
            <div className="preview-row">
              {profile.interests.map((interest) => (
                <Badge key={interest}>{interest}</Badge>
              ))}
            </div>
            {profile.interestOther && (
              <p className="preview-info-copy">{profile.interestOther}</p>
            )}
          </dd>
        </div>
      )}
      {experience !== undefined && (
        <div>
          <dt>경험</dt>
          <dd className="preview-info-copy">
            {experience || '아직 입력하지 않았어요.'}
          </dd>
        </div>
      )}
      {profile.intro !== undefined && (
        <div>
          <dt>자기소개</dt>
          <dd className="preview-info-copy">
            {profile.intro || '아직 입력하지 않았어요.'}
          </dd>
        </div>
      )}
      {profile.availability !== undefined && (
        <div>
          <dt>활동 가능 시간</dt>
          <dd className="preview-info-copy">
            {profile.availability || '아직 시간을 선택하지 않았어요.'}
          </dd>
        </div>
      )}
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
              {profile.portfolioTitle || '포트폴리오 열기'}
              <ExternalLink size={16} aria-hidden="true" />
              <span className="sr-only"> (새 창)</span>
            </a>
          </dd>
        </div>
      )}
    </dl>
  );
}
