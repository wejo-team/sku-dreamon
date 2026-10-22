/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ReferencePages.tsx - 로컬 링크 목적지 원본
 * 2. docs/design/screens.md - 「재현 경로」 실제 기관·개인 사이트를 대신하는 /reference/notices, /reference/portfolios
 * 3. docs/design/handoff.md - 레퍼런스의 외부 링크를 실제 공고 근거로 사용하지 않음
 */

import { useParams } from 'react-router';
import { archivedContest, contests } from '@/features/demo/data';
import { memberLimitLabel } from '@/features/demo/contest-state';
import { BackLink, EmptyState, PageIntro } from '@/components/common/CommonUi';

// Local destinations keep fixture links reviewable without inventing organizer URLs.
// [출처 2, 3] 공고 원문 자리 표시
export function ReferenceNoticePage() {
  const { contestId } = useParams();
  const contest = [...contests, archivedContest].find(
    (item) => item.id === contestId,
  );
  if (!contest)
    return (
      <EmptyState
        title="공고를 찾을 수 없어요"
        description="공모전 목록에서 다시 확인해 주세요."
      />
    );
  return (
    <article className="preview-panel preview-stack">
      <BackLink to={`/contests/${contest.id}`}>공모전으로</BackLink>
      <PageIntro title={contest.title} description={contest.organizer} />
      <p>{contest.description}</p>
      <dl className="preview-detail-facts">
        <div>
          <dt>접수 기간</dt>
          <dd>
            {contest.startsAt} ~ {contest.deadline}
          </dd>
        </div>
        <div>
          <dt>참가 대상</dt>
          <dd>{contest.audienceOriginal}</dd>
        </div>
        <div>
          <dt>참가 인원</dt>
          <dd>{memberLimitLabel(contest)}</dd>
        </div>
        <div>
          <dt>제출물</dt>
          <dd>{contest.deliverables.join(' · ') || '주최 기관 문의'}</dd>
        </div>
      </dl>
    </article>
  );
}

// [출처 2] 포트폴리오 자리 표시
export function ReferencePortfolioPage() {
  const { personId } = useParams();
  if (personId !== 'seoyeon')
    return (
      <EmptyState
        title="페이지를 찾을 수 없어요"
        description="링크를 다시 확인해 주세요."
      />
    );
  return (
    <article className="preview-panel preview-stack">
      <PageIntro title="김서연의 프로젝트" description="개발 · UI/UX 디자인" />
      <h2>그린 캠퍼스</h2>
      <p>
        교내 분리배출 정보를 쉽게 찾는 모바일 웹 프로젝트입니다. 화면 설계와
        프론트엔드 개발에 참여했습니다.
      </p>
      <p>작은 행동이 더 나은 일상을 만드는 서비스를 만들고 있어요.</p>
    </article>
  );
}
