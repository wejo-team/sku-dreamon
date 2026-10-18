import { useParams } from 'react-router';
import { archivedContest, contests, previewPath } from './data';
import { BackLink, EmptyState, PageIntro } from './PreviewUi';

// Local destinations keep fixture links reviewable without inventing organizer URLs.
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
      <BackLink to={previewPath(`/contests/${contest.id}`)}>
        공모전으로
      </BackLink>
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
          <dd>{contest.audience}</dd>
        </div>
        <div>
          <dt>참가 방식</dt>
          <dd>{contest.participation === 'individual' ? '개인' : '팀'}</dd>
        </div>
        <div>
          <dt>제출물</dt>
          <dd>{contest.deliverables.join(' · ') || '주최 기관 문의'}</dd>
        </div>
      </dl>
    </article>
  );
}

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
