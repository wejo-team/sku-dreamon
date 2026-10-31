/** 검증된 답변의 설명과 등록 정보를 사람이 읽을 수 있는 복사 텍스트로 만듭니다. */
import type { Labels } from '@/features/catalogs/labels';
import type { ChatResult, ResourceCard } from './contract';

const moment = (value: string) =>
  new Intl.DateTimeFormat('ko-KR', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Seoul',
  }).format(new Date(value));

function cardFacts(card: ResourceCard, labels: Labels) {
  if (!('details' in card)) return [];
  const facts = [
    `분야: ${card.fieldCodes.map(labels.fieldLabel).join(' · ') || '미입력'}`,
  ];
  if (card.roleCodes.length)
    facts.push(`역할: ${card.roleCodes.map(labels.roleLabel).join(' · ')}`);
  const details = card.details;
  if (details.kind === 'person') {
    facts.push(
      `등록 역량: ${details.skillCodes.map(labels.skillLabel).join(' · ') || '미입력'}`,
    );
    facts.push(
      `관련 경험: ${details.experienceState === 'none' ? '관련 경험 없음' : details.experienceBody || '경험 미입력'}`,
    );
    facts.push(
      `주당 시간: ${details.weeklyAvailabilityCode ? labels.weeklyAvailabilityLabel(details.weeklyAvailabilityCode) : '미입력'} (모든 프로젝트 합산 참고값)`,
    );
    if (details.introduction) facts.push(`자기소개: ${details.introduction}`);
  } else if (details.kind === 'team') {
    facts.push(
      `공모전: ${details.contestTitle}`,
      `모집 인원: ${details.memberCount}/${details.capacity}명 (팀장 포함)`,
      `모집 종료 시각: ${moment(details.recruitmentEndsAt)} (한국 시간)`,
    );
  } else {
    facts.push(
      `주최: ${details.organizer}`,
      `접수 종료 시각: ${moment(details.endsAt)} (한국 시간)`,
    );
  }
  return facts;
}

export function chatClipboardText(result: ChatResult, labels: Labels) {
  return [
    result.answer,
    ...result.cards.map((card) =>
      [
        card.title,
        card.reason,
        ...cardFacts(card, labels),
        ...('evidence' in card ? card.evidence : []),
      ].join('\n'),
    ),
  ].join('\n\n');
}
