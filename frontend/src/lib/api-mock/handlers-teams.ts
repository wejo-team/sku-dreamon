/**
 * [참조 출처]
 * 1. docs/api/teams.md#endpoints, #queries - 팀 탐색·생성·워크스페이스, 검색 대상과 정렬 createdAt DESC, id DESC
 * 2. docs/api/teams.md#team-create - 생성 트랜잭션: 팀·팀장 소속, 같은 공모전 본인 대기 지원 폐기
 * 3. docs/api/teams.md#team-member - 프로필은 본인·공개·지원받은 팀장에게만
 * 4. docs/api/teams.md#transitions - 모집 종료·재개 전이, 버전 먼저 비교, no-op 200
 * 5. docs/api/applications.md#endpoints - 지원 9개 API, 관계 밖 404·행동 권한 403
 * 6. docs/api/applications.md#transitions - 검토 시작·미선발·선발·취소 전이와 no-op 200
 * 7. docs/api/applications.md#application - 원인 ID는 본인에게만, 받은 팀장에게는 null
 * 8. docs/api/conventions.md#errors - 업무 코드별 HTTP 상태(401·403·404·409·422)
 *
 * 상태 전이 규칙은 화면과 같은 features/demo/team-state를 사용하고, 여기서는 HTTP 계약(버전·재전송·no-op·상태 코드)만 담당합니다.
 */

import {
  ApplicationCreate,
  ApplicationStatus,
  type Application,
} from '@/features/applications/api';
import { TeamCreate } from '@/features/teams/api';
import { toTeamSummary } from '@/features/demo/fixtures';
import {
  appendNotifications,
  transitionNotifications,
} from '@/features/demo/notification-state';
import {
  applyToTeam,
  cancelTeamApplication,
  closeTeamRecruitment,
  createDemoTeam,
  hasMembershipInContest,
  isPending,
  rejectTeamApplicant,
  reopenTeamRecruitment,
  selectTeamApplicant,
  startApplicantReview,
  teamMembers,
  type Transition,
} from '@/features/demo/team-state';
import { CatalogCode, Id, VersionedAction } from '@/lib/api-contract';
import {
  MockRouter,
  booleanQuery,
  fail,
  forbidden,
  invalid,
  notFound,
  ok,
  paginate,
  searchText,
  validate,
} from '@/lib/api-mock/http';
import {
  pageResponse,
  parseOptionalQuery,
} from '@/lib/api-mock/handlers-account';
import {
  assertVersion,
  contestById,
  db,
  idempotent,
  isCurrentMember,
  newId,
  nowIso,
  profileOf,
  requireSession,
  state,
  teamById,
  teamRecord,
  teamSummary,
} from '@/lib/api-mock/state';

// [출처 8] 업무 코드 → HTTP 상태
const STATUS: Record<string, number> = {
  RESOURCE_NOT_FOUND: 404,
  FORBIDDEN: 403,
  UNAUTHENTICATED: 401,
  VALIDATION_ERROR: 422,
};

// 전이를 적용하고 그 변경의 알림을 함께 기록합니다. 실패는 같은 코드로 응답합니다.
function commit(transition: Transition) {
  if ('error' in transition) {
    const { code, message } = transition.error;
    // [출처 8] 422 loc에는 요청 필드 이름을 넣습니다(docs/api/conventions.md#errors)
    if (code === 'VALIDATION_ERROR')
      invalid(
        ['body', ...(transition.error.field ? [transition.error.field] : [])],
        message,
      );
    fail(STATUS[code] ?? 409, code, message);
  }
  const next = (transition as { db: typeof state.db }).db;
  const additions = transitionNotifications(
    state.db,
    next,
    `mock-${++state.sequence}`,
    nowIso(),
  );
  state.db = {
    ...next,
    notifications: appendNotifications(next.notifications, additions),
  };
}

// scope: 특정 공모전의 팀(contest) 또는 전체 팀(all). 전체 팀 검색만 공모전명 포함(출처 1)
function teamList(
  query: URLSearchParams,
  contestId: string | null,
  scope: 'contest' | 'all',
) {
  const q = searchText(query);
  const roleCode = parseOptionalQuery(
    CatalogCode,
    query.get('roleCode'),
    'roleCode',
  );
  const recruitingOnly = booleanQuery(query, 'recruitingOnly');
  const roleName = (code: string) =>
    db().catalogs.roles.find((item) => item.code === code)?.displayName ?? '';
  const items = db()
    .teams.map((record) => teamById(record.id)!)
    .filter((team) => !contestId || team.contestId === contestId)
    .filter((team) => !roleCode || team.roleCodes.includes(roleCode))
    .filter((team) => !recruitingOnly || team.isRecruiting)
    .filter(
      (team) =>
        !q ||
        [
          team.name,
          team.introduction,
          ...team.roleCodes.map(roleName),
          // [출처 1] 전체 팀 검색(GET /teams, contestId 제한 포함)은 공모전명 포함
          ...(scope === 'all' ? [team.contestTitle] : []),
        ]
          .join(' ')
          .toLowerCase()
          .includes(q),
    )
    .sort(
      (left, right) =>
        right.createdAt.localeCompare(left.createdAt) ||
        right.id.localeCompare(left.id),
    )
    .map(toTeamSummary);
  return pageResponse(paginate(items, query));
}

const pendingCount = (teamId: string) =>
  db().applications.filter((item) => item.teamId === teamId && isPending(item))
    .length;

// [출처 7] 원인 ID는 지원자 본인에게만 제공
function viewApplication(
  application: Application,
  viewer: string,
): Application {
  if (application.applicantAccountId === viewer) return application;
  return {
    ...application,
    discardedByApplicationId: null,
    discardedByTeamId: null,
  };
}

// [출처 5] 지원 본인 또는 받은 팀장만. 관계 밖이면 존재를 숨기는 404
function relatedApplication(applicationId: string, viewer: string) {
  const application =
    db().applications.find((item) => item.id === applicationId) ?? notFound();
  const owner = teamById(application.teamId)?.ownerAccountId;
  if (application.applicantAccountId !== viewer && owner !== viewer) notFound();
  return { application, isOwner: owner === viewer };
}

const findApplication = (applicationId: string) =>
  db().applications.find((item) => item.id === applicationId)!;

function applicant(application: Application, viewer: string) {
  return {
    application: viewApplication(application, viewer),
    profile: profileOf(application.applicantAccountId)!,
    isSelectionCandidate:
      isPending(application) &&
      !hasMembershipInContest(
        db(),
        application.contestId,
        application.applicantAccountId,
      ),
  };
}

// [출처 6] 받은 팀장의 버전 있는 행동. 버전을 먼저 비교하고, 이미 목표 상태면 no-op 200
function ownerAction(
  applicationId: string,
  body: unknown,
  target: Application['status'],
  run: (accountId: string) => Transition,
) {
  const accountId = requireSession();
  const { application, isOwner } = relatedApplication(applicationId, accountId);
  if (!isOwner) forbidden();
  const action = validate(VersionedAction, body);
  assertVersion(application.version, action.expectedVersion);
  if (application.status !== target) commit(run(accountId));
  return ok(viewApplication(findApplication(applicationId), accountId));
}

export function registerTeamRoutes(router: MockRouter) {
  router
    .on('GET', '/contests/{contestId}/teams', ({ params, query }) => {
      if (!contestById(params.contestId!)) notFound();
      return teamList(query, params.contestId!, 'contest');
    })
    .on('GET', '/teams', ({ query }) =>
      teamList(
        query,
        parseOptionalQuery(Id, query.get('contestId'), 'contestId'),
        'all',
      ),
    )
    .on('GET', '/teams/{teamId}', ({ params }) =>
      ok(teamById(params.teamId!) ?? notFound()),
    )
    // [출처 2] 팀 생성. 첫 생성 201, 같은 시도 재전송 200
    .on('POST', '/teams', ({ body }) => {
      const accountId = requireSession();
      const input = validate(TeamCreate, body);
      const attempt = idempotent(
        input.requestId,
        accountId,
        'POST /teams',
        input,
      );
      if (attempt.replayOf) return ok(teamById(attempt.replayOf), 200);
      if (!contestById(input.contestId)) notFound();
      const teamId = newId();
      commit(
        createDemoTeam(
          db(),
          {
            contestId: input.contestId,
            name: input.name,
            introduction: input.introduction,
            capacity: Number(input.capacity),
            roleCodes: input.roleCodes,
            recruitmentDeadline: input.recruitmentDeadline,
          },
          accountId,
          { teamId, membershipId: newId() },
          state.now,
        ),
      );
      attempt.remember(teamId);
      return ok(teamById(teamId), 201);
    })
    // 현재 팀장·확정 팀원인 팀, 소속 시작 joinedAt DESC
    .on('GET', '/me/teams', ({ query }) => {
      const accountId = requireSession();
      const items = db()
        .memberships.filter(
          (item) => item.accountId === accountId && !item.endedAt,
        )
        .sort(
          (left, right) =>
            right.joinedAt.localeCompare(left.joinedAt) ||
            right.membershipId.localeCompare(left.membershipId),
        )
        .map((membership) => ({
          team: teamSummary(membership.teamId),
          membershipId: membership.membershipId,
          membershipRole: membership.membershipRole,
          roleCode: membership.roleCode,
          pendingApplicationCount:
            membership.membershipRole === 'leader'
              ? pendingCount(membership.teamId)
              : null,
        }));
      return pageResponse(paginate(items, query));
    })
    // [출처 3] 팀 공간: 현재 소속만
    .on('GET', '/teams/{teamId}/space', ({ params }) => {
      const accountId = requireSession();
      const team = teamById(params.teamId!) ?? notFound();
      if (!isCurrentMember(team.id, accountId)) forbidden();
      const viewerRole =
        team.ownerAccountId === accountId ? 'leader' : 'member';
      return ok({
        team,
        members: teamMembers(db(), team.id, accountId),
        viewerRole,
        pendingApplicationCount:
          viewerRole === 'leader' ? pendingCount(team.id) : null,
      });
    })
    // [출처 4] 모집 종료. 이미 closed면 사유를 보존하고 no-op
    .on('PUT', '/teams/{teamId}/recruitment/closure', ({ params, body }) => {
      const accountId = requireSession();
      const record = teamRecord(params.teamId!);
      if (record.ownerAccountId !== accountId) forbidden();
      const action = validate(VersionedAction, body);
      assertVersion(record.version, action.expectedVersion);
      if (record.recruitmentState === 'open')
        commit(closeTeamRecruitment(db(), record.id, accountId));
      return ok({ team: teamSummary(record.id) });
    })
    // [출처 4] 모집 재개. 이미 open이며 모집 가능하면 no-op
    .on('PUT', '/teams/{teamId}/recruitment/reopening', ({ params, body }) => {
      const accountId = requireSession();
      const record = teamRecord(params.teamId!);
      if (record.ownerAccountId !== accountId) forbidden();
      const action = validate(VersionedAction, body);
      assertVersion(record.version, action.expectedVersion);
      if (!(
        record.recruitmentState === 'open' && teamById(record.id)!.isRecruiting
      ))
        commit(reopenTeamRecruitment(db(), record.id, accountId, state.now));
      return ok({ team: teamSummary(record.id) });
    });
}

export function registerApplicationRoutes(router: MockRouter) {
  router
    // 신규 지원. 첫 접수 201, 같은 시도 재전송 200
    .on('POST', '/teams/{teamId}/applications', ({ params, body }) => {
      const accountId = requireSession();
      const input = validate(ApplicationCreate, body);
      const route = `POST /teams/${params.teamId}/applications`;
      const attempt = idempotent(input.requestId, accountId, route, input);
      if (attempt.replayOf) return ok(findApplication(attempt.replayOf), 200);
      if (!teamById(params.teamId!)) notFound();
      const id = newId();
      commit(
        applyToTeam(
          db(),
          accountId,
          params.teamId!,
          input.roleCode,
          input.message ?? null,
          id,
          state.now,
        ),
      );
      attempt.remember(id);
      return ok(findApplication(id), 201);
    })
    .on('GET', '/me/applications', ({ query }) => {
      const accountId = requireSession();
      const status = parseOptionalQuery(
        ApplicationStatus,
        query.get('status'),
        'status',
      );
      const items = db()
        .applications.filter((item) => item.applicantAccountId === accountId)
        .filter((item) => !status || item.status === status)
        .sort(
          (left, right) =>
            right.submittedAt.localeCompare(left.submittedAt) ||
            right.id.localeCompare(left.id),
        )
        .map((application) => ({
          application,
          team: teamSummary(application.teamId),
          isCurrentMember: isCurrentMember(application.teamId, accountId),
        }));
      return pageResponse(paginate(items, query));
    })
    .on('GET', '/applications/{applicationId}', ({ params }) => {
      const accountId = requireSession();
      const { application } = relatedApplication(
        params.applicationId!,
        accountId,
      );
      return ok(viewApplication(application, accountId));
    })
    // [출처 6] 본인 취소. 이미 취소면 기존 결과 유지(no-op)
    .on(
      'PUT',
      '/applications/{applicationId}/cancellation',
      ({ params, body }) => {
        const accountId = requireSession();
        const { application } = relatedApplication(
          params.applicationId!,
          accountId,
        );
        if (application.applicantAccountId !== accountId) forbidden();
        const action = validate(VersionedAction, body);
        assertVersion(application.version, action.expectedVersion);
        // [출처 6] 이미 취소된 요청은 기존 취소 결과 유지: 그 취소로 끝난 소속이 있으면 true
        if (application.status === 'canceled')
          return ok({
            application,
            membershipEnded: db().memberships.some(
              (item) =>
                item.teamId === application.teamId &&
                item.accountId === accountId &&
                item.endedAt === application.updatedAt,
            ),
          });
        const wasSelected = application.status === 'selected';
        commit(
          cancelTeamApplication(db(), application.id, accountId, state.now),
        );
        return ok({
          application: findApplication(application.id),
          membershipEnded: wasSelected,
        });
      },
    )
    // 팀장 지원자 목록
    .on('GET', '/teams/{teamId}/applicants', ({ params, query }) => {
      const accountId = requireSession();
      const team = teamById(params.teamId!) ?? notFound();
      if (team.ownerAccountId !== accountId) forbidden();
      const status = parseOptionalQuery(
        ApplicationStatus,
        query.get('status'),
        'status',
      );
      const items = db()
        .applications.filter((item) => item.teamId === team.id)
        .filter((item) => !status || item.status === status)
        .sort(
          (left, right) =>
            right.submittedAt.localeCompare(left.submittedAt) ||
            right.id.localeCompare(left.id),
        )
        .map((application) => applicant(application, accountId));
      return pageResponse(paginate(items, query));
    })
    .on('GET', '/applications/{applicationId}/applicant', ({ params }) => {
      const accountId = requireSession();
      const { application, isOwner } = relatedApplication(
        params.applicationId!,
        accountId,
      );
      if (!isOwner) forbidden();
      return ok(applicant(application, accountId));
    })
    .on(
      'PUT',
      '/applications/{applicationId}/review-start',
      ({ params, body }) =>
        ownerAction(params.applicationId!, body, 'reviewing', (accountId) =>
          startApplicantReview(
            db(),
            params.applicationId!,
            accountId,
            state.now,
          ),
        ),
    )
    .on('PUT', '/applications/{applicationId}/rejection', ({ params, body }) =>
      ownerAction(params.applicationId!, body, 'rejected', (accountId) =>
        rejectTeamApplicant(db(), params.applicationId!, accountId, state.now),
      ),
    )
    // [출처 6] 선발. 이미 선발된 동일 소속이면 no-op
    .on(
      'PUT',
      '/applications/{applicationId}/selection',
      ({ params, body }) => {
        const accountId = requireSession();
        const { application, isOwner } = relatedApplication(
          params.applicationId!,
          accountId,
        );
        if (!isOwner) forbidden();
        const action = validate(VersionedAction, body);
        assertVersion(application.version, action.expectedVersion);
        const existing = () =>
          db().memberships.find(
            (item) =>
              item.teamId === application.teamId &&
              item.accountId === application.applicantAccountId &&
              !item.endedAt,
          );
        if (!(application.status === 'selected' && existing()))
          commit(
            selectTeamApplicant(
              db(),
              application.id,
              accountId,
              newId(),
              state.now,
            ),
          );
        return ok({
          application: viewApplication(
            findApplication(application.id),
            accountId,
          ),
          team: teamSummary(application.teamId),
          membershipId: existing()!.membershipId,
        });
      },
    );
}
