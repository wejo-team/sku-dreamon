/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ExplorePages.tsx - 탐색·공모전 상세·사람 상세 원본
 * 2. docs/design/screens.md - 공모전·팀·사람 탐색, 공모전 상세의 함께할 팀, 사람 상세 접근 제한
 * 3. docs/design/tokens.md - 공모전 카드(왼쪽 40% 포스터·D-day·우하단 팀 수), 검색창 안 AI 아이콘, 44px 조작
 * 4. docs/specs/contests.md - 공고 공개·참가·마감 정책
 * 5. docs/specs/profile.md#people-directory - 로그인 후 공개 프로필만 검색·열람
 * 6. docs/design/assets/explore-390.png, contest-teams-390.png, contest-teams-empty-390.png, people-pagination-390.png, search-ai-320.png - 실제 화면
 * 7. docs/api/contests.md#queries, docs/api/teams.md#queries, docs/api/profiles.md#directory-endpoints -
 *    검색·필터·정렬·페이지는 서버 query(q·fieldCode·roleCode·recruitingOnly·contestId·sort·page·pageSize)로 위임
 * 8. docs/development/frontend.md - 「API와 query」 각 화면은 로딩·빈 결과·오류 상태 제공
 */

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
import { useQuery } from '@tanstack/react-query';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import { audienceLabels, koreanDate } from '@/features/catalogs/labels';
import { useLabels } from '@/features/catalogs/queries';
import { useSession } from '@/features/auth/queries';
import {
  contestQueryOptions,
  contestsQueryOptions,
} from '@/features/contests/queries';
import {
  peopleQueryOptions,
  personQueryOptions,
} from '@/features/profiles/queries';
import {
  contestTeamsQueryOptions,
  teamsQueryOptions,
} from '@/features/teams/queries';
import {
  deadlineLabel,
  deadlineNotice,
  memberLimitLabel,
  summaryBadgeLabel,
  summaryDaysLeft,
} from '@/features/demo/contest-state';
import { ApiError } from '@/lib/api';
import { ContestCover } from '@/components/common/ContestCover';
import { ExploreFilters } from '@/features/explore/ExploreFilters';
import { ProfileDetails } from '@/components/common/ProfileDetails';
import { ListPagination } from '@/components/common/ListPagination';
import {
  REFERENCE_PAGE_SIZE,
  requestedPage,
  useListPage,
} from '@/components/common/use-list-page';
import { TeamCard } from '@/components/common/TeamCard';
import {
  ActionLink,
  Avatar,
  BackLink,
  Badge,
  EmptyState,
  Notice,
  PageIntro,
  SchoolVerificationBadge,
} from '@/components/common/CommonUi';

// [출처 2, 3, 6] 탭·검색·필터·정렬·페이지를 URL에 유지하는 탐색
export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const { signedIn } = useSession();
  const { fieldLabel, roleLabel } = useLabels();
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
  // [출처 7] 검색·필터·정렬·페이지는 서버가 처리합니다. 빈 값은 보내지 않습니다.
  const page = requestedPage(params);
  const search = q.trim() || undefined;
  const contestParam = params.get('contest') ?? '';
  const contestsQuery = useQuery({
    ...contestsQueryOptions({
      q: search,
      fieldCode: category || undefined,
      sort: sort === 'deadline' ? 'deadline_asc' : 'created_desc',
      page,
      pageSize: REFERENCE_PAGE_SIZE,
    }),
    enabled: tab === 'contests',
  });
  const teamsQuery = useQuery({
    ...teamsQueryOptions({
      q: search,
      roleCode: role || undefined,
      recruitingOnly: params.get('open') === 'true' || undefined,
      contestId: contestParam || undefined,
      page,
      pageSize: REFERENCE_PAGE_SIZE,
    }),
    enabled: tab === 'teams',
  });
  // [출처 5] 로그인 후 현재 공개 프로필만
  const peopleQuery = useQuery({
    ...peopleQueryOptions({
      q: search,
      roleCode: role || undefined,
      page,
      pageSize: REFERENCE_PAGE_SIZE,
    }),
    enabled: tab === 'people' && signedIn,
  });
  const active =
    tab === 'contests'
      ? contestsQuery
      : tab === 'teams'
        ? teamsQuery
        : peopleQuery;
  const count = active.data?.pagination.total ?? 0;
  const ready = !!active.data && !active.isPlaceholderData;
  const { totalPages, hrefForPage, headingRef } = useListPage(
    count,
    'page',
    ready,
  );
  const reset = () => setParams(tab === 'contests' ? {} : { tab });
  const contextQuery = useQuery({
    ...contestQueryOptions(contestParam),
    enabled: !!contestParam,
  });
  const contestContext = contextQuery.data;
  const listState =
    tab === 'people' && !signedIn
      ? 'guest'
      : active.isError
        ? 'error'
        : !active.data
          ? 'loading'
          : 'ready';
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
            to={value === 'contests' ? '/explore' : `/explore?tab=${value}`}
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
          <Link to="/ai" aria-label="AI에게 추천 받기" title="AI에게 추천 받기">
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
        {listState === 'ready' && (
          <span className="preview-result-count" role="status">
            <span className="sr-only">검색 결과 </span>
            {count}
            <span className="sr-only">개</span>
          </span>
        )}
        {tab === 'teams' && (
          <Link className="preview-text-link" to="/teams/new">
            팀 만들기
            <ArrowRight size={16} aria-hidden="true" />
          </Link>
        )}
      </div>
      {listState === 'guest' ? (
        <EmptyState
          title="로그인하고 함께할 사람을 찾아보세요"
          description="공개에 동의한 사람들의 프로필을 확인할 수 있어요."
        >
          <ActionLink
            to={'/login?returnTo=' + encodeURIComponent('/explore?tab=people')}
          >
            로그인하기
          </ActionLink>
        </EmptyState>
      ) : listState === 'error' ? (
        <EmptyState
          title="목록을 불러오지 못했어요"
          description="잠시 후 다시 시도해 주세요."
        >
          <Button onClick={() => void active.refetch()} variant="outline">
            다시 시도
          </Button>
        </EmptyState>
      ) : listState === 'loading' ? (
        <p className="preview-muted" role="status">
          불러오는 중…
        </p>
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
            contestsQuery.data?.data.map((item, index) => (
              <Link
                className="preview-card preview-contest-card"
                key={item.id}
                to={`/contests/${item.id}?from=${from}`}
              >
                <div className="preview-contest-cover">
                  <ContestCover
                    src={item.posterUrl ?? undefined}
                    loading={index === 0 ? 'eager' : 'lazy'}
                  />
                  <span
                    className={`preview-deadline ${item.registrationStatus === 'open' && summaryDaysLeft(item) <= 7 ? 'preview-deadline--soon' : ''}`}
                  >
                    {summaryBadgeLabel(item)}
                  </span>
                </div>
                <div className="preview-contest-copy">
                  <h3>{item.title}</h3>
                  <div className="preview-row">
                    {item.fieldCodes.map((code) => (
                      <Badge key={code}>{fieldLabel(code)}</Badge>
                    ))}
                  </div>
                  <p className="preview-muted">{item.organizer}</p>
                  <span className="preview-contest-teams">
                    <Users size={16} aria-hidden="true" />
                    <span className="sr-only">연결된 팀 </span>
                    {/* [출처 3] 모집 상태와 관계없는 연결 팀 전체 수(teamCount) */}
                    {item.teamCount}
                    <span className="sr-only">개</span>
                  </span>
                </div>
              </Link>
            ))}
          {tab === 'teams' &&
            teamsQuery.data?.data.map((item) => (
              <TeamCard
                key={item.id}
                team={item}
                roleLabel={roleLabel}
                to={`/teams/${item.id}?from=${from}`}
              />
            ))}
          {tab === 'people' &&
            peopleQuery.data?.data.map((item) => (
              <Link
                className="preview-card preview-person-card"
                key={item.accountId}
                to={`/people/${item.accountId}?from=${from}`}
              >
                <div className="preview-row">
                  <Avatar
                    name={item.realName}
                    imageCode={item.profileImageCode}
                  />
                  <div>
                    <h3>{item.realName}</h3>
                    <p className="preview-muted">
                      {item.roleCodes.map(roleLabel).join(' · ')}
                    </p>
                  </div>
                  <ChevronRight
                    className="preview-person-arrow"
                    size={20}
                    aria-hidden="true"
                  />
                </div>
                <div className="preview-row">
                  {item.fieldCodes.map((code) => (
                    <Badge key={code}>{fieldLabel(code)}</Badge>
                  ))}
                </div>
              </Link>
            ))}
        </div>
      )}
      {listState === 'ready' && count > 0 && (
        <ListPagination
          page={active.data?.pagination.page ?? page}
          totalPages={totalPages}
          hrefForPage={hrefForPage}
          label="탐색 결과 페이지"
        />
      )}
    </section>
  );
}

// [출처 2, 4, 6] 공고 정보와 연결 팀, 마감 시 생성·AI 숨김
export function ContestPage() {
  const { contestId = '' } = useParams();
  const [params] = useSearchParams();
  const { fieldLabel, roleLabel } = useLabels();
  const location = useLocation();
  const contestQuery = useQuery(contestQueryOptions(contestId));
  // [출처 7] 이 공고의 팀(모집 상태와 관계없이 전체)을 서버 페이지로 받습니다.
  const teamPage = requestedPage(params, 'teamPage');
  const teamsQuery = useQuery({
    ...contestTeamsQueryOptions(contestId, {
      page: teamPage,
      pageSize: REFERENCE_PAGE_SIZE,
    }),
    enabled: !!contestQuery.data,
  });
  const teamTotal = teamsQuery.data?.pagination.total ?? 0;
  const { totalPages, hrefForPage, headingRef } = useListPage(
    teamTotal,
    'teamPage',
    !!teamsQuery.data && !teamsQuery.isPlaceholderData,
  );
  const teamFrom = encodeURIComponent(location.pathname + location.search);
  const contest = contestQuery.data;
  if (contestQuery.isPending)
    return (
      <p className="preview-muted" role="status">
        불러오는 중…
      </p>
    );
  if (contestQuery.isError && !isNotFound(contestQuery.error))
    return (
      <EmptyState
        title="공모전 정보를 불러오지 못했어요"
        description="잠시 후 다시 시도해 주세요."
      >
        <Button variant="outline" onClick={() => void contestQuery.refetch()}>
          다시 시도
        </Button>
      </EmptyState>
    );
  if (!contest)
    return (
      <EmptyState
        title="공모전을 찾을 수 없어요"
        description="탐색에서 다른 공모전을 확인해 주세요."
      >
        <ActionLink to="/explore">탐색으로</ActionLink>
      </EmptyState>
    );
  const from = params.get('from');
  const back =
    from &&
    !/[\\\r\n]/.test(from) &&
    from.startsWith('/') &&
    !from.startsWith('//')
      ? from
      : '/explore';
  const backPathname = back.split('?')[0];
  const backLabel =
    backPathname === '/ai'
      ? 'AI 대화로'
      : backPathname === '/'
        ? '탐색으로'
        : backPathname?.startsWith('/teams/')
          ? '팀 상세로'
          : backPathname === '/explore'
            ? '탐색으로'
            : '이전 화면으로';
  return (
    <div className="preview-detail">
      <BackLink to={back}>{backLabel}</BackLink>
      <div className="preview-detail-grid">
        <article className="preview-stack">
          <div className="preview-row">
            {contest.fieldCodes.map((code) => (
              <Badge key={code}>{fieldLabel(code)}</Badge>
            ))}
            <Badge tone="warm">{summaryBadgeLabel(contest)}</Badge>
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
                <dd>{deadlineLabel(contest.timing.closing)}</dd>
              </div>
              <div>
                <dt>
                  <Users size={16} />
                  참가 대상
                </dt>
                <dd>
                  {contest.audienceCodes
                    .map((code) => audienceLabels[code])
                    .join(' · ')}
                </dd>
              </div>
              <div>
                <dt>접수 시작</dt>
                <dd>{contest.timing.openSourceDate}</dd>
              </div>
              <div>
                <dt>공식 참가 인원</dt>
                <dd>{memberLimitLabel(contest.capacity)}</dd>
              </div>
              <div>
                <dt>원문 참가 자격</dt>
                <dd>{contest.eligibilityText}</dd>
              </div>
              <div>
                <dt>제출물</dt>
                <dd>{contest.deliverables || '공식 공고 확인 필요'}</dd>
              </div>
              <div>
                <dt>정보 확인일</dt>
                <dd>{koreanDate(contest.verifiedAt)}</dd>
              </div>
            </dl>
            {deadlineNotice(contest.timing.closing) && (
              <p className="preview-muted">
                {deadlineNotice(contest.timing.closing)}
              </p>
            )}
            <a
              className="preview-button"
              href={contest.sourceUrl}
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
                {teamTotal}
                <span className="sr-only">개</span>
              </span>
            </div>
            {contest.registrationStatus === 'open' && (
              <div className="preview-contest-team-actions">
                <Button
                  asChild
                  variant="outline"
                  className="preview-compact-action preview-ai-shortcut"
                >
                  <Link
                    to="/ai"
                    aria-label="AI로 팀 찾아보기"
                    title="AI로 팀 찾아보기"
                  >
                    <Sparkles size={20} aria-hidden="true" />
                  </Link>
                </Button>
                <Button asChild className="preview-compact-action">
                  <Link
                    to={`/teams/new?contest=${contest.id}`}
                    aria-label="팀 만들기"
                    title="팀 만들기"
                  >
                    <Plus size={20} aria-hidden="true" />
                  </Link>
                </Button>
              </div>
            )}
          </div>
          {contest.registrationStatus === 'scheduled' && (
            <Notice>접수가 시작되면 팀을 만들거나 지원할 수 있어요.</Notice>
          )}
          {contest.registrationStatus === 'closed' && (
            <Notice>
              접수가 마감되어 새 팀을 만들거나 지원할 수 없어요. 공고는 계속
              확인할 수 있어요.
            </Notice>
          )}
          {!teamsQuery.data ? (
            <p className="preview-muted" role="status">
              {teamsQuery.isError
                ? '팀 목록을 불러오지 못했어요.'
                : '불러오는 중…'}
            </p>
          ) : teamTotal ? (
            <>
              <div className="preview-grid preview-contest-team-list">
                {teamsQuery.data.data.map((team) => (
                  <TeamCard
                    key={team.id}
                    team={{ ...team, contest }}
                    roleLabel={roleLabel}
                    to={`/teams/${team.id}?from=${teamFrom}`}
                    showContest={false}
                  />
                ))}
              </div>
              {totalPages > 1 && (
                <ListPagination
                  page={teamsQuery.data.pagination.page}
                  totalPages={totalPages}
                  hrefForPage={hrefForPage}
                  label="공모전 팀 목록 페이지"
                />
              )}
            </>
          ) : (
            <EmptyState
              title={
                contest.registrationStatus === 'closed'
                  ? '등록된 팀이 없어요'
                  : '아직 함께할 팀이 없어요'
              }
              description={
                contest.registrationStatus === 'closed'
                  ? '공모전 상세 정보는 계속 확인할 수 있어요.'
                  : contest.registrationStatus === 'scheduled'
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

// [출처 2, 5] 비공개 프로필 직접 접근 제외, 로그인 안내
export function PersonPage() {
  const { personId = '' } = useParams();
  const [params] = useSearchParams();
  const session = useSession();
  const labels = useLabels();
  const { roleLabel } = labels;
  const personQuery = useQuery({
    ...personQueryOptions(personId),
    enabled: session.signedIn,
  });
  if (session.isPending || (session.signedIn && personQuery.isPending))
    return (
      <p className="preview-muted" role="status">
        불러오는 중…
      </p>
    );
  if (!session.signedIn)
    return (
      <EmptyState
        title="로그인이 필요해요"
        description="사람 프로필은 로그인 후 확인할 수 있어요."
      >
        <ActionLink
          to={'/login?returnTo=' + encodeURIComponent(`/people/${personId}`)}
        >
          로그인하기
        </ActionLink>
      </EmptyState>
    );
  if (personQuery.isError && !isNotFound(personQuery.error))
    return (
      <EmptyState
        title="프로필을 불러오지 못했어요"
        description="잠시 후 다시 시도해 주세요."
      >
        <Button variant="outline" onClick={() => void personQuery.refetch()}>
          다시 시도
        </Button>
      </EmptyState>
    );
  // [출처 5] 공개 프로필만 상세 열람. 비공개·미존재는 서버가 같은 404로 응답
  // 404면 이전에 받은 프로필이 있어도 표시하지 않습니다(비공개 전환·계정 전환).
  const person = isNotFound(personQuery.error) ? undefined : personQuery.data;
  if (!person)
    return (
      <EmptyState
        title="프로필을 찾을 수 없어요"
        description="사람 탐색에서 다른 프로필을 확인해 주세요."
      >
        <ActionLink to="/explore?tab=people">사람 탐색으로</ActionLink>
      </EmptyState>
    );
  const from = params.get('from');
  const back =
    from &&
    !/[\\\r\n]/.test(from) &&
    (from === '/' ||
      from === '/ai' ||
      from === '/explore' ||
      from.startsWith('/explore?'))
      ? from
      : '/explore?tab=people';
  return (
    <div className="preview-detail preview-profile-detail">
      <BackLink to={back}>
        {back === '/ai'
          ? 'AI 대화로'
          : back === '/'
            ? '탐색으로'
            : '사람 탐색으로'}
      </BackLink>
      <div className="preview-panel preview-stack">
        <div className="preview-row">
          <Avatar
            name={person.realName}
            imageCode={person.profileImageCode}
            size="large"
          />
          <div>
            <h1>{person.realName}</h1>
            <p className="preview-muted">
              {person.roleCodes.map(roleLabel).join(' · ')}
            </p>
          </div>
        </div>
        <SchoolVerificationBadge />
        <ProfileDetails profile={person} labels={labels} />
      </div>
    </div>
  );
}

// 존재를 숨기는 관계·없는 리소스는 404(코드는 리소스별로 다를 수 있어 status로 판단)
const isNotFound = (error: unknown) =>
  error instanceof ApiError && error.status === 404;
