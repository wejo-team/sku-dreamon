/**
 * [참조 출처]
 * 1. docs/api/teams.md#endpoints, #queries - 팀 탐색·생성·워크스페이스, 검색 대상과 정렬 createdAt DESC, id DESC
 * 2. docs/api/teams.md#team-create - 생성 트랜잭션: 팀·팀장 소속, 같은 공모전 본인 대기 지원 폐기(team_created_elsewhere)
 * 3. docs/api/teams.md#team-member - 프로필은 본인·공개·지원받은 팀장에게만
 * 4. docs/api/teams.md#transitions - 모집 종료·재개 전이, no-op 200, 409 코드
 * 5. docs/api/applications.md#endpoints - 지원 9개 API, 관계 밖 404·행동 권한 403
 * 6. docs/api/applications.md#transitions - 검토 시작·미선발·선발·취소 전이, 선발 시 다른 대기 지원 폐기, 정원 충족 시 마감
 * 7. docs/api/applications.md#application-create - 신규 지원 조건과 409 코드
 * 8. docs/api/applications.md#application - 원인 ID는 본인에게만, 받은 팀장에게는 null
 */

import {
  ApplicationCreate,
  ApplicationStatus,
  type Application,
} from '@/features/applications/api';
import { TeamCreate } from '@/features/teams/api';
import {
  currentMemberships,
  toTeamMember,
  toTeamSummary,
  type MembershipRecord,
  type TeamRecord,
} from '@/features/demo/fixtures';
import { VersionedAction } from '@/lib/api-contract';
import {
  MockRouter,
  booleanQuery,
  conflict,
  forbidden,
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
  bumpVersion,
  catalogHas,
  contestById,
  db,
  hasMembershipInContest,
  idempotent,
  isCurrentMember,
  newId,
  notifyApplication,
  nowIso,
  profileOf,
  requireSession,
  state,
  teamById,
  teamRecord,
  teamSummary,
} from '@/lib/api-mock/state';

const PENDING: Application['status'][] = ['submitted', 'reviewing'];

function teamList(query: URLSearchParams, contestId: string | null) {
  const q = searchText(query);
  const roleCode = query.get('roleCode');
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
          // [출처 1] 전체 팀 검색만 공모전명 포함
          ...(contestId ? [] : [team.contestTitle]),
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

function pendingCount(teamId: string) {
  return db().applications.filter(
    (item) => item.teamId === teamId && PENDING.includes(item.status),
  ).length;
}

// [출처 3] 지원받은 팀장은 해당 지원자 프로필 열람 가능
const receivedApplicationFrom = (teamOwner: string, applicantId: string) =>
  db().applications.some(
    (item) =>
      item.applicantAccountId === applicantId &&
      teamById(item.teamId)?.ownerAccountId === teamOwner,
  );

// [출처 8] 원인 ID는 지원자 본인에게만 제공
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

function replaceApplication(next: Application) {
  db().applications = db().applications.map((item) =>
    item.id === next.id ? next : item,
  );
  return next;
}

function updateTeam(next: TeamRecord) {
  db().teams = db().teams.map((item) => (item.id === next.id ? next : item));
}

// [출처 2, 6] 같은 공모전에서 해당 계정의 다른 대기 지원을 폐기
function discardPending(
  accountId: string,
  contestId: string,
  except: string | null,
  reason: Application['discardReason'],
  cause: { applicationId?: string; teamId?: string },
) {
  for (const item of db().applications) {
    if (
      item.applicantAccountId !== accountId ||
      item.contestId !== contestId ||
      item.id === except ||
      !PENDING.includes(item.status)
    )
      continue;
    const discarded = replaceApplication({
      ...item,
      status: 'discarded',
      discardReason: reason,
      discardedByApplicationId: cause.applicationId ?? null,
      discardedByTeamId: cause.teamId ?? null,
      version: bumpVersion(item.version),
      updatedAt: nowIso(),
    });
    notifyApplication(discarded);
  }
}

function capacityAllowed(contestId: string, capacity: bigint) {
  const contest = contestById(contestId)!;
  const min = contest.capacity.minimumMembers;
  const max = contest.capacity.maximumMembers;
  if (contest.capacity.kind === 'unknown') return false;
  if (min && capacity < BigInt(min)) return false;
  if (max && capacity > BigInt(max)) return false;
  return true;
}

export function registerTeamRoutes(router: MockRouter) {
  router
    .on('GET', '/contests/{contestId}/teams', ({ params, query }) => {
      if (!contestById(params.contestId!)) notFound();
      return teamList(query, params.contestId!);
    })
    .on('GET', '/teams', ({ query }) => teamList(query, query.get('contestId')))
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
      const contest = contestById(input.contestId) ?? notFound();
      if (contest.registrationStatus !== 'open')
        conflict('CONTEST_NOT_OPEN', '공모전 접수 기간이 아니에요.');
      if (!capacityAllowed(contest.id, BigInt(input.capacity)))
        conflict(
          'CAPACITY_OUT_OF_RANGE',
          '공식 참가 인원 범위를 확인해 주세요.',
        );
      if (input.roleCodes.some((code) => !catalogHas('roles', code)))
        conflict(
          'INVALID_CATALOG_SELECTION',
          '모집 역할을 다시 확인해 주세요.',
        );
      if (hasMembershipInContest(contest.id, accountId))
        conflict(
          'MEMBERSHIP_CONFLICT',
          '이미 이 공모전의 팀에 소속되어 있어요.',
        );
      const teamId = newId();
      const createdAt = nowIso();
      // 마감 입력: 날짜만 있으면 한국시간 날짜 끝(다음 날 00:00)을 제외 경계로 사용
      const deadline = input.recruitmentDeadline;
      const endsAt =
        deadline.time || deadline.timeZone
          ? new Date(
              `${deadline.date}T${deadline.time ?? '23:59:59'}${deadline.timeZone === 'UTC' ? 'Z' : '+09:00'}`,
            ).toISOString()
          : new Date(
              Date.parse(`${deadline.date}T00:00:00+09:00`) + 86_400_000,
            ).toISOString();
      const team: TeamRecord = {
        id: teamId,
        version: '1',
        contestId: contest.id,
        name: input.name,
        introduction: input.introduction,
        roleCodes: input.roleCodes,
        capacity: input.capacity,
        recruitmentState: input.capacity === '1' ? 'closed' : 'open',
        closedReason: input.capacity === '1' ? 'capacity_reached' : null,
        recruitmentEndsAt: endsAt.replace('.000Z', 'Z'),
        createdAt,
        recruitmentDeadline: {
          sourceDate: deadline.date,
          sourceTime: deadline.time ?? null,
          sourceTimeZone: deadline.timeZone ?? null,
          effectiveTimeZone: deadline.timeZone ?? 'Asia/Seoul',
          timeDefaulted: !deadline.time,
          timeZoneDefaulted: !deadline.timeZone,
        },
        ownerAccountId: accountId,
      };
      db().teams.push(team);
      db().memberships.push({
        membershipId: newId(),
        teamId,
        accountId,
        membershipRole: 'leader',
        roleCode: null,
        joinedAt: createdAt,
        endedAt: null,
      });
      discardPending(accountId, contest.id, null, 'team_created_elsewhere', {
        teamId,
      });
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
        .map((membership: MembershipRecord) => ({
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
      const members = currentMemberships(db().memberships, team.id).map(
        (membership) =>
          toTeamMember(
            membership,
            db().profiles,
            (profile) =>
              profile.accountId === accountId ||
              profile.isPublic ||
              receivedApplicationFrom(accountId, profile.accountId),
          ),
      );
      return ok({
        team,
        members,
        viewerRole,
        pendingApplicationCount:
          viewerRole === 'leader' ? pendingCount(team.id) : null,
      });
    })
    // [출처 4] 모집 종료
    .on('PUT', '/teams/{teamId}/recruitment/closure', ({ params, body }) => {
      const accountId = requireSession();
      const record = teamRecord(params.teamId!);
      if (record.ownerAccountId !== accountId) forbidden();
      const action = validate(VersionedAction, body);
      assertVersion(record.version, action.expectedVersion);
      if (record.recruitmentState === 'closed')
        return ok({ team: teamSummary(record.id) });
      updateTeam({
        ...record,
        recruitmentState: 'closed',
        closedReason: 'leader_closed',
        version: bumpVersion(record.version),
      });
      return ok({ team: teamSummary(record.id) });
    })
    // [출처 4] 모집 재개: 공고 접수·팀 기한·잔여 정원 확인
    .on('PUT', '/teams/{teamId}/recruitment/reopening', ({ params, body }) => {
      const accountId = requireSession();
      const record = teamRecord(params.teamId!);
      if (record.ownerAccountId !== accountId) forbidden();
      const action = validate(VersionedAction, body);
      assertVersion(record.version, action.expectedVersion);
      const team = teamById(record.id)!;
      if (record.recruitmentState === 'open') {
        if (team.isRecruiting) return ok({ team: toTeamSummary(team) });
        conflict(
          'INVALID_RECRUITMENT_STATE',
          '모집을 다시 시작할 수 없는 상태예요.',
        );
      }
      if (contestById(team.contestId)!.registrationStatus !== 'open')
        conflict('CONTEST_NOT_OPEN', '공모전 접수 기간이 아니에요.');
      if (state.now >= Date.parse(team.recruitmentEndsAt))
        conflict('RECRUITMENT_DEADLINE_PASSED', '팀 모집 기한이 지났어요.');
      if (team.memberCount >= Number(team.capacity))
        conflict('TEAM_FULL', '팀 정원이 모두 찼어요.');
      updateTeam({
        ...record,
        recruitmentState: 'open',
        closedReason: null,
        version: bumpVersion(record.version),
      });
      return ok({ team: teamSummary(record.id) });
    });
}

export function registerApplicationRoutes(router: MockRouter) {
  router
    // [출처 7] 신규 지원
    .on('POST', '/teams/{teamId}/applications', ({ params, body }) => {
      const accountId = requireSession();
      const input = validate(ApplicationCreate, body);
      const route = `POST /teams/${params.teamId}/applications`;
      const attempt = idempotent(input.requestId, accountId, route, input);
      if (attempt.replayOf)
        return ok(
          db().applications.find((item) => item.id === attempt.replayOf),
          200,
        );
      const team = teamById(params.teamId!) ?? notFound();
      const profile = profileOf(accountId);
      if (!profile)
        conflict('PROFILE_REQUIRED', '필수 프로필을 먼저 저장해 주세요.');
      if (!profile!.isPublic)
        conflict('PROFILE_PRIVATE', '프로필을 공개해야 지원할 수 있어요.');
      if (!catalogHas('roles', input.roleCode))
        conflict(
          'INVALID_CATALOG_SELECTION',
          '지원 역할을 다시 확인해 주세요.',
        );
      if (contestById(team.contestId)!.registrationStatus !== 'open')
        conflict('CONTEST_NOT_OPEN', '공모전 접수 기간이 아니에요.');
      if (team.recruitmentState === 'closed')
        conflict('RECRUITMENT_CLOSED', '모집이 마감되었어요.');
      if (state.now >= Date.parse(team.recruitmentEndsAt))
        conflict('RECRUITMENT_DEADLINE_PASSED', '팀 모집 기한이 지났어요.');
      if (team.memberCount >= Number(team.capacity))
        conflict('TEAM_FULL', '팀 정원이 모두 찼어요.');
      if (hasMembershipInContest(team.contestId, accountId))
        conflict(
          'MEMBERSHIP_CONFLICT',
          '이미 이 공모전의 팀에 소속되어 있어요.',
        );
      const mine = db().applications.filter(
        (item) =>
          item.teamId === team.id && item.applicantAccountId === accountId,
      );
      if (mine.some((item) => PENDING.includes(item.status)))
        conflict('DUPLICATE_APPLICATION', '이미 이 팀에 지원했어요.');
      if (mine.some((item) => item.status === 'rejected'))
        conflict(
          'REAPPLICATION_NOT_ALLOWED',
          '이 팀에는 다시 지원할 수 없어요.',
        );
      const now = nowIso();
      const application: Application = {
        id: newId(),
        version: '1',
        teamId: team.id,
        contestId: team.contestId,
        applicantAccountId: accountId,
        roleCode: input.roleCode,
        message: input.message?.trim() || null,
        status: 'submitted',
        discardReason: null,
        discardedByApplicationId: null,
        discardedByTeamId: null,
        submittedAt: now,
        updatedAt: now,
      };
      db().applications.push(application);
      notifyApplication(application, true);
      attempt.remember(application.id);
      return ok(application, 201);
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
    // [출처 6] 본인 취소. 선발 후 취소는 소속 종료·자리 반환, 자동 재개 없음
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
        if (application.status === 'canceled')
          return ok({ application, membershipEnded: false });
        if (
          !['submitted', 'reviewing', 'selected'].includes(application.status)
        )
          conflict(
            'INVALID_APPLICATION_STATE',
            '취소할 수 없는 지원 상태예요.',
          );
        let membershipEnded = false;
        if (application.status === 'selected') {
          db().memberships = db().memberships.map((item) => {
            if (
              item.teamId === application.teamId &&
              item.accountId === accountId &&
              !item.endedAt
            ) {
              membershipEnded = true;
              return { ...item, endedAt: nowIso() };
            }
            return item;
          });
        }
        const canceled = replaceApplication({
          ...application,
          status: 'canceled',
          version: bumpVersion(application.version),
          updatedAt: nowIso(),
        });
        notifyApplication(canceled);
        return ok({ application: canceled, membershipEnded });
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
        ownerAction(params.applicationId!, body, (application) => {
          if (application.status === 'reviewing') return application;
          if (application.status !== 'submitted')
            conflict(
              'INVALID_APPLICATION_STATE',
              '검토를 시작할 수 없는 상태예요.',
            );
          return 'reviewing';
        }),
    )
    .on('PUT', '/applications/{applicationId}/rejection', ({ params, body }) =>
      ownerAction(params.applicationId!, body, (application) => {
        if (application.status === 'rejected') return application;
        if (!PENDING.includes(application.status))
          conflict(
            'INVALID_APPLICATION_STATE',
            '미선발 처리할 수 없는 상태예요.',
          );
        return 'rejected';
      }),
    )
    // [출처 6] 선발: 공고 접수 기간·여석·무소속. 팀 저장 상태가 closed여도 기존 유효 지원은 선발 가능
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
        const team = teamById(application.teamId)!;
        const existing = db().memberships.find(
          (item) =>
            item.teamId === team.id &&
            item.accountId === application.applicantAccountId &&
            !item.endedAt,
        );
        if (application.status === 'selected' && existing)
          return ok({
            application: viewApplication(application, accountId),
            team: toTeamSummary(team),
            membershipId: existing.membershipId,
          });
        if (!PENDING.includes(application.status))
          conflict(
            'INVALID_APPLICATION_STATE',
            '선발할 수 없는 지원 상태예요.',
          );
        if (state.now >= Date.parse(team.contest.endsAt))
          conflict(
            'CONTEST_NOT_OPEN',
            '공모전 접수가 마감되어 선발할 수 없어요.',
          );
        if (team.memberCount >= Number(team.capacity))
          conflict('TEAM_FULL', '팀 정원이 모두 찼어요.');
        if (
          hasMembershipInContest(team.contestId, application.applicantAccountId)
        )
          conflict(
            'MEMBERSHIP_CONFLICT',
            '지원자가 이미 이 공모전의 팀에 소속되어 있어요.',
          );
        const membershipId = newId();
        db().memberships.push({
          membershipId,
          teamId: team.id,
          accountId: application.applicantAccountId,
          membershipRole: 'member',
          roleCode: application.roleCode,
          joinedAt: nowIso(),
          endedAt: null,
        });
        const selected = replaceApplication({
          ...application,
          status: 'selected',
          version: bumpVersion(application.version),
          updatedAt: nowIso(),
        });
        notifyApplication(selected);
        discardPending(
          application.applicantAccountId,
          team.contestId,
          application.id,
          'selected_elsewhere',
          { applicationId: application.id },
        );
        // 정원이 차면 모집 마감(capacity_reached)
        const after = teamById(team.id)!;
        if (after.memberCount >= Number(after.capacity)) {
          const record = teamRecord(team.id);
          updateTeam({
            ...record,
            recruitmentState: 'closed',
            closedReason: 'capacity_reached',
            version: bumpVersion(record.version),
          });
        }
        return ok({
          application: viewApplication(selected, accountId),
          team: teamSummary(team.id),
          membershipId,
        });
      },
    );
}

function applicant(application: Application, viewer: string) {
  return {
    application: viewApplication(application, viewer),
    profile: profileOf(application.applicantAccountId)!,
    isSelectionCandidate:
      PENDING.includes(application.status) &&
      !hasMembershipInContest(
        application.contestId,
        application.applicantAccountId,
      ),
  };
}

// [출처 6] 받은 팀장의 버전 있는 행동. 버전을 먼저 비교하고, 같은 상태면 no-op 200
function ownerAction(
  applicationId: string,
  body: unknown,
  next: (application: Application) => Application | Application['status'],
) {
  const accountId = requireSession();
  const { application, isOwner } = relatedApplication(applicationId, accountId);
  if (!isOwner) forbidden();
  const action = validate(VersionedAction, body);
  assertVersion(application.version, action.expectedVersion);
  const result = next(application);
  if (typeof result !== 'string') return ok(viewApplication(result, accountId));
  const updated = replaceApplication({
    ...application,
    status: result,
    version: bumpVersion(application.version),
    updatedAt: nowIso(),
  });
  notifyApplication(updated);
  return ok(viewApplication(updated, accountId));
}
