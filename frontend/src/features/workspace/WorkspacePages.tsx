/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/WorkspacePages.tsx - 워크스페이스·공개 모집글·팀 공간·지원자 관리·지원자 검토 원본
 * 2. docs/design/screens.md - 워크스페이스·내 지원·팀 공간·지원자 관리 경로와 완료 조건
 * 3. docs/design/tokens.md - 「모바일 상호작용 확인」 내 지원(ClipboardList)·팀 만들기(Plus) 44px, 팀 카드 전체 링크
 * 4. docs/specs/team-recruitment.md#acceptance-criteria - 지원·선발·취소·재지원·폐기·재개
 * 5. docs/specs/profile.md#visibility - 신규 지원은 공개 상태에서만, 지원받은 팀장의 현재 프로필 열람
 * 6. docs/design/assets/workspace-390.png, applications-390.png, members-390.png, selection-390.png, applicant-profile-390.png, application-discarded-390.png, recruitment-reopen-confirm-320.png - 실제 화면
 */

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
  RotateCcw,
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
import type {
  Application,
  ApplicationStatus,
} from '@/features/applications/api';
import type { TeamDetail, TeamMember } from '@/features/teams/api';
import { fieldLabel, roleLabel, roleOptions } from '@/features/demo/labels';
import {
  ActionLink,
  Avatar,
  BackLink,
  Badge,
  EmptyState,
  PageIntro,
  SchoolVerificationBadge,
  TeamStatusBadge,
} from '@/components/common/CommonUi';
import { ProfileDetails } from '@/components/common/ProfileDetails';
import { ProfileVisibilityControl } from '@/features/account/AccountPages';
import { ApplicantReview } from '@/features/teams/ApplicantReview';
import { contestStatus, deadlineLabel } from '@/features/demo/contest-state';
import { useDemo } from '@/features/demo/demo-context';
import {
  missingProfileFields,
  profileTextLength,
} from '@/features/demo/profile-fields';
import {
  applicantVisibleProfile,
  isPending,
  isTeamMember,
  isTeamOwner,
  recruitmentIssue,
  recruitmentReopeningIssue,
  selectionScenario,
} from '@/features/demo/team-state';

const workspacePath = '/workspace';
const applicationsPath = `${workspacePath}?view=applications`;
const applicationSchema = z.object({
  role: z.string().min(1, '지원할 역할을 선택해 주세요.'),
  message: z
    .string()
    .trim()
    .refine(
      (value) => profileTextLength(value) <= 1000,
      '팀에 전할 말은 1,000자까지 입력할 수 있어요.',
    ),
});
type ApplicationFields = z.infer<typeof applicationSchema>;

function returnPath(search: string, fallback: string) {
  const from = new URLSearchParams(search).get('from');
  if (!from || /[\\\r\n]/.test(from)) return fallback;
  // 앱 내부 경로만 허용하고 프로토콜 상대 주소(//)는 기본 경로로 돌립니다.
  if (from === '/') return '/explore';
  return from.startsWith('/') && !from.startsWith('//') ? from : fallback;
}
function loginPath(from: string) {
  return `/login?returnTo=${encodeURIComponent(from)}`;
}
function teamPath(id: string, from = workspacePath) {
  return `${`/teams/${id}`}?from=${encodeURIComponent(from)}`;
}
function teamViewPath(
  id: string,
  view: 'space' | 'applicants',
  from = workspacePath,
) {
  return `${`/teams/${id}`}?${new URLSearchParams({ view, from }).toString()}`;
}
function returnLabel(path: string) {
  if (path === '/ai') return 'AI 대화로';
  if (path === '/explore') return '탐색으로';
  if (path === applicationsPath) return '내 지원으로';
  if (path.split('?')[0] === workspacePath) return '워크스페이스로';
  return '목록으로';
}
// [출처 4] ApplicationStatus 표시 문구
function applicationLabel(status: ApplicationStatus) {
  return {
    submitted: '지원 완료',
    reviewing: '검토 중',
    selected: '선발 · 팀원 확정',
    rejected: '미선발',
    canceled: '지원 취소',
    discarded: '폐기',
  }[status];
}
// [출처 4] 폐기 사유(discardReason)별 안내. 자동 복원 없음
function discardMessage(application: Application) {
  return application.discardReason === 'team_created_elsewhere'
    ? '같은 공모전에서 직접 팀을 만들어 이 지원은 폐기됐어요.'
    : '같은 공모전의 다른 팀에서 선발되어 이 지원은 폐기됐어요.';
}
// 소속 표시: 팀장은 공개된 희망 역할을, 팀원은 선발된 지원 역할을 함께 보여줌
function memberRole(member: TeamMember) {
  if (member.membershipRole === 'member')
    return member.roleCode ? roleLabel(member.roleCode) : '팀원';
  const preferred = member.profile?.roleCodes[0];
  return preferred ? `팀장 · ${roleLabel(preferred)}` : '팀장';
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

// [출처 2, 3, 6] 내 팀·내 지원, 빈 상태
export function WorkspacePage() {
  const {
    signedIn,
    teams,
    applications: allApplications,
    account,
    db,
    cancelApplication,
  } = useDemo();
  const location = useLocation();
  const showApplications =
    new URLSearchParams(location.search).get('view') === 'applications';
  // [출처 4] 내 지원은 본인 지원만, 최신 접수순(submittedAt DESC, id DESC)
  const applications = allApplications
    .filter((item) => item.applicantAccountId === account.id)
    .sort(
      (left, right) =>
        right.submittedAt.localeCompare(left.submittedAt) ||
        right.id.localeCompare(left.id),
    );
  const myTeams = teams.filter((team) => isTeamMember(db, team.id, account.id));
  if (!signedIn)
    return (
      <div className="workspace-page preview-stack">
        <h1 className="sr-only">워크스페이스</h1>
        <LoginPrompt
          from={showApplications ? applicationsPath : workspacePath}
        />
      </div>
    );
  return (
    <div className="workspace-page preview-stack">
      <h1 className="sr-only">워크스페이스</h1>
      <header className="workspace-heading">
        <div className="workspace-section-summary">
          <h2
            id={
              showApplications
                ? 'workspace-applications-title'
                : 'workspace-teams-title'
            }
          >
            {showApplications ? '내 지원' : '내 팀'}
          </h2>
          <span className="preview-muted">
            {showApplications
              ? `${applications.length}건`
              : `${myTeams.length}개`}
          </span>
        </div>
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
            <Link to="/teams/new" aria-label="팀 만들기" title="팀 만들기">
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
          {!applications.length ? (
            <EmptyState
              title="아직 지원한 팀이 없어요"
              description="함께할 팀을 찾아 지원해 보세요."
            >
              <ActionLink to="/explore?tab=teams" secondary>
                팀 둘러보기
              </ActionLink>
            </EmptyState>
          ) : (
            <ul className="workspace-application-list">
              {applications.map((application) => {
                const team = teams.find(
                  (item) => item.id === application.teamId,
                );
                const selected = application.status === 'selected';
                const member = !!team && isTeamMember(db, team.id, account.id);
                const cancellable = [
                  'submitted',
                  'reviewing',
                  'selected',
                ].includes(application.status);
                return (
                  <li
                    key={application.id}
                    className="preview-panel preview-stack"
                  >
                    <div className="preview-split">
                      <div>
                        <h3>{team?.name ?? '팀 정보 없음'}</h3>
                        <p className="preview-muted">
                          {roleLabel(application.roleCode)} 지원
                        </p>
                      </div>
                      <Badge tone={selected ? 'lime' : 'neutral'}>
                        {applicationLabel(application.status)}
                      </Badge>
                    </div>
                    <p className="preview-muted">{team?.contestTitle}</p>
                    <details className="workspace-application-message group">
                      <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring">
                        <span>내가 전한 말</span>
                        <ChevronRight
                          size={18}
                          aria-hidden="true"
                          className="group-open:rotate-90"
                        />
                      </summary>
                      <p className="whitespace-pre-wrap break-words">
                        {application.message || '작성한 메시지가 없어요.'}
                      </p>
                    </details>
                    {selected && (
                      <p>
                        선발되어 팀원이 됐어요. 팀 공간에서 함께할 멤버를
                        확인하세요.
                      </p>
                    )}
                    {application.status === 'canceled' && (
                      <p className="preview-muted">
                        지원이 취소됐어요. 현재 모집 조건이 맞으면 다시 지원할
                        수 있어요.
                      </p>
                    )}
                    {application.status === 'discarded' && (
                      <p className="preview-muted">
                        {discardMessage(application)} 이후 참여를 취소해도
                        자동으로 복원되지 않아요.
                      </p>
                    )}
                    {team && (
                      <>
                        <ActionLink
                          to={
                            selected && member
                              ? teamViewPath(team.id, 'space', applicationsPath)
                              : teamPath(team.id, applicationsPath)
                          }
                          secondary
                        >
                          {selected && member
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
                            onConfirm={() =>
                              cancelApplication(application.id).ok
                            }
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
          {!myTeams.length ? (
            <EmptyState
              title="함께할 첫 팀을 찾아보세요"
              description="팀을 만들거나 관심 있는 팀에 지원해 보세요."
            >
              <ActionLink to="/explore?tab=teams">팀 둘러보기</ActionLink>
            </EmptyState>
          ) : (
            <div className="workspace-team-grid">
              {myTeams.map((team) => {
                const owner = isTeamOwner(team, account.id);
                const pending = allApplications.filter(
                  (item) => item.teamId === team.id && isPending(item),
                ).length;
                return (
                  <Link
                    key={team.id}
                    to={teamViewPath(team.id, 'space')}
                    className="preview-card workspace-team-card"
                    aria-label={`${team.name} 팀 공간으로`}
                  >
                    <div className="preview-split">
                      <TeamStatusBadge team={team} />
                      {owner && pending > 0 && (
                        <span className="workspace-pending">
                          검토 대기 {pending}명
                        </span>
                      )}
                    </div>
                    <h3>{team.name}</h3>
                    <p className="workspace-team-contest">
                      {team.contestTitle}
                    </p>
                    <div className="workspace-team-summary">
                      <dl className="workspace-team-facts">
                        <div>
                          <dt>내 역할</dt>
                          <dd>{owner ? '팀장' : '팀원'}</dd>
                        </div>
                        <div>
                          <dt>확정 인원</dt>
                          <dd>
                            {team.memberCount} / {team.capacity}명
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
  team: TeamDetail;
  active: 'space' | 'applicants';
  from: string;
}) {
  const { account } = useDemo();
  return (
    <nav className="workspace-team-tabs" aria-label="팀 메뉴">
      <Link
        to={teamViewPath(team.id, 'space', from)}
        aria-current={active === 'space' ? 'page' : undefined}
      >
        팀 공간
      </Link>
      {isTeamOwner(team, account.id) && (
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
  team: TeamDetail;
  currentPath: string;
}) {
  const { contests } = useDemo();
  const contest = contests.find((item) => item.id === team.contestId);
  return (
    <div className="preview-stack">
      <section
        className="preview-panel preview-stack"
        aria-labelledby="team-goal-title"
      >
        <h2 id="team-goal-title">팀 목표</h2>
        <p>{team.introduction}</p>
      </section>
      <section
        className="preview-panel preview-stack"
        aria-labelledby="team-roles-title"
      >
        <h2 id="team-roles-title">모집 정보</h2>
        <div className="preview-row">
          {team.roleCodes.map((code) => (
            <Badge key={code}>{roleLabel(code)}</Badge>
          ))}
        </div>
        {Number(team.capacity) > 1 ? (
          <p className="preview-muted">
            안내한 역할과 달라도 지원할 수 있어요.
          </p>
        ) : (
          <p className="preview-muted">
            1명으로 참가하는 팀으로 추가 모집하지 않아요.
          </p>
        )}
        <dl className="workspace-detail-facts">
          <div>
            <dt>총 정원</dt>
            <dd>팀장 포함 총 {team.capacity}명</dd>
          </div>
          <div>
            <dt>현재 확정</dt>
            <dd>
              {team.memberCount}명 · 남은 자리{' '}
              {Math.max(0, Number(team.capacity) - team.memberCount)}명
            </dd>
          </div>
          <div>
            <dt>팀 모집 마감</dt>
            <dd>{team.recruitmentDeadline.sourceDate.replaceAll('-', '.')}</dd>
          </div>
        </dl>
        {team.fieldCodes.length > 0 && (
          <div className="preview-row">
            {team.fieldCodes.map((code) => (
              <Badge key={code}>{fieldLabel(code)}</Badge>
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
            {contestStatus(contest) === 'closed' ? (
              '접수 마감됨'
            ) : (
              <>
                <span>접수 마감</span>
                <strong>{deadlineLabel(contest.timing.closing)}</strong>
              </>
            )}
          </p>
          <ActionLink
            to={`${`/contests/${contest.id}`}?from=${encodeURIComponent(currentPath)}`}
            secondary
          >
            공모전 자세히 보기
          </ActionLink>
          <a
            className="workspace-text-link"
            href={contest.sourceUrl}
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

function RecruitmentControl({ team }: { team: TeamDetail }) {
  const { closeRecruitment, reopenRecruitment, account } = useDemo();
  const [feedback, setFeedback] = useState('');
  if (!isTeamOwner(team, account.id)) return null;
  const closed = team.recruitmentState === 'closed';
  const issue = recruitmentReopeningIssue(team, account.id);
  return (
    <section className="preview-stack" aria-label="모집 관리">
      {closed ? (
        issue ? (
          <>
            <Button
              className="preview-button"
              variant="outline"
              disabled
              aria-describedby="recruitment-reopening-issue"
            >
              <RotateCcw size={18} aria-hidden="true" /> 다시 모집하기
            </Button>
            <p id="recruitment-reopening-issue" className="preview-muted">
              {issue}
            </p>
          </>
        ) : (
          <ConfirmAction
            title="모집을 다시 시작할까요?"
            description="새로운 지원을 다시 받을 수 있어요. 기존 지원과 확정된 팀원은 유지되고, 폐기된 지원은 복원되지 않아요."
            confirmLabel="모집 중으로 변경"
            onConfirm={() => {
              if (!reopenRecruitment(team.id).ok) return false;
              setFeedback(
                '모집을 다시 시작했어요. 새로운 지원을 받을 수 있어요.',
              );
              return true;
            }}
          >
            <RotateCcw size={18} aria-hidden="true" /> 다시 모집하기
          </ConfirmAction>
        )
      ) : !recruitmentIssue(team) ? (
        <ConfirmAction
          title="팀 모집을 종료할까요?"
          description="새로운 지원을 받을 수 없게 돼요. 기존 지원과 팀원은 유지돼요. 기한과 정원 조건이 맞으면 직접 모집을 다시 시작할 수 있어요."
          confirmLabel="모집 종료하기"
          onConfirm={() => {
            if (!closeRecruitment(team.id).ok) return false;
            setFeedback(
              '모집을 종료했어요. 기존 지원과 확정된 팀원은 유지돼요.',
            );
            return true;
          }}
        >
          모집 종료
        </ConfirmAction>
      ) : null}
      {feedback && (
        <p role="status" className="preview-muted">
          {feedback}
        </p>
      )}
    </section>
  );
}

function TeamSpace({
  team,
  from,
  currentPath,
  management,
}: {
  team: TeamDetail;
  from: string;
  currentPath: string;
  management: boolean;
}) {
  const { applications, account, db, teamMembers } = useDemo();
  const owner = isTeamOwner(team, account.id);
  // [출처 4] 팀장이 받은 지원(최신 접수순)
  const teamApplicants = applications
    .filter((application) => application.teamId === team.id)
    .sort(
      (left, right) =>
        right.submittedAt.localeCompare(left.submittedAt) ||
        right.id.localeCompare(left.id),
    );
  const waiting = teamApplicants.filter(isPending).length;
  const members = teamMembers(team.id);
  return (
    <div className="preview-detail preview-stack workspace-team-space">
      <BackLink to={from}>{returnLabel(from)}</BackLink>
      <PageIntro title={team.name} description={team.contestTitle} />
      <div className="preview-row">
        <TeamStatusBadge team={team} />
        <span className="preview-inline-fact">
          <span>내 역할</span>
          <strong>{owner ? '팀장' : '팀원'}</strong>
        </span>
        <span className="preview-inline-fact">
          <span>확정</span>
          <strong>
            {team.memberCount} / {team.capacity}명
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
                const applicantProfile = applicantVisibleProfile(db, applicant);
                const name = applicantProfile?.realName ?? '';
                return (
                  <li key={applicant.id}>
                    <Link
                      to={`/applicants/${applicant.id}`}
                      aria-label={`${name} 지원서 검토`}
                      className="workspace-applicant-row"
                    >
                      <Avatar
                        name={name}
                        accountId={applicant.applicantAccountId}
                        imageCode={applicantProfile?.profileImageCode ?? null}
                      />
                      <div className="workspace-applicant-name">
                        <strong>{name}</strong>
                        <p className="preview-muted">
                          {roleLabel(applicant.roleCode)} 지원
                        </p>
                        {applicant.status === 'discarded' && (
                          <p className="preview-muted">
                            {applicant.discardReason ===
                            'team_created_elsewhere'
                              ? '같은 공모전에서 직접 팀을 만듦'
                              : '같은 공모전의 다른 팀에서 선발됨'}
                          </p>
                        )}
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
              <span className="preview-muted">{team.memberCount}명</span>
            </div>
            <ul className="workspace-member-list">
              {/* [출처 4] 소속 표시와 프로필 열람 분리: 비공개 팀원의 사진은 보이지 않음(profile=null) */}
              {members.map((member) => (
                <li key={member.membershipId}>
                  <Avatar
                    name={member.realName}
                    accountId={member.accountId}
                    imageCode={member.profile?.profileImageCode ?? null}
                  />
                  <div>
                    <strong>
                      {member.realName}
                      {member.accountId === account.id ? ' (나)' : ''}
                    </strong>
                    <p className="preview-muted">
                      {memberRole(member)} · 교내 미인증
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
          <TeamOverview team={team} currentPath={currentPath} />
          <ActionLink to={teamPath(team.id, workspacePath)} secondary>
            공개 모집글 보기
          </ActionLink>
        </>
      )}
      <RecruitmentControl team={team} />
    </div>
  );
}

// [출처 2, 4, 5, 6] 공개 모집글·팀 공간·지원자 관리(view 파라미터)
export function TeamPage() {
  const { teamId } = useParams();
  const { teams, signedIn, account, db } = useDemo();
  const location = useLocation();
  const view = new URLSearchParams(location.search).get('view');
  const team = teams.find((item) => item.id === teamId);
  const from = returnPath(
    location.search,
    view ? workspacePath : '/explore?tab=teams',
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
    if (
      !isTeamMember(db, team.id, account.id) ||
      (view === 'applicants' && !isTeamOwner(team, account.id))
    )
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
    <TeamRecruitmentDetail
      key={team.id}
      team={team}
      from={from}
      currentPath={currentPath}
    />
  );
}

function TeamRecruitmentDetail({
  team,
  from,
  currentPath,
}: {
  team: TeamDetail;
  from: string;
  currentPath: string;
}) {
  const preview = useDemo();
  const currentPreview = useRef(preview);
  const active = useRef(false);
  const [completed, setCompleted] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const me = preview.account.id;
  // 이 팀에 대한 본인의 최신 유효 기록(취소 제외)
  const existingApplication = preview.applications
    .filter(
      (application) =>
        application.teamId === team.id &&
        application.applicantAccountId === me &&
        application.status !== 'canceled',
    )
    .sort((left, right) =>
      right.submittedAt.localeCompare(left.submittedAt),
    )[0];
  const member = isTeamMember(preview.db, team.id, me);
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
    if (!latest.signedIn || !latest.apply(team.id, role, message).ok) {
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
      <PageIntro title={team.name} description={team.contestTitle} />
      <div className="preview-row">
        <TeamStatusBadge team={team} />
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
        ) : member ? (
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
            <p>
              {existingApplication.status === 'discarded'
                ? discardMessage(existingApplication)
                : `이미 ${roleLabel(existingApplication.roleCode)} 역할로 지원한 팀이에요.`}
            </p>
            <ActionLink to={applicationsPath}>내 지원 확인하기</ActionLink>
          </>
        ) : issue ? (
          <>
            <p>{issue}</p>
            <ActionLink to="/explore?tab=teams" secondary>
              다른 팀 둘러보기
            </ActionLink>
          </>
        ) : missing.length ? (
          <>
            <Alert role="note">
              <AlertTitle>지원 전에 프로필을 완성해 주세요</AlertTitle>
              <AlertDescription>
                보완이 필요한 정보: {missing.join(', ')}
              </AlertDescription>
            </Alert>
            <ActionLink
              to={`/profile?edit=details&returnTo=${encodeURIComponent(currentPath)}`}
            >
              프로필 보완하기
            </ActionLink>
            <p className="preview-muted">
              저장 후 이 팀으로 돌아와 지원할 수 있어요.
            </p>
          </>
        ) : !preview.profile.isPublic ? (
          <>
            <Alert role="note">
              <AlertTitle>프로필을 공개한 뒤 지원할 수 있어요</AlertTitle>
              <AlertDescription>
                공개하면 사람 검색과 AI 사람 추천에서 등록한 프로필을 볼 수
                있어요. 공개 전환 후 지원할 역할과 메시지를 작성해 주세요.
              </AlertDescription>
            </Alert>
            <ProfileVisibilityControl
              checked={false}
              triggerLabel="프로필 공개하기"
              onConfirm={(isPublic) =>
                preview.saveProfile({
                  ...preview.profile,
                  isPublic,
                  version: (BigInt(preview.profile.version) + 1n).toString(),
                })
              }
            />
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
                        key={role.code}
                      >
                        <RadioGroupItem
                          id={`application-role-${index}`}
                          value={role.code}
                          ref={index === 0 ? field.ref : undefined}
                        />
                        <span>{role.displayName}</span>
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
                지원받은 팀장은 등록한 전체 프로필과 팀에 전할 말을 확인하고 AI
                검토에 최신 프로필을 사용할 수 있어요. 이후 프로필을 비공개로
                바꾸어도 기존 지원과 해당 팀장의 검토는 유지돼요.
              </AlertDescription>
            </Alert>
            <p className="preview-muted">
              참가 자격은 공모전 원문에서 확인해 주세요. 학적·학년·전공으로
              지원을 제한하지 않으며, 접수 완료가 참가 자격을 보장하지는 않아요.
            </p>
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

// [출처 4, 5, 6] 해당 팀장만 전체 현재 프로필 확인
export function ApplicantPage() {
  const { applicantId } = useParams();
  const { signedIn, applications, teams, account } = useDemo();
  const location = useLocation();
  const applicant = applications.find((item) => item.id === applicantId);
  // [출처 5] 해당 지원을 받은 팀장만
  const team = teams.find(
    (item) => item.id === applicant?.teamId && isTeamOwner(item, account.id),
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
  applicant: Application;
  team: TeamDetail;
}) {
  const { selectApplicant, signedIn, db, account } = useDemo();
  // [출처 5] 지원 당시 사본이 아닌 현재 전체 프로필
  const visible = applicantVisibleProfile(db, applicant)!;
  const managementPath = teamViewPath(team.id, 'applicants');
  const pending = isPending(applicant);
  const scenario = selectionScenario(team);
  return (
    <div className="preview-detail preview-stack">
      <BackLink to={managementPath}>지원자 관리로</BackLink>
      <PageIntro
        title="지원서 검토"
        description={`${team.name} · ${roleLabel(applicant.roleCode)} 지원`}
      />
      <TeamTabs team={team} active="applicants" from={workspacePath} />
      <section
        className="preview-panel preview-stack"
        aria-labelledby="applicant-name"
      >
        <div className="preview-row">
          <Avatar
            name={visible.realName}
            accountId={visible.accountId}
            imageCode={visible.profileImageCode}
            size="large"
          />
          <div>
            <h2 id="applicant-name">{visible.realName}</h2>
            <SchoolVerificationBadge />
          </div>
          <Badge>{applicationLabel(applicant.status)}</Badge>
        </div>
        <ProfileDetails profile={visible} />
        <p className="preview-muted">
          지원받은 팀장에게는 공개 설정과 관계없이 등록한 전체 프로필이 보여요.
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
      <ApplicantReview
        application={applicant}
        profile={visible}
        mayReviewExistingApplication={
          signedIn &&
          isTeamOwner(team, account.id) &&
          applicant.teamId === team.id
        }
      />

      <section
        className="preview-panel preview-stack preview-sticky-action"
        aria-labelledby="applicant-decision-title"
      >
        <h2 id="applicant-decision-title">검토 결과</h2>
        {applicant.status === 'selected' ? (
          <>
            <Alert role="status">
              <CheckCircle2 size={24} aria-hidden="true" />
              <AlertTitle>
                {visible.realName} 님이 팀원으로 확정됐어요
              </AlertTitle>
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
                <strong>{team.memberCount}명</strong>
              </span>
              <span className="preview-inline-fact">
                <span>남은 자리</span>
                <strong>
                  {Math.max(0, Number(team.capacity) - team.memberCount)}명
                </strong>
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
                title={`${visible.realName} 님을 선발할까요?`}
                description="선발하면 즉시 팀원이 확정돼요. 이 지원자가 같은 공모전의 다른 팀에 낸 대기 지원은 폐기되며, 나중에 팀 참여를 취소해도 복원되지 않아요."
                confirmLabel="선발하고 팀원 확정"
                onConfirm={() => selectApplicant(applicant.id).ok}
              >
                이 지원자 선발하기
                <ArrowRight size={18} aria-hidden="true" />
              </ConfirmAction>
            )}
          </>
        ) : (
          <p>
            {applicant.status === 'canceled'
              ? '지원자가 지원을 취소했어요.'
              : applicant.status === 'discarded'
                ? applicant.discardReason === 'team_created_elsewhere'
                  ? '같은 공모전에서 지원자가 직접 팀을 만들어 폐기된 지원이에요. 지원 기록은 남지만 선발 대상에서는 제외돼요.'
                  : '같은 공모전의 다른 팀에서 선발되어 폐기된 지원이에요. 지원 기록은 남지만 선발 대상에서는 제외돼요.'
                : '미선발된 지원서예요.'}
          </p>
        )}
      </section>
    </div>
  );
}
