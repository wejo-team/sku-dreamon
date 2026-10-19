import {
  CalendarDays,
  ChevronRight,
  Search,
  ArrowRight,
  Sparkles,
  Plus,
  RotateCcw,
  Users,
  X,
} from 'lucide-react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import {
  contests,
  archivedContest,
  people,
  previewPath,
  getPublicProfile,
} from './data';
import { usePreview } from './preview-context';
import {
  contestBadgeLabel,
  contestDaysLeft,
  contestDeadline,
  contestStatus,
  deadlineLabel,
  deadlineNotice,
  isContestOpen,
  memberLimitLabel,
} from './contest-state';
import { recruitmentIssue } from './team-state';
import { ContestCover } from './ContestCover';
import { ExploreFilters } from './ExploreFilters';
import { ProfileDetails } from './ProfileDetails';
import { ListPagination } from './ListPagination';
import { useListPage } from './use-list-page';
import { TeamCard } from './TeamCard';
import {
  ActionLink,
  Avatar,
  BackLink,
  Badge,
  EmptyState,
  Notice,
  PageIntro,
  SchoolVerificationBadge,
} from './PreviewUi';

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const { teams, profile, signedIn } = usePreview();
  const mine = signedIn ? getPublicProfile(profile) : null;
  const visiblePeople = signedIn ? (mine ? [...people, mine] : people) : [];
  const location = useLocation();
  const tab =
    params.get('tab') === 'teams'
      ? 'teams'
      : params.get('tab') === 'people'
        ? 'people'
        : 'contests';
  const q = params.get('q') ?? '';
  const category = params.get('category') ?? '';
  const role = params.get('role') ?? '';
  const sort = params.get('sort') ?? 'default';
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.delete('page');
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: key === 'q' });
  };
  const from = encodeURIComponent(location.pathname + location.search);
  const includes = (text: string) =>
    text.toLocaleLowerCase().includes(q.trim().toLocaleLowerCase());
  const matchedContests = contests.filter(
    (item) =>
      includes(`${item.title} ${item.organizer} ${item.interests.join(' ')}`) &&
      (!category || item.interests.includes(category)),
  );
  if (sort === 'deadline')
    matchedContests.sort((a, b) => contestDeadline(a) - contestDeadline(b));
  const matchedTeams = teams.filter(
    (item) =>
      includes(
        `${item.name} ${item.summary} ${item.roles.join(' ')} ${contests.find((contest) => contest.id === item.contestId)?.title}`,
      ) &&
      (!role || item.roles.includes(role)) &&
      (params.get('open') !== 'true' || !recruitmentIssue(item)) &&
      (!params.get('contest') || item.contestId === params.get('contest')),
  );
  const matchedPeople = visiblePeople.filter(
    (item) =>
      includes(
        [
          item.name,
          ...item.roles,
          ...(item.interests ?? []),
          ...(item.skills ?? []),
          item.academicStatus,
          item.grade,
          item.college,
          item.department,
          item.major,
          item.intro,
          item.experience,
          item.availability,
          item.portfolioTitle,
          item.portfolio,
        ].join(' '),
      ) &&
      (!role || item.roles.includes(role)),
  );
  const count =
    tab === 'contests'
      ? matchedContests.length
      : tab === 'teams'
        ? matchedTeams.length
        : matchedPeople.length;
  const { page, totalPages, start, end, hrefForPage, headingRef } =
    useListPage(count);
  const reset = () => setParams(tab === 'contests' ? {} : { tab });
  const contestContext = contests.find(
    (item) => item.id === params.get('contest'),
  );
  return (
    <section className="preview-explore" aria-label="탐색">
      <h1 className="sr-only">탐색</h1>
      <nav className="preview-tabs" aria-label="탐색 종류">
        {[
          ['contests', '공모전'],
          ['teams', '팀'],
          ['people', '사람'],
        ].map(([value, label]) => (
          <Link
            key={value}
            to={previewPath(
              value === 'contests' ? '/explore' : `/explore?tab=${value}`,
            )}
            aria-current={tab === value ? 'page' : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className="preview-search">
        <Search size={20} aria-hidden="true" />
        <Input
          aria-label="탐색 검색"
          placeholder={
            tab === 'contests'
              ? '공모전 검색'
              : tab === 'teams'
                ? '팀 이름, 키워드 검색'
                : '이름, 역할, 관심 분야 검색'
          }
          value={q}
          onChange={(event) => update('q', event.target.value)}
        />
        {q && (
          <Button
            variant="ghost"
            aria-label="검색어 지우기"
            onClick={() => update('q', '')}
          >
            <X size={18} aria-hidden="true" />
          </Button>
        )}
        <Button
          asChild
          variant="outline"
          className="preview-compact-action preview-ai-shortcut"
        >
          <Link
            to={previewPath('/ai')}
            aria-label="AI에게 추천 받기"
            title="AI에게 추천 받기"
          >
            <Sparkles size={20} aria-hidden="true" />
          </Link>
        </Button>
      </div>
      <div className="preview-filters">
        <ExploreFilters
          key={tab}
          kind={tab}
          value={tab === 'contests' ? category : role}
          onlyOpen={params.get('open') === 'true'}
          onApply={(value, onlyOpen) => {
            const next = new URLSearchParams(params);
            next.delete('page');
            const key = tab === 'contests' ? 'category' : 'role';
            if (value) next.set(key, value);
            else next.delete(key);
            if (tab === 'teams' && onlyOpen) next.set('open', 'true');
            else next.delete('open');
            setParams(next);
          }}
        />
        {tab === 'contests' && (
          <div className="preview-filter-control preview-sort">
            <Label className="sr-only" htmlFor="explore-sort">
              정렬
            </Label>
            <NativeSelect
              id="explore-sort"
              value={sort}
              onChange={(event) => update('sort', event.target.value)}
            >
              <option value="default">등록순</option>
              <option value="deadline">마감 임박순</option>
            </NativeSelect>
          </div>
        )}
        {(q ||
          category ||
          role ||
          sort !== 'default' ||
          params.get('open') ||
          contestContext) && (
          <Button
            variant="outline"
            className="preview-compact-action"
            aria-label="검색 조건 초기화"
            title="검색 조건 초기화"
            onClick={reset}
          >
            <RotateCcw size={18} aria-hidden="true" />
          </Button>
        )}
      </div>
      {contestContext && tab === 'teams' && (
        <Notice>{contestContext.title}에 함께 도전하는 팀이에요.</Notice>
      )}
      <div className="preview-results-heading">
        <h2 ref={headingRef} tabIndex={-1}>
          {tab === 'contests'
            ? '공모전 둘러보기'
            : tab === 'teams'
              ? '함께 도전하는 팀'
              : '함께할 사람'}
        </h2>
        {(tab !== 'people' || signedIn) && (
          <span className="preview-result-count" role="status">
            <span className="sr-only">검색 결과 </span>
            {count}
            <span className="sr-only">개</span>
          </span>
        )}
        {tab === 'teams' && (
          <Link className="preview-text-link" to={previewPath('/teams/new')}>
            팀 만들기
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        )}
      </div>
      {tab === 'people' && !signedIn ? (
        <EmptyState
          title="로그인하고 함께할 사람을 찾아보세요"
          description="공개에 동의한 사람들의 프로필을 확인할 수 있어요."
        >
          <ActionLink
            to={previewPath(
              '/login?returnTo=' +
                encodeURIComponent(previewPath('/explore?tab=people')),
            )}
          >
            로그인하기
          </ActionLink>
        </EmptyState>
      ) : !count ? (
        <EmptyState
          title="검색 결과가 없어요"
          description="검색어를 바꾸거나 필터를 줄여보세요."
        >
          <Button onClick={reset} className="preview-button">
            검색 조건 초기화
          </Button>
        </EmptyState>
      ) : (
        <div
          className={`preview-grid preview-explore-grid preview-explore-grid--${tab}`}
        >
          {tab === 'contests' &&
            matchedContests.slice(start, end).map((item, index) => (
              <Link
                className="preview-card preview-contest-card"
                key={item.id}
                to={previewPath(`/contests/${item.id}?from=${from}`)}
              >
                <div className="preview-contest-cover">
                  <ContestCover
                    src={item.cover}
                    loading={index === 0 ? 'eager' : 'lazy'}
                  />
                  <span
                    className={`preview-deadline ${isContestOpen(item) && contestDaysLeft(item) <= 7 ? 'preview-deadline--soon' : ''}`}
                  >
                    {contestBadgeLabel(item)}
                  </span>
                </div>
                <div className="preview-contest-copy">
                  <h3>{item.title}</h3>
                  <div className="preview-row">
                    {item.interests.map((interest) => (
                      <Badge key={interest}>{interest}</Badge>
                    ))}
                  </div>
                  <p className="preview-muted">{item.organizer}</p>
                  <span className="preview-contest-teams">
                    <Users size={16} aria-hidden="true" />
                    <span className="sr-only">연결된 팀 </span>
                    {teams.filter((team) => team.contestId === item.id).length}
                    <span className="sr-only">개</span>
                  </span>
                </div>
              </Link>
            ))}
          {tab === 'teams' &&
            matchedTeams
              .slice(start, end)
              .map((item) => (
                <TeamCard
                  key={item.id}
                  team={item}
                  to={previewPath(`/teams/${item.id}?from=${from}`)}
                />
              ))}
          {tab === 'people' &&
            matchedPeople.slice(start, end).map((item) => (
              <Link
                className="preview-card preview-person-card"
                key={item.id}
                to={previewPath(`/people/${item.id}?from=${from}`)}
              >
                <div className="preview-row">
                  <Avatar
                    name={item.name}
                    personId={item.id}
                    avatarId={item.avatarId}
                  />
                  <div>
                    <h3>{item.name}</h3>
                    <p className="preview-muted">{item.roles.join(' · ')}</p>
                  </div>
                  <ChevronRight
                    className="preview-person-arrow"
                    size={20}
                    aria-hidden="true"
                  />
                </div>
                <div className="preview-row">
                  {(item.interests ?? []).map((value) => (
                    <Badge key={value}>{value}</Badge>
                  ))}
                </div>
              </Link>
            ))}
        </div>
      )}
      {count > 0 && (
        <ListPagination
          page={page}
          totalPages={totalPages}
          hrefForPage={hrefForPage}
          label="탐색 결과 페이지"
        />
      )}
    </section>
  );
}

export function ContestPage() {
  const { contestId } = useParams();
  const [params] = useSearchParams();
  const { teams } = usePreview();
  const location = useLocation();
  const relatedTeams = teams.filter((team) => team.contestId === contestId);
  const { page, totalPages, start, end, hrefForPage, headingRef } = useListPage(
    relatedTeams.length,
    'teamPage',
  );
  const teamFrom = encodeURIComponent(location.pathname + location.search);
  const contest = [...contests, archivedContest].find(
    (item) => item.id === contestId,
  );
  if (!contest)
    return (
      <EmptyState
        title="공모전을 찾을 수 없어요"
        description="탐색에서 다른 공모전을 확인해 주세요."
      >
        <ActionLink to={previewPath('/explore')}>탐색으로</ActionLink>
      </EmptyState>
    );
  const from = params.get('from');
  const back =
    from &&
    !/[\\\r\n]/.test(from) &&
    (from.startsWith('/design-preview/') || from === '/design-preview')
      ? from
      : previewPath('/explore');
  const backPathname = back.split('?')[0];
  const backLabel =
    backPathname === previewPath('/ai')
      ? 'AI 대화로'
      : backPathname === previewPath()
        ? '탐색으로'
        : backPathname?.startsWith(previewPath('/teams/'))
          ? '팀 상세로'
          : backPathname === previewPath('/explore')
            ? '탐색으로'
            : '이전 화면으로';
  return (
    <div className="preview-detail">
      <BackLink to={back}>{backLabel}</BackLink>
      <div className="preview-detail-grid">
        <article className="preview-stack">
          <div className="preview-row">
            {contest.interests.map((interest) => (
              <Badge key={interest}>{interest}</Badge>
            ))}
            <Badge tone="warm">{contestBadgeLabel(contest)}</Badge>
          </div>
          <PageIntro title={contest.title} description={contest.organizer} />
          <div className="preview-panel">
            <h2>공모전 소개</h2>
            <p>{contest.description}</p>
            <dl className="preview-detail-facts">
              <div>
                <dt>
                  <CalendarDays size={16} />
                  접수 마감
                </dt>
                <dd>{deadlineLabel(contest)}</dd>
              </div>
              <div>
                <dt>
                  <Users size={16} />
                  참가 대상
                </dt>
                <dd>{contest.audience.join(' · ')}</dd>
              </div>
              <div>
                <dt>접수 시작</dt>
                <dd>{contest.startsAt}</dd>
              </div>
              <div>
                <dt>공식 참가 인원</dt>
                <dd>{memberLimitLabel(contest)}</dd>
              </div>
              <div>
                <dt>원문 참가 자격</dt>
                <dd>{contest.audienceOriginal}</dd>
              </div>
              <div>
                <dt>제출물</dt>
                <dd>
                  {contest.deliverables.length
                    ? contest.deliverables.join(' · ')
                    : '공식 공고 확인 필요'}
                </dd>
              </div>
              <div>
                <dt>정보 확인일</dt>
                <dd>{contest.verifiedOn}</dd>
              </div>
            </dl>
            {deadlineNotice(contest) && (
              <p className="preview-muted">{deadlineNotice(contest)}</p>
            )}
            <a
              className="preview-button"
              href={contest.officialUrl}
              target="_blank"
              rel="noreferrer"
            >
              공식 공고 확인하기
            </a>
          </div>
          <Notice>공모전 접수는 주최 기관에서 진행합니다.</Notice>
        </article>
        <section
          className="preview-contest-teams-section"
          aria-labelledby="contest-teams-title"
        >
          <div className="preview-contest-teams-heading">
            <div className="preview-contest-teams-title">
              <h2 id="contest-teams-title" ref={headingRef} tabIndex={-1}>
                함께할 팀
              </h2>
              <span className="preview-result-count">
                <span className="sr-only">팀 </span>
                {relatedTeams.length}
                <span className="sr-only">개</span>
              </span>
            </div>
            {isContestOpen(contest) && (
              <div className="preview-contest-team-actions">
                <Button
                  asChild
                  variant="outline"
                  className="preview-compact-action preview-ai-shortcut"
                >
                  <Link
                    to={previewPath('/ai')}
                    aria-label="AI로 팀 찾아보기"
                    title="AI로 팀 찾아보기"
                  >
                    <Sparkles size={20} aria-hidden="true" />
                  </Link>
                </Button>
                <Button asChild className="preview-compact-action">
                  <Link
                    to={previewPath(`/teams/new?contest=${contest.id}`)}
                    aria-label="팀 만들기"
                    title="팀 만들기"
                  >
                    <Plus size={20} aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            )}
          </div>
          {contestStatus(contest) === 'upcoming' && (
            <Notice>접수가 시작되면 팀을 만들거나 지원할 수 있어요.</Notice>
          )}
          {contestStatus(contest) === 'closed' && (
            <Notice>
              접수가 마감되어 새 팀을 만들거나 지원할 수 없어요. 공고는 계속
              확인할 수 있어요.
            </Notice>
          )}
          {relatedTeams.length ? (
            <>
              <div className="preview-grid preview-contest-team-list">
                {relatedTeams.slice(start, end).map((team) => (
                  <TeamCard
                    key={team.id}
                    team={team}
                    to={previewPath(`/teams/${team.id}?from=${teamFrom}`)}
                    showContest={false}
                  />
                ))}
              </div>
              {totalPages > 1 && (
                <ListPagination
                  page={page}
                  totalPages={totalPages}
                  hrefForPage={hrefForPage}
                  label="공모전 팀 목록 페이지"
                />
              )}
            </>
          ) : (
            <EmptyState
              title={
                contestStatus(contest) === 'closed'
                  ? '등록된 팀이 없어요'
                  : '아직 함께할 팀이 없어요'
              }
              description={
                contestStatus(contest) === 'closed'
                  ? '공모전 상세 정보는 계속 확인할 수 있어요.'
                  : contestStatus(contest) === 'upcoming'
                    ? '접수가 시작되면 첫 팀을 만들어 보세요.'
                    : '첫 팀을 만들어 함께 도전해 보세요.'
              }
            />
          )}
        </section>
      </div>
    </div>
  );
}

export function PersonPage() {
  const { personId } = useParams();
  const [params] = useSearchParams();
  const { profile, signedIn } = usePreview();
  if (!signedIn)
    return (
      <EmptyState
        title="로그인이 필요해요"
        description="사람 프로필은 로그인 후 확인할 수 있어요."
      >
        <ActionLink
          to={previewPath(
            '/login?returnTo=' +
              encodeURIComponent(previewPath(`/people/${personId}`)),
          )}
        >
          로그인하기
        </ActionLink>
      </EmptyState>
    );
  const person =
    personId === 'me'
      ? signedIn
        ? getPublicProfile(profile)
        : null
      : people.find((item) => item.id === personId);
  if (!person)
    return (
      <EmptyState
        title="프로필을 찾을 수 없어요"
        description="사람 탐색에서 다른 프로필을 확인해 주세요."
      >
        <ActionLink to={previewPath('/explore?tab=people')}>
          사람 탐색으로
        </ActionLink>
      </EmptyState>
    );
  const from = params.get('from');
  const back =
    from &&
    !/[\\\r\n]/.test(from) &&
    (from === previewPath() ||
      from === previewPath('/ai') ||
      from === previewPath('/explore') ||
      from.startsWith(previewPath('/explore?')))
      ? from
      : previewPath('/explore?tab=people');
  return (
    <div className="preview-detail preview-profile-detail">
      <BackLink to={back}>
        {back === previewPath('/ai')
          ? 'AI 대화로'
          : back === previewPath()
            ? '탐색으로'
            : '사람 탐색으로'}
      </BackLink>
      <div className="preview-panel preview-stack">
        <div className="preview-row">
          <Avatar
            name={person.name}
            personId={person.id}
            avatarId={person.avatarId}
            size="large"
          />
          <div>
            <h1>{person.name}</h1>
            <p className="preview-muted">{person.roles.join(' · ')}</p>
          </div>
        </div>
        <SchoolVerificationBadge />
        <ProfileDetails profile={person} />
      </div>
    </div>
  );
}
