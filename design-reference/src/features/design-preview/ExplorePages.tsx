import {
  ArrowRight,
  CalendarDays,
  ChevronRight,
  Search,
  Users,
  X,
} from 'lucide-react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { NativeSelect } from '@/components/ui/native-select';
import {
  contests,
  archivedContest,
  interestOptions,
  people,
  previewPath,
  roleOptions,
  getPublicProfile,
} from './data';
import { usePreview } from './preview-context';
import { ContestCover } from './ContestCover';
import {
  ActionLink,
  Avatar,
  BackLink,
  Badge,
  EmptyState,
  Notice,
  PageIntro,
} from './PreviewUi';

export function ExplorePage() {
  const [params, setParams] = useSearchParams();
  const { teams, profile, signedIn } = usePreview();
  const mine = signedIn ? getPublicProfile(profile) : null;
  const visiblePeople = signedIn ? (mine ? [...people, mine] : people) : [];
  const location = useLocation();
  const tab = ['teams', 'people'].includes(params.get('tab') ?? '')
    ? params.get('tab')!
    : 'contests';
  const q = params.get('q') ?? '';
  const category = params.get('category') ?? '';
  const role = params.get('role') ?? '';
  const sort = params.get('sort') ?? 'default';
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next, { replace: key === 'q' });
  };
  const from = encodeURIComponent(location.pathname + location.search);
  const includes = (text: string) =>
    text.toLocaleLowerCase().includes(q.trim().toLocaleLowerCase());
  const matchedContests = contests.filter(
    (item) =>
      includes(`${item.title} ${item.organizer} ${item.category}`) &&
      (!category || item.interests.includes(category)),
  );
  if (sort === 'deadline') matchedContests.sort((a, b) => a.days - b.days);
  const matchedTeams = teams.filter(
    (item) =>
      includes(
        `${item.name} ${item.summary} ${item.roles.join(' ')} ${contests.find((contest) => contest.id === item.contestId)?.title}`,
      ) &&
      (!role || item.roles.includes(role)) &&
      (params.get('open') !== 'true' ||
        ['모집중', '지원자검토'].includes(item.status)) &&
      (!params.get('contest') || item.contestId === params.get('contest')),
  );
  const matchedPeople = visiblePeople.filter(
    (item) =>
      includes(
        `${item.name} ${item.roles.join(' ')} ${item.interests?.join(' ') ?? ''} ${item.intro ?? ''} ${item.experience ?? ''}`,
      ) &&
      (!role || item.roles.includes(role)),
  );
  const count =
    tab === 'contests'
      ? matchedContests.length
      : tab === 'teams'
        ? matchedTeams.length
        : matchedPeople.length;
  const reset = () => setParams(tab === 'contests' ? {} : { tab });
  const contestContext = contests.find(
    (item) => item.id === params.get('contest'),
  );
  return (
    <section className="preview-explore" aria-label="탐색">
      <PageIntro title="탐색" />
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
      </div>
      <div className="preview-filters">
        {tab === 'contests' ? (
          <div className="preview-filter-control">
            <Label className="sr-only" htmlFor="explore-category">
              분야
            </Label>
            <NativeSelect
              id="explore-category"
              value={category}
              onChange={(event) => update('category', event.target.value)}
            >
              <option value="">모든 분야</option>
              {interestOptions.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </NativeSelect>
          </div>
        ) : (
          <div className="preview-filter-control">
            <Label className="sr-only" htmlFor="explore-role">
              역할
            </Label>
            <NativeSelect
              id="explore-role"
              value={role}
              onChange={(event) => update('role', event.target.value)}
            >
              <option value="">모든 역할</option>
              {roleOptions.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </NativeSelect>
          </div>
        )}
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
        {tab === 'teams' && (
          <Label className="preview-inline-check" htmlFor="explore-open">
            <Checkbox
              id="explore-open"
              checked={params.get('open') === 'true'}
              onCheckedChange={(checked) =>
                update('open', checked === true ? 'true' : '')
              }
            />
            모집중만
          </Label>
        )}
        {(q || category || role || params.get('open') || contestContext) && (
          <Button
            variant="ghost"
            className="preview-text-button"
            onClick={reset}
          >
            초기화
          </Button>
        )}
      </div>
      {contestContext && tab === 'teams' && (
        <Notice>{contestContext.title}에 함께 도전하는 팀이에요.</Notice>
      )}
      <div className="preview-results-heading">
        <h2>
          {tab === 'contests'
            ? '모집 중인 공모전'
            : tab === 'teams'
              ? '함께 도전하는 팀'
              : '다양한 관심사를 가진 사람들'}
        </h2>
        <span className="preview-result-count" role="status">
          <span className="sr-only">검색 결과 </span>
          {count}
          <span className="sr-only">개</span>
        </span>
        {tab === 'teams' && (
          <Link className="preview-text-link" to={previewPath('/teams/new')}>
            팀 만들기
            <ArrowRight size={16} />
          </Link>
        )}
      </div>
      {tab !== 'people' && (
        <ActionLink to={previewPath('/ai')} secondary>
          AI에게 추천 받기
        </ActionLink>
      )}
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
            matchedContests.map((item, index) => (
              <Link
                className="preview-card preview-contest-card"
                key={item.id}
                to={previewPath(`/contests/${item.id}?from=${from}`)}
              >
                <div className="preview-contest-heading">
                  <div className="preview-contest-cover">
                    <ContestCover
                      src={item.cover}
                      loading={index === 0 ? 'eager' : 'lazy'}
                    />
                    <span
                      className={`preview-deadline ${item.days <= 7 ? 'preview-deadline--soon' : ''}`}
                    >
                      D−{item.days}
                    </span>
                  </div>
                  <div className="preview-contest-copy">
                    <Badge>{item.category}</Badge>
                    <h3>{item.title}</h3>
                    <p className="preview-muted">{item.organizer}</p>
                  </div>
                </div>
                <dl className="preview-card-facts">
                  <div>
                    <dt>참가 대상</dt>
                    <dd>{item.audience}</dd>
                  </div>
                  <div>
                    <dt>접수 마감</dt>
                    <dd>{item.deadline}</dd>
                  </div>
                </dl>
                <div className="preview-card-footer">
                  <span>
                    <Users size={16} aria-hidden="true" />
                    함께할 팀{' '}
                    {
                      teams.filter(
                        (team) =>
                          team.contestId === item.id &&
                          team.status === '모집중',
                      ).length
                    }
                    개
                  </span>
                  <span className="preview-contest-detail-link">
                    상세 보기
                    <ChevronRight size={16} aria-hidden="true" />
                  </span>
                </div>
              </Link>
            ))}
          {tab === 'teams' &&
            matchedTeams.map((item) => (
              <Link
                className="preview-card preview-team-card"
                key={item.id}
                to={previewPath(`/teams/${item.id}?from=${from}`)}
              >
                <div className="preview-row preview-split">
                  <Badge tone={item.status === '모집중' ? 'lime' : 'neutral'}>
                    {item.status}
                  </Badge>
                  <span className="preview-muted">
                    {item.members}명 활동 중
                  </span>
                </div>
                <h3>{item.name}</h3>
                <p className="preview-card-description">{item.summary}</p>
                <div className="preview-row">
                  {item.roles.map((value) => (
                    <Badge key={value}>{value}</Badge>
                  ))}
                </div>
                <div className="preview-card-footer">
                  <span>
                    {
                      contests.find((contest) => contest.id === item.contestId)
                        ?.title
                    }
                  </span>
                  <ChevronRight size={20} aria-hidden="true" />
                </div>
              </Link>
            ))}
          {tab === 'people' &&
            matchedPeople.map((item) => (
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
    </section>
  );
}

export function ContestPage() {
  const { contestId } = useParams();
  const [params] = useSearchParams();
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
            <Badge>{contest.category}</Badge>
            <Badge tone="warm">
              {contest.status === 'closed' ? '접수 마감' : `D−${contest.days}`}
            </Badge>
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
                <dd>{contest.deadline}</dd>
              </div>
              <div>
                <dt>
                  <Users size={16} />
                  참가 대상
                </dt>
                <dd>{contest.audience}</dd>
              </div>
              <div>
                <dt>접수 시작</dt>
                <dd>{contest.startsAt}</dd>
              </div>
              <div>
                <dt>참가 방식</dt>
                <dd>
                  {contest.participation === 'individual'
                    ? '개인 참가'
                    : contest.participation === 'both'
                      ? '개인 또는 팀 참가'
                      : '팀 참가'}
                </dd>
              </div>
              {contest.participation !== 'individual' && (
                <div>
                  <dt>공식 팀 인원</dt>
                  <dd>
                    {contest.minMembers && contest.maxMembers
                      ? `${contest.minMembers}~${contest.maxMembers}명`
                      : '공식 공고 확인 필요'}
                  </dd>
                </div>
              )}
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
        <aside className="preview-panel preview-detail-aside">
          <h2>함께할 팀</h2>
          {contest.participation === 'individual' && (
            <Notice>
              개인 참가 공모전이에요. 준비 모임에서 함께 준비하고 접수는 각자
              진행해요.
            </Notice>
          )}
          {contest.status === 'closed' ? (
            <Notice>
              접수가 마감되어 새 팀을 만들거나 지원할 수 없어요. 공고는 계속
              확인할 수 있어요.
            </Notice>
          ) : (
            <>
              <ActionLink
                to={previewPath(`/explore?tab=teams&contest=${contest.id}`)}
              >
                팀 찾기
              </ActionLink>
              <ActionLink
                to={previewPath(`/teams/new?contest=${contest.id}`)}
                secondary
              >
                {contest.participation === 'individual'
                  ? '준비 모임 만들기'
                  : '팀 만들기'}
              </ActionLink>
              <ActionLink to={previewPath('/ai')} secondary>
                AI로 팀 찾아보기
              </ActionLink>
            </>
          )}
        </aside>
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
        <div>
          <h2>희망 역할</h2>
          <div className="preview-row">
            {person.roles.map((role) => (
              <Badge key={role} tone="lime">
                {role}
              </Badge>
            ))}
          </div>
        </div>
        {!!person.interests?.length && (
          <div>
            <h2>관심 분야</h2>
            <div className="preview-row">
              {(person.interests ?? []).map((interest) => (
                <Badge key={interest}>{interest}</Badge>
              ))}
            </div>
          </div>
        )}
        {person.intro && (
          <div>
            <h2>자기소개</h2>
            <p>{person.intro}</p>
          </div>
        )}
        {person.experience && (
          <div>
            <h2>경험</h2>
            <p>{person.experience}</p>
          </div>
        )}
        <Badge>미인증</Badge>
      </div>
    </div>
  );
}
