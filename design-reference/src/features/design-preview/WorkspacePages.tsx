import { useEffect, useRef, useState, type ReactNode } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { Controller, useForm } from 'react-hook-form';
import {
  ArrowRight,
  CheckCircle2,
  ChevronRight,
  ClipboardList,
  ExternalLink,
  FileText,
  LoaderCircle,
  Plus,
  Sparkles,
} from 'lucide-react';
import { Link, useLocation, useParams } from 'react-router';
import { z } from 'zod';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from '@/components/ui/drawer';
import { Label } from '@/components/ui/label';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Textarea } from '@/components/ui/textarea';
import {
  contests,
  previewBase,
  previewPath,
  roleOptions,
  type Applicant,
  type ApplicationStatus,
  type Team,
} from './data';
import {
  ActionLink,
  Avatar,
  BackLink,
  Badge,
  EmptyState,
  PageIntro,
} from './PreviewUi';
import { usePreview } from './preview-context';
import { missingProfileFields } from './profile-fields';
import {
  applicantVisibleProfile,
  isTeamMember,
  recruitmentIssue,
  selectionScenario,
  teamStatusLabel,
} from './team-state';
import './workspace.css';

const workspacePath = previewPath('/workspace');
const applicationsPath = `${workspacePath}?view=applications`;
const applicationSchema = z.object({
  role: z.string().min(1, '지원할 역할을 선택해 주세요.'),
  message: z
    .string()
    .trim()
    .max(1000, '팀에 전할 말은 1,000자까지 입력할 수 있어요.'),
});
type ApplicationFields = z.infer<typeof applicationSchema>;

function returnPath(search: string, fallback: string) {
  const from = new URLSearchParams(search).get('from');
  if (!from || /[\\\r\n]/.test(from)) return fallback;
  if (from === previewBase) return previewPath('/explore');
  return from.startsWith(`${previewBase}/`) ? from : fallback;
}
function loginPath(from: string) {
  return `${previewPath('/login')}?returnTo=${encodeURIComponent(from)}`;
}
function teamPath(id: string, from = workspacePath) {
  return `${previewPath(`/teams/${id}`)}?from=${encodeURIComponent(from)}`;
}
function teamViewPath(
  id: string,
  view: 'space' | 'applicants',
  from = workspacePath,
) {
  return `${previewPath(`/teams/${id}`)}?${new URLSearchParams({ view, from }).toString()}`;
}
function returnLabel(path: string) {
  if (path === previewPath('/ai')) return 'AI 대화로';
  if (path === previewPath('/explore')) return '탐색으로';
  if (path === applicationsPath) return '내 지원으로';
  if (path.split('?')[0] === workspacePath) return '워크스페이스로';
  return '목록으로';
}
function applicationLabel(status: ApplicationStatus) {
  return {
    지원완료: '지원 완료',
    검토중: '검토 중',
    선발: '선발 · 팀원 확정',
    미선발: '미선발',
    지원취소: '지원 취소',
  }[status];
}
function LoginPrompt({ from }: { from: string }) {
  return (
    <EmptyState
      title="로그인하고 이어가세요"
      description="내 팀과 지원 현황은 로그인 후 확인할 수 있어요."
    >
      <ActionLink to={loginPath(from)}>로그인하기</ActionLink>
    </EmptyState>
  );
}

function ConfirmAction({
  children,
  title,
  description,
  confirmLabel,
  onConfirm,
  destructive = false,
}: {
  children: ReactNode;
  title: string;
  description: string;
  confirmLabel: string;
  onConfirm: () => boolean;
  destructive?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(false);
  return (
    <Drawer
      open={open}
      onOpenChange={(value) => {
        setOpen(value);
        setError(false);
      }}
    >
      <DrawerTrigger asChild>
        <Button type="button" variant="outline" className="preview-button">
          {children}
        </Button>
      </DrawerTrigger>
      <DrawerContent className="dreamon-preview preview-drawer workspace-confirm-drawer">
        <DrawerHeader>
          <DrawerTitle>{title}</DrawerTitle>
          <DrawerDescription>{description}</DrawerDescription>
        </DrawerHeader>
        {error && (
          <Alert variant="destructive" role="alert">
            <AlertDescription>
              현재 상태가 바뀌어 처리하지 못했어요. 모집 상태와 정원, 소속을
              다시 확인해 주세요.
            </AlertDescription>
          </Alert>
        )}
        <DrawerFooter>
          <Button
            type="button"
            variant="default"
            className={`preview-button${destructive ? ' workspace-destructive-action' : ''}`}
            onClick={() => {
              if (onConfirm()) setOpen(false);
              else setError(true);
            }}
          >
            {confirmLabel}
          </Button>
          <DrawerClose asChild>
            <Button type="button" variant="outline" className="preview-button">
              돌아가기
            </Button>
          </DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}

export function WorkspacePage() {
  const { signedIn, teams, applications, applicants, cancelApplication } =
    usePreview();
  const location = useLocation();
  const showApplications =
    new URLSearchParams(location.search).get('view') === 'applications';
  const myTeams = teams.filter((team) => isTeamMember(team));
  if (!signedIn)
    return (
      <div className="workspace-page preview-stack">
        <PageIntro title="워크스페이스" />
        <LoginPrompt
          from={showApplications ? applicationsPath : workspacePath}
        />
      </div>
    );
  return (
    <div className="workspace-page preview-stack">
      <header className="workspace-heading">
        <PageIntro title="워크스페이스" />
        <nav className="workspace-actions" aria-label="워크스페이스 작업">
          <Button asChild variant="outline" className="workspace-action">
            <Link
              to={applicationsPath}
              aria-label="내 지원"
              title="내 지원"
              aria-current={showApplications ? 'page' : undefined}
            >
              <ClipboardList size={20} aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild className="workspace-action workspace-create-action">
            <Link
              to={previewPath('/teams/new')}
              aria-label="팀 만들기"
              title="팀 만들기"
            >
              <Plus size={22} aria-hidden="true" />
            </Link>
          </Button>
        </nav>
      </header>
      {showApplications ? (
        <section
          className="preview-stack"
          aria-labelledby="workspace-applications-title"
        >
          <BackLink to={workspacePath}>내 팀으로</BackLink>
          <div className="preview-section-title">
            <h2 id="workspace-applications-title">내 지원</h2>
            <span className="preview-muted">{applications.length}건</span>
          </div>
          {!applications.length ? (
            <EmptyState
              title="아직 지원한 팀이 없어요"
              description="함께할 팀을 찾아 지원해 보세요."
            >
              <ActionLink to={previewPath('/explore?tab=teams')} secondary>
                팀 둘러보기
              </ActionLink>
            </EmptyState>
          ) : (
            <ul className="workspace-application-list">
              {[...applications].reverse().map((application) => {
                const team = teams.find(
                  (item) => item.id === application.teamId,
                );
                const selected = application.status === '선발';
                const cancellable = ['지원완료', '검토중', '선발'].includes(
                  application.status,
                );
                return (
                  <li
                    key={application.id}
                    className="preview-panel preview-stack"
                  >
                    <div className="preview-split">
                      <div>
                        <h3>{team?.name ?? '팀 정보 없음'}</h3>
                        <p className="preview-muted">{application.role} 지원</p>
                      </div>
                      <Badge tone={selected ? 'lime' : 'neutral'}>
                        {applicationLabel(application.status)}
                      </Badge>
                    </div>
                    <p className="preview-muted">
                      {
                        contests.find((item) => item.id === team?.contestId)
                          ?.title
                      }
                    </p>
                    {selected && (
                      <p>
                        선발되어 팀원이 됐어요. 팀 공간에서 함께할 멤버를
                        확인하세요.
                      </p>
                    )}
                    {application.status === '지원취소' && (
                      <p className="preview-muted">
                        지원이 취소됐어요. 현재 모집 조건이 맞으면 다시 지원할
                        수 있어요.
                      </p>
                    )}
                    {team && (
                      <>
                        <ActionLink
                          to={
                            selected && isTeamMember(team)
                              ? teamViewPath(team.id, 'space', applicationsPath)
                              : teamPath(team.id, applicationsPath)
                          }
                          secondary
                        >
                          {selected && isTeamMember(team)
                            ? '팀 공간으로'
                            : '지원한 팀 보기'}
                        </ActionLink>
                        {cancellable && (
                          <ConfirmAction
                            title={
                              selected
                                ? '팀 참여를 취소할까요?'
                                : '지원을 취소할까요?'
                            }
                            description={
                              selected
                                ? '확정된 팀원에서 제외되고 팀 공간에 접근할 수 없게 돼요. 모집이 끝난 팀은 다시 지원할 수 없어요.'
                                : '팀장에게 취소 결과가 표시돼요. 현재 모집 조건을 충족하면 다시 지원할 수 있어요.'
                            }
                            confirmLabel="지원 취소하기"
                            onConfirm={() => cancelApplication(application.id)}
                            destructive
                          >
                            지원 취소
                          </ConfirmAction>
                        )}
                      </>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </section>
      ) : (
        <section
          className="preview-stack"
          aria-labelledby="workspace-teams-title"
        >
          <div className="preview-section-title">
            <h2 id="workspace-teams-title">내 팀</h2>
            <span className="preview-muted">{myTeams.length}개</span>
          </div>
          {!myTeams.length ? (
            <EmptyState
              title="함께할 첫 팀을 찾아보세요"
              description="팀을 만들거나 관심 있는 팀에 지원해 보세요."
            >
              <ActionLink to={previewPath('/explore?tab=teams')}>
                팀 둘러보기
              </ActionLink>
            </EmptyState>
          ) : (
            <div className="workspace-team-grid">
              {myTeams.map((team) => {
                const pending = applicants.filter(
                  (item) =>
                    item.teamId === team.id &&
                    ['지원완료', '검토중'].includes(item.status),
                ).length;
                return (
                  <Link
                    key={team.id}
                    to={teamViewPath(team.id, 'space')}
                    className="preview-card workspace-team-card"
                    aria-label={`${team.name} 팀 공간으로`}
                  >
                    <div className="preview-split">
                      <Badge>{teamStatusLabel(team)}</Badge>
                      {team.owner && pending > 0 && (
                        <span className="workspace-pending">
                          검토 대기 {pending}명
                        </span>
                      )}
                    </div>
                    <h3>{team.name}</h3>
                    <p className="workspace-team-contest">
                      {
                        contests.find((item) => item.id === team.contestId)
                          ?.title
                      }
                    </p>
                    <div className="workspace-team-summary">
                      <dl className="workspace-team-facts">
                        <div>
                          <dt>내 역할</dt>
                          <dd>{team.owner ? '팀장' : '팀원'}</dd>
                        </div>
                        <div>
                          <dt>확정 인원</dt>
                          <dd>
                            {team.members} / {team.capacity}명
                          </dd>
                        </div>
                      </dl>
                      <span className="workspace-team-enter" aria-hidden="true">
                        <ChevronRight size={22} />
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </section>
      )}
    </div>
  );
}

function TeamTabs({
  team,
  active,
  from,
}: {
  team: Team;
  active: 'space' | 'applicants';
  from: string;
}) {
  return (
    <nav className="workspace-team-tabs" aria-label="팀 메뉴">
      <Link
        to={teamViewPath(team.id, 'space', from)}
        aria-current={active === 'space' ? 'page' : undefined}
      >
        팀 공간
      </Link>
      {team.owner && (
        <Link
          to={teamViewPath(team.id, 'applicants', from)}
          aria-current={active === 'applicants' ? 'page' : undefined}
        >
          지원자 관리
        </Link>
      )}
    </nav>
  );
}

function TeamOverview({
  team,
  currentPath,
}: {
  team: Team;
  currentPath: string;
}) {
  const contest = contests.find((item) => item.id === team.contestId);
  return (
    <div className="preview-stack">
      <section
        className="preview-panel preview-stack"
        aria-labelledby="team-goal-title"
      >
        <h2 id="team-goal-title">팀 목표</h2>
        <p>{team.summary}</p>
        {team.kind === 'preparation' && (
          <Alert role="note">
            <AlertDescription>
              함께 준비하는 팀이에요. 공모전 출전과 제출은 각자 진행해요.
            </AlertDescription>
          </Alert>
        )}
      </section>
      <section
        className="preview-panel preview-stack"
        aria-labelledby="team-roles-title"
      >
        <h2 id="team-roles-title">모집 정보</h2>
        <div className="preview-row">
          {team.roles.map((role) => (
            <Badge key={role}>{role}</Badge>
          ))}
        </div>
        <p className="preview-muted">안내한 역할과 달라도 지원할 수 있어요.</p>
        <dl className="workspace-detail-facts">
          <div>
            <dt>총 정원</dt>
            <dd>팀장 포함 총 {team.capacity}명</dd>
          </div>
          <div>
            <dt>현재 확정</dt>
            <dd>
              {team.members}명 · 남은 자리{' '}
              {Math.max(0, team.capacity - team.members)}명
            </dd>
          </div>
          <div>
            <dt>팀 모집 마감</dt>
            <dd>{team.recruitmentDeadline?.replaceAll('-', '.')}</dd>
          </div>
        </dl>
        {Boolean(team.interests?.length) && (
          <div className="preview-row">
            {team.interests.map((interest) => (
              <Badge key={interest}>{interest}</Badge>
            ))}
          </div>
        )}
      </section>
      {contest && (
        <section
          className="preview-panel preview-stack"
          aria-labelledby="team-contest-title"
        >
          <h2 id="team-contest-title">참여 공모전</h2>
          <h3>{contest.title}</h3>
          <p className="preview-inline-fact">
            {contest.status === 'closed' ? (
              '접수 마감됨'
            ) : (
              <>
                <span>접수 마감</span>
                <strong>{contest.deadline}</strong>
              </>
            )}
          </p>
          <ActionLink
            to={`${previewPath(`/contests/${contest.id}`)}?from=${encodeURIComponent(currentPath)}`}
            secondary
          >
            공모전 자세히 보기
          </ActionLink>
          <a
            className="workspace-text-link"
            href={contest.officialUrl}
            target="_blank"
            rel="noreferrer"
          >
            공식 원문 보기 <ExternalLink size={16} aria-hidden="true" />
          </a>
        </section>
      )}
    </div>
  );
}

function TeamSpace({
  team,
  from,
  currentPath,
  management,
}: {
  team: Team;
  from: string;
  currentPath: string;
  management: boolean;
}) {
  const { applicants, closeRecruitment, profile } = usePreview();
  const teamApplicants = applicants.filter(
    (applicant) => applicant.teamId === team.id,
  );
  const waiting = teamApplicants.filter((applicant) =>
    ['지원완료', '검토중'].includes(applicant.status),
  ).length;
  return (
    <div className="preview-detail preview-stack workspace-team-space">
      <BackLink to={from}>{returnLabel(from)}</BackLink>
      <PageIntro
        title={team.name}
        description={contests.find((item) => item.id === team.contestId)?.title}
      />
      <div className="preview-row">
        <Badge>{teamStatusLabel(team)}</Badge>
        <span className="preview-inline-fact">
          <span>내 역할</span>
          <strong>{team.owner ? '팀장' : '팀원'}</strong>
        </span>
        <span className="preview-inline-fact">
          <span>확정</span>
          <strong>
            {team.members} / {team.capacity}명
          </strong>
        </span>
      </div>
      <TeamTabs
        team={team}
        active={management ? 'applicants' : 'space'}
        from={from}
      />
      {management ? (
        <section
          className="preview-stack"
          aria-labelledby="team-applicants-title"
        >
          <div className="preview-section-title">
            <h2 id="team-applicants-title">지원자 관리</h2>
            <span className="preview-muted">검토 대기 {waiting}명</span>
          </div>
          {!teamApplicants.length ? (
            <p className="preview-panel preview-muted">
              아직 접수된 지원서가 없어요.
            </p>
          ) : (
            <ul className="workspace-applicant-list">
              {teamApplicants.map((applicant) => {
                const name = applicantVisibleProfile(applicant, profile).name;
                return (
                  <li key={applicant.id}>
                    <Link
                      to={previewPath(`/applicants/${applicant.id}`)}
                      aria-label={`${name} 지원서 검토`}
                      className="workspace-applicant-row"
                    >
                      <Avatar name={name} personId={applicant.personId} />
                      <div className="workspace-applicant-name">
                        <strong>{name}</strong>
                        <p className="preview-muted">{applicant.role} 지원</p>
                      </div>
                      <Badge>{applicationLabel(applicant.status)}</Badge>
                      <ChevronRight size={18} aria-hidden="true" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
          <p className="preview-muted">
            선발하면 즉시 팀원이 확정되고 남은 자리가 줄어요.
          </p>
        </section>
      ) : (
        <>
          <section
            className="preview-panel preview-stack"
            aria-labelledby="team-members-title"
          >
            <div className="preview-section-title">
              <h2 id="team-members-title">확정된 팀원</h2>
              <span className="preview-muted">{team.members}명</span>
            </div>
            <ul className="workspace-member-list">
              {team.memberProfiles?.map((member) => (
                <li key={member.id}>
                  <Avatar
                    name={member.id === 'me' ? profile.name : member.name}
                    personId={member.id}
                  />
                  <div>
                    <strong>
                      {member.id === 'me' ? profile.name : member.name}
                      {member.id === 'me' ? ' (나)' : ''}
                    </strong>
                    <p className="preview-muted">{member.role} · 교내 미인증</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <TeamOverview team={team} currentPath={currentPath} />
          {team.owner && !recruitmentIssue(team) && (
            <ConfirmAction
              title="팀 모집을 종료할까요?"
              description="새로운 지원을 받을 수 없게 돼요. 기존 지원 내역과 확정된 팀원은 유지돼요."
              confirmLabel="모집 종료하기"
              onConfirm={() => closeRecruitment(team.id)}
            >
              모집 종료
            </ConfirmAction>
          )}
          <ActionLink to={teamPath(team.id, workspacePath)} secondary>
            공개 모집글 보기
          </ActionLink>
        </>
      )}
    </div>
  );
}

export function TeamPage() {
  const { teamId } = useParams();
  const { teams, signedIn } = usePreview();
  const location = useLocation();
  const view = new URLSearchParams(location.search).get('view');
  const team = teams.find((item) => item.id === teamId);
  const from = returnPath(
    location.search,
    view ? workspacePath : previewPath('/explore?tab=teams'),
  );
  const currentPath = `${location.pathname}${location.search}`;
  if (!team)
    return (
      <div className="preview-detail preview-stack">
        <BackLink to={from}>{returnLabel(from)}</BackLink>
        <EmptyState
          title="팀을 찾을 수 없어요"
          description="목록으로 돌아가 다른 팀을 확인해 주세요."
        >
          <ActionLink to={from}>목록으로 돌아가기</ActionLink>
        </EmptyState>
      </div>
    );
  if (view === 'space' || view === 'applicants') {
    if (!signedIn)
      return (
        <div className="preview-detail preview-stack">
          <BackLink to={teamPath(team.id)}>공개 모집글로</BackLink>
          <LoginPrompt from={currentPath} />
        </div>
      );
    if (!isTeamMember(team) || (view === 'applicants' && !team.owner))
      return (
        <div className="preview-detail preview-stack">
          <BackLink to={teamPath(team.id)}>공개 모집글로</BackLink>
          <EmptyState
            title={
              view === 'applicants'
                ? '팀장만 지원서를 볼 수 있어요'
                : '현재 팀원만 팀 공간에 들어갈 수 있어요'
            }
            description="공개 모집글에서 팀의 모집 정보를 확인할 수 있어요."
          />
        </div>
      );
    return (
      <TeamSpace
        team={team}
        from={from}
        currentPath={currentPath}
        management={view === 'applicants'}
      />
    );
  }
  return (
    <TeamDetail
      key={team.id}
      team={team}
      from={from}
      currentPath={currentPath}
    />
  );
}

function TeamDetail({
  team,
  from,
  currentPath,
}: {
  team: Team;
  from: string;
  currentPath: string;
}) {
  const preview = usePreview();
  const currentPreview = useRef(preview);
  const active = useRef(false);
  const [completed, setCompleted] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const existingApplication = [...preview.applications]
    .reverse()
    .find(
      (application) =>
        application.teamId === team.id && application.status !== '지원취소',
    );
  const missing = missingProfileFields(preview.profile);
  const issue = recruitmentIssue(team);
  const {
    control,
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ApplicationFields>({
    resolver: zodResolver(applicationSchema),
    defaultValues: { role: '', message: '' },
  });
  useEffect(() => {
    currentPreview.current = preview;
  }, [preview]);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  async function submitApplication({ role, message }: ApplicationFields) {
    setSubmitError('');
    await new Promise<void>((resolve) => window.setTimeout(resolve, 350));
    if (!active.current) return;
    const latest = currentPreview.current;
    if (!latest.signedIn || !latest.apply(team.id, role, message)) {
      setSubmitError(
        '지원을 완료하지 못했어요. 로그인과 현재 모집 상태, 필수 프로필을 확인해 주세요.',
      );
      return;
    }
    setCompleted(true);
  }
  return (
    <div className="preview-detail preview-stack">
      <BackLink to={from}>{returnLabel(from)}</BackLink>
      <PageIntro
        title={team.name}
        description={contests.find((item) => item.id === team.contestId)?.title}
      />
      <div className="preview-row">
        <Badge>{teamStatusLabel(team)}</Badge>
        <span className="preview-muted">팀장 포함 총 {team.capacity}명</span>
      </div>
      <TeamOverview team={team} currentPath={currentPath} />
      <section
        className="preview-panel preview-stack preview-sticky-action"
        aria-labelledby="team-application-title"
      >
        <h2 id="team-application-title">팀 지원</h2>
        {!preview.signedIn ? (
          <>
            <p>로그인 후 지원할 수 있어요.</p>
            <ActionLink to={loginPath(currentPath)}>
              로그인하고 지원하기
            </ActionLink>
          </>
        ) : isTeamMember(team) ? (
          <>
            <p>이미 함께하고 있는 팀이에요.</p>
            <ActionLink to={teamViewPath(team.id, 'space', from)}>
              팀 공간으로
            </ActionLink>
          </>
        ) : completed ? (
          <>
            <Alert role="status">
              <CheckCircle2 size={24} aria-hidden="true" />
              <AlertTitle>지원이 완료됐어요</AlertTitle>
              <AlertDescription>
                내 지원에서 결과를 확인하세요.
              </AlertDescription>
            </Alert>
            <ActionLink to={applicationsPath}>내 지원 확인하기</ActionLink>
          </>
        ) : existingApplication ? (
          <>
            <Badge>{applicationLabel(existingApplication.status)}</Badge>
            <p>이미 {existingApplication.role} 역할로 지원한 팀이에요.</p>
            <ActionLink to={applicationsPath}>내 지원 확인하기</ActionLink>
          </>
        ) : issue ? (
          <>
            <p>{issue}</p>
            <ActionLink to={previewPath('/explore?tab=teams')} secondary>
              다른 팀 둘러보기
            </ActionLink>
          </>
        ) : missing.length ? (
          <>
            <Alert role="note">
              <AlertTitle>지원 전에 프로필을 완성해 주세요</AlertTitle>
              <AlertDescription>
                아직 입력하지 않은 정보: {missing.join(', ')}
              </AlertDescription>
            </Alert>
            <ActionLink
              to={`${previewPath('/profile')}?edit=details&returnTo=${encodeURIComponent(currentPath)}`}
            >
              프로필 보완하기
            </ActionLink>
            <p className="preview-muted">
              저장 후 이 팀으로 돌아와 지원할 수 있어요.
            </p>
          </>
        ) : (
          <form
            className="preview-form"
            onSubmit={(event) => void handleSubmit(submitApplication)(event)}
            noValidate
          >
            <fieldset className="preview-field" disabled={isSubmitting}>
              <legend id="application-role-label">지원할 역할</legend>
              <Controller
                name="role"
                control={control}
                render={({ field }) => (
                  <RadioGroup
                    name={field.name}
                    value={field.value}
                    onValueChange={field.onChange}
                    onBlur={field.onBlur}
                    disabled={isSubmitting}
                    aria-labelledby="application-role-label"
                    aria-invalid={Boolean(errors.role)}
                    aria-describedby={
                      errors.role ? 'application-role-error' : undefined
                    }
                  >
                    {roleOptions.map((role, index) => (
                      <Label
                        className="preview-choice"
                        htmlFor={`application-role-${index}`}
                        key={role}
                      >
                        <RadioGroupItem
                          id={`application-role-${index}`}
                          value={role}
                          ref={index === 0 ? field.ref : undefined}
                        />
                        <span>{role}</span>
                      </Label>
                    ))}
                  </RadioGroup>
                )}
              />
              {errors.role && (
                <p
                  id="application-role-error"
                  className="preview-error"
                  role="alert"
                >
                  {errors.role.message}
                </p>
              )}
            </fieldset>
            <div className="preview-field">
              <Label htmlFor="application-message">
                팀에 전할 말 <span className="preview-muted">선택</span>
              </Label>
              <p id="application-message-help" className="preview-muted">
                함께하고 싶은 이유나 맡고 싶은 일을 알려주세요. 최대 1,000자
              </p>
              <Textarea
                id="application-message"
                rows={4}
                maxLength={1000}
                {...register('message')}
                aria-describedby="application-message-help application-message-error"
                aria-invalid={!!errors.message}
                disabled={isSubmitting}
              />
              {errors.message && (
                <p
                  id="application-message-error"
                  className="preview-error"
                  role="alert"
                >
                  {errors.message.message}
                </p>
              )}
            </div>
            <Alert role="note">
              <AlertTitle>팀장에게 전달되는 정보</AlertTitle>
              <AlertDescription>
                이름, 희망 역할, 보유 역량, 팀에 전할 말과 공개한 프로필 항목이
                전달돼요. 비공개 관심 분야·경험·자기소개는 유지되고,
                포트폴리오는 프로필에서 공개한 경우에만 보여요.
              </AlertDescription>
            </Alert>
            {submitError && (
              <Alert variant="destructive" role="alert">
                <AlertDescription>{submitError}</AlertDescription>
              </Alert>
            )}
            <Button
              type="submit"
              className="preview-button"
              disabled={isSubmitting}
            >
              {isSubmitting ? (
                <>
                  <LoaderCircle size={18} aria-hidden="true" />
                  지원하는 중…
                </>
              ) : (
                <>
                  이 팀에 지원하기
                  <ArrowRight size={18} aria-hidden="true" />
                </>
              )}
            </Button>
          </form>
        )}
      </section>
    </div>
  );
}

export function ApplicantPage() {
  const { applicantId } = useParams();
  const { signedIn, applicants, teams } = usePreview();
  const location = useLocation();
  const applicant = applicants.find((item) => item.id === applicantId);
  const team = teams.find(
    (item) => item.id === applicant?.teamId && item.owner,
  );
  if (!signedIn)
    return (
      <div className="preview-detail preview-stack">
        <BackLink to={workspacePath}>워크스페이스로</BackLink>
        <LoginPrompt from={`${location.pathname}${location.search}`} />
      </div>
    );
  if (!applicant || !team)
    return (
      <div className="preview-detail preview-stack">
        <BackLink to={workspacePath}>워크스페이스로</BackLink>
        <EmptyState
          title="지원서를 확인할 수 없어요"
          description="내가 관리하는 팀에 접수된 지원서만 확인할 수 있어요."
        >
          <ActionLink to={workspacePath}>워크스페이스로 돌아가기</ActionLink>
        </EmptyState>
      </div>
    );
  return (
    <ApplicantDetail key={applicant.id} applicant={applicant} team={team} />
  );
}

function ApplicantDetail({
  applicant,
  team,
}: {
  applicant: Applicant;
  team: Team;
}) {
  const { selectApplicant, profile } = usePreview();
  const visible = applicantVisibleProfile(applicant, profile);
  const managementPath = teamViewPath(team.id, 'applicants');
  const pending = ['지원완료', '검토중'].includes(applicant.status);
  const scenario = selectionScenario(team);
  return (
    <div className="preview-detail preview-stack">
      <BackLink to={managementPath}>지원자 관리로</BackLink>
      <PageIntro
        title="지원서 검토"
        description={`${team.name} · ${applicant.role} 지원`}
      />
      <TeamTabs team={team} active="applicants" from={workspacePath} />
      <section
        className="preview-panel preview-stack"
        aria-labelledby="applicant-name"
      >
        <div className="preview-row">
          <Avatar
            name={visible.name}
            personId={applicant.personId}
            size="large"
          />
          <div>
            <h2 id="applicant-name">{visible.name}</h2>
            <p className="preview-muted">교내 미인증</p>
          </div>
          <Badge>{applicationLabel(applicant.status)}</Badge>
        </div>
        <dl className="preview-profile-facts">
          <div>
            <dt>희망 역할</dt>
            <dd className="preview-row">
              {visible.roles.map((role) => (
                <Badge key={role}>{role}</Badge>
              ))}
            </dd>
          </div>
          <div>
            <dt>보유 역량</dt>
            <dd className="preview-row">
              {visible.skills.length ? (
                visible.skills.map((skill) => (
                  <Badge key={skill}>{skill}</Badge>
                ))
              ) : (
                <p className="preview-muted">아직 입력하지 않았어요.</p>
              )}
            </dd>
          </div>
          {visible.interests !== undefined && (
            <div>
              <dt>관심 분야</dt>
              <dd className="preview-row">
                {visible.interests.map((interest) => (
                  <Badge key={interest}>{interest}</Badge>
                ))}
              </dd>
            </div>
          )}
          {visible.experience !== undefined && (
            <div>
              <dt>경험</dt>
              <dd className="preview-info-copy">{visible.experience}</dd>
            </div>
          )}
          {visible.intro !== undefined && (
            <div>
              <dt>자기소개</dt>
              <dd className="preview-info-copy">
                {visible.intro || '아직 입력하지 않았어요.'}
              </dd>
            </div>
          )}
          {visible.portfolio && (
            <div>
              <dt>포트폴리오</dt>
              <dd>
                <a
                  className="workspace-text-link"
                  href={visible.portfolio}
                  target="_blank"
                  rel="noreferrer"
                >
                  {visible.portfolioTitle || '포트폴리오 열기'}
                  <ExternalLink size={16} aria-hidden="true" />
                </a>
                <p className="preview-muted">
                  외부 사이트로 이동해요. 링크가 열리지 않으면 지원자에게 공개
                  설정을 확인해 주세요.
                </p>
              </dd>
            </div>
          )}
        </dl>
        <p className="preview-muted">
          현재 공개한 정보만 보여요. 개인 일정과 이메일은 표시하지 않아요.
        </p>
      </section>
      <section
        className="preview-panel preview-stack"
        aria-labelledby="applicant-message-title"
      >
        <div className="preview-row">
          <FileText size={20} aria-hidden="true" />
          <h2 id="applicant-message-title">팀에 전한 말</h2>
        </div>
        <p>{applicant.message || '작성한 메시지가 없어요.'}</p>
      </section>
      {pending && scenario === 'ready' && (
        <section
          className="preview-panel preview-stack"
          aria-labelledby="applicant-recommendation-title"
        >
          <div className="preview-row">
            <Sparkles size={20} aria-hidden="true" />
            <h2 id="applicant-recommendation-title">AI 검토 도움</h2>
          </div>
          <p>
            {applicant.id === 'app-seoyeon'
              ? '개발 역할을 희망하고, 지원서에서 환경 문제를 해결하는 서비스에 대한 관심을 밝혔어요. 팀의 기술 구현을 함께 이야기해 보세요.'
              : applicant.id === 'app-sua'
                ? '지원서에서 사용자 리서치와 화면 설계에 참여하고 싶다고 밝혔어요. 팀이 해결할 문제를 함께 구체화해 보세요.'
                : '지원서의 희망 역할과 팀에 전한 말을 바탕으로 함께할 방향을 확인해 보세요.'}
          </p>
          <p className="preview-muted">
            추천 이유를 참고하고, 최종 선발은 팀장이 판단해요.
          </p>
        </section>
      )}
      <section
        className="preview-panel preview-stack preview-sticky-action"
        aria-labelledby="applicant-decision-title"
      >
        <h2 id="applicant-decision-title">검토 결과</h2>
        {applicant.status === '선발' ? (
          <>
            <Alert role="status">
              <CheckCircle2 size={24} aria-hidden="true" />
              <AlertTitle>{visible.name} 님이 팀원으로 확정됐어요</AlertTitle>
              <AlertDescription>
                팀 공간에서 확정된 팀원과 남은 자리를 확인할 수 있어요.
              </AlertDescription>
            </Alert>
            <ActionLink to={teamViewPath(team.id, 'space')}>
              팀 공간으로
            </ActionLink>
            <ActionLink to={managementPath} secondary>
              지원자 관리로 돌아가기
            </ActionLink>
          </>
        ) : pending ? (
          <>
            <div className="preview-row">
              <span className="preview-inline-fact">
                <span>현재</span>
                <strong>{team.members}명</strong>
              </span>
              <span className="preview-inline-fact">
                <span>남은 자리</span>
                <strong>{Math.max(0, team.capacity - team.members)}명</strong>
              </span>
            </div>
            {scenario !== 'ready' ? (
              <p className="preview-muted">
                {scenario === 'full'
                  ? '팀 정원이 모두 찼어요.'
                  : '지원서가 접수되어 있어요.'}
              </p>
            ) : (
              <ConfirmAction
                title={`${visible.name} 님을 선발할까요?`}
                description="선발하면 즉시 팀원이 확정되고 남은 자리가 한 자리 줄어요. 별도의 수락 단계는 없어요."
                confirmLabel="선발하고 팀원 확정"
                onConfirm={() => selectApplicant(applicant.id)}
              >
                이 지원자 선발하기
                <ArrowRight size={18} aria-hidden="true" />
              </ConfirmAction>
            )}
          </>
        ) : (
          <p>
            {applicant.status === '지원취소'
              ? '지원자가 지원을 취소했어요.'
              : '미선발된 지원서예요.'}
          </p>
        )}
      </section>
    </div>
  );
}
