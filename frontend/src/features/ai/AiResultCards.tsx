/** 검증된 AI 결과를 근거·등록 정보·표시 내 필터·사람 비교로 보여줍니다. */
import { useId, useState } from 'react';
import { Link } from 'react-router';
import {
  CalendarDays,
  ChevronDown,
  ChevronRight,
  Columns2,
  TextSearch,
  Users,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { NativeSelect } from '@/components/ui/native-select';
import { useLabels } from '@/features/catalogs/queries';
import type { Labels } from '@/features/catalogs/labels';
import type { RichResourceCard } from './contract';
import { DemoBadge } from '@/components/common/CommonUi';

type AiDisplayCard = RichResourceCard;
type PersonDetails = Extract<RichResourceCard['details'], { kind: 'person' }>;

function koreanInstant(value: string) {
  return new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).format(Date.parse(value));
}

function experienceText(profile: PersonDetails) {
  return profile.experienceState === 'none'
    ? '관련 경험 없음'
    : profile.experienceState === 'provided'
      ? profile.experienceBody || '미입력'
      : '경험 미입력';
}

export function AiEvidence({ evidence }: { evidence: string[] }) {
  return evidence.length ? (
    <ul className="ai-evidence-list">
      {evidence.map((text, index) => (
        <li key={`${index}-${text}`}>{text}</li>
      ))}
    </ul>
  ) : (
    <p className="ai-result-muted">별도로 제공된 추천 근거가 없어요.</p>
  );
}

export function AiPersonFacts({
  profile,
  labels,
}: {
  profile: PersonDetails;
  labels: Labels;
}) {
  return (
    <dl className="ai-result-facts">
      <div>
        <dt>등록 역량</dt>
        <dd>
          {profile.skillCodes.map(labels.skillLabel).join(' · ') ||
            '역량 미입력'}
        </dd>
      </div>
      <div>
        <dt>관련 경험</dt>
        <dd>{experienceText(profile)}</dd>
      </div>
      <div>
        <dt>주당 시간</dt>
        <dd>
          {profile.weeklyAvailabilityCode
            ? labels.weeklyAvailabilityLabel(profile.weeklyAvailabilityCode)
            : '주당 시간 미입력'}
        </dd>
      </div>
      {profile.introduction && (
        <div>
          <dt>자기소개</dt>
          <dd>{profile.introduction}</dd>
        </div>
      )}
    </dl>
  );
}

function ResourceFacts({
  card,
  labels,
}: {
  card: AiDisplayCard;
  labels: Labels;
}) {
  const details = card.details;
  if (details.kind === 'person')
    return <AiPersonFacts profile={details} labels={labels} />;
  return (
    <dl className="ai-result-facts">
      {details.kind === 'contest' ? (
        <>
          <div>
            <dt>주최</dt>
            <dd>{details.organizer}</dd>
          </div>
          <div>
            <dt>접수 기간</dt>
            <dd>{koreanInstant(details.startsAt)}부터 (한국시간)</dd>
          </div>
          <div>
            <dt>접수 종료 시각</dt>
            <dd>{koreanInstant(details.endsAt)} (한국시간)</dd>
          </div>
          <div>
            <dt>현재 상태</dt>
            <dd>
              {
                {
                  scheduled: '접수 예정',
                  open: '접수 중',
                  closed: '접수 마감',
                }[details.registrationStatus]
              }
            </dd>
          </div>
        </>
      ) : (
        <>
          <div>
            <dt>공모전</dt>
            <dd>{details.contestTitle}</dd>
          </div>
          <div>
            <dt>모집 역할</dt>
            <dd>
              {card.roleCodes.map(labels.roleLabel).join(' · ') ||
                '등록된 역할 없음'}
            </dd>
          </div>
          <div>
            <dt>현재 인원</dt>
            <dd>
              {details.memberCount} / {details.capacity}명 (팀장 포함)
            </dd>
          </div>
          <div>
            <dt>모집 종료 시각</dt>
            <dd>{koreanInstant(details.recruitmentEndsAt)} (한국시간)</dd>
          </div>
          <div>
            <dt>현재 상태</dt>
            <dd>{details.isRecruiting ? '모집 중' : '모집 종료'}</dd>
          </div>
        </>
      )}
    </dl>
  );
}

export function AiResultCards({
  cards,
  returnTo = '/ai',
  getHref,
}: {
  cards: AiDisplayCard[];
  returnTo?: string;
  getHref?: (card: AiDisplayCard) => string;
}) {
  const labels = useLabels();
  const id = useId();
  const [skill, setSkill] = useState('');
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [showComparison, setShowComparison] = useState(false);
  const people = cards.filter(
    (card) => card.kind === 'person' && card.details.kind === 'person',
  );
  const skills: string[] = [
    ...new Set(
      people.flatMap((card) =>
        card.details.kind === 'person' ? card.details.skillCodes : [],
      ),
    ),
  ];
  const currentSkill = skills.includes(skill) ? skill : '';
  const visible = cards.filter(
    (card) =>
      !currentSkill ||
      card.details.kind !== 'person' ||
      card.details.skillCodes.some((code) => code === currentSkill),
  );
  const selected = visible
    .filter(
      (card) => card.kind === 'person' && selectedIds.includes(card.resourceId),
    )
    .slice(0, 3);
  const comparing = showComparison && selected.length >= 2;
  const href = (card: AiDisplayCard) =>
    getHref?.(card) ??
    `/${card.kind === 'person' ? 'people' : `${card.kind}s`}/${encodeURIComponent(card.resourceId)}?from=${encodeURIComponent(returnTo)}`;
  const toggleSelection = (resourceId: string, checked: boolean) => {
    setShowComparison(false);
    const currentIds = selected.map((card) => card.resourceId);
    setSelectedIds(
      checked
        ? [
            ...currentIds.filter((value) => value !== resourceId),
            resourceId,
          ].slice(0, 3)
        : currentIds.filter((value) => value !== resourceId),
    );
  };
  if (!cards.length) return null;
  return (
    <div className="ai-rich-results">
      {people.length > 0 && skills.length > 0 && (
        <div className="ai-result-filter">
          <label htmlFor={`${id}-skill`}>현재 표시된 사람의 등록 역량</label>
          <NativeSelect
            id={`${id}-skill`}
            value={currentSkill}
            onChange={(event) => {
              setSkill(event.target.value);
              setSelectedIds([]);
              setShowComparison(false);
            }}
          >
            <option value="">모든 역량</option>
            {skills.map((code) => (
              <option key={code} value={code}>
                {labels.skillLabel(code)}
              </option>
            ))}
          </NativeSelect>
          <p className="ai-result-muted" role="status">
            현재 표시된 사람 {people.length}명 중{' '}
            {visible.filter((card) => card.kind === 'person').length}명
          </p>
        </div>
      )}
      {people.length >= 2 && (
        <div className="ai-comparison-controls">
          <Button
            type="button"
            variant="outline"
            disabled={selected.length < 2}
            aria-pressed={comparing}
            aria-controls={`${id}-comparison`}
            onClick={() => setShowComparison(!comparing)}
          >
            <Columns2 size={16} aria-hidden="true" />
            {comparing ? '카드로 보기' : `선택한 ${selected.length}명 비교`}
          </Button>
          <span className="ai-result-muted">
            비교할 사람 2~3명을 선택하세요.
          </span>
        </div>
      )}
      {comparing ? (
        <div
          id={`${id}-comparison`}
          className="ai-comparison-scroll"
          role="region"
          aria-label="등록 정보 비교 표"
          tabIndex={0}
        >
          <table className="ai-comparison-table">
            <caption>선택한 사람의 등록 정보 비교</caption>
            <thead>
              <tr>
                <th scope="col">항목</th>
                {selected.map((card) => (
                  <th key={card.resourceId} scope="col">
                    <Link to={href(card)}>{card.title}</Link>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              <tr>
                <th scope="row">희망 역할</th>
                {selected.map((card) => (
                  <td key={card.resourceId}>
                    {card.roleCodes.map(labels.roleLabel).join(' · ') ||
                      '미입력'}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">등록 역량</th>
                {selected.map((card) => (
                  <td key={card.resourceId}>
                    {card.details.kind === 'person'
                      ? card.details.skillCodes
                          .map(labels.skillLabel)
                          .join(' · ') || '미입력'
                      : ''}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">관련 경험</th>
                {selected.map((card) => (
                  <td key={card.resourceId}>
                    {card.details.kind === 'person'
                      ? experienceText(card.details)
                      : ''}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">주당 시간</th>
                {selected.map((card) => (
                  <td key={card.resourceId}>
                    {card.details.kind === 'person' &&
                    card.details.weeklyAvailabilityCode
                      ? labels.weeklyAvailabilityLabel(
                          card.details.weeklyAvailabilityCode,
                        )
                      : '미입력'}
                  </td>
                ))}
              </tr>
              <tr>
                <th scope="row">추천 이유</th>
                {selected.map((card) => (
                  <td key={card.resourceId}>{card.reason}</td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="ai-result-list">
          {visible.map((card) => {
            const person = card.details.kind === 'person';
            const chosen = selected.some(
              (value) => value.resourceId === card.resourceId,
            );
            return (
              <article
                className="ai-result-card"
                aria-label={card.title}
                key={`${card.kind}-${card.resourceId}`}
              >
                <div className="ai-result-heading">
                  <span className="ai-result-avatar" aria-hidden="true">
                    {person ? (
                      card.title.slice(0, 1)
                    ) : card.kind === 'team' ? (
                      <Users size={20} />
                    ) : (
                      <CalendarDays size={20} />
                    )}
                  </span>
                  <Link className="ai-result-title" to={href(card)}>
                    <h3>{card.title}</h3>
                    <ChevronRight size={16} aria-hidden="true" />
                  </Link>
                </div>
                <p className="ai-result-meta">
                  {(person || card.kind === 'team'
                    ? card.roleCodes.map(labels.roleLabel)
                    : card.fieldCodes.map(labels.fieldLabel)
                  ).join(' · ')}
                  <DemoBadge
                    isDemo={card.isDemo}
                    kind={card.kind === 'person' ? 'account' : card.kind}
                  />
                </p>
                {card.details.kind === 'person' &&
                  card.details.skillCodes.length > 0 && (
                    <div className="ai-result-tags" aria-label="등록 역량">
                      {card.details.skillCodes.map((code) => (
                        <span key={code}>{labels.skillLabel(code)}</span>
                      ))}
                    </div>
                  )}
                <p className="ai-result-reason">{card.reason}</p>
                <details className="ai-result-disclosure">
                  <summary>
                    <TextSearch size={16} aria-hidden="true" />
                    <span>추천 근거와 등록 정보</span>
                    <ChevronDown
                      size={16}
                      className="ai-disclosure-chevron"
                      aria-hidden="true"
                    />
                  </summary>
                  <div className="ai-result-expanded">
                    <AiEvidence evidence={card.evidence} />
                    <ResourceFacts card={card} labels={labels} />
                  </div>
                </details>
                {person && people.length >= 2 && (
                  <label className="ai-compare-choice">
                    <Checkbox
                      checked={chosen}
                      disabled={!chosen && selected.length >= 3}
                      onCheckedChange={(checked) =>
                        toggleSelection(card.resourceId, checked === true)
                      }
                      aria-label={`${card.title} 비교에 포함`}
                    />
                    <span>비교에 포함</span>
                  </label>
                )}
              </article>
            );
          })}
        </div>
      )}
      {people.length > 0 && (
        <p className="ai-result-footnote">
          주당 시간은 모든 프로젝트를 합친 자기신고 참고값이에요. 실제 활동
          일정은 별도로 조율해 주세요.
        </p>
      )}
    </div>
  );
}
