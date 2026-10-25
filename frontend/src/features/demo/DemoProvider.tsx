/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/PreviewProvider.tsx - 메모리 상태 원본
 * 2. docs/design/handoff.md - 「데이터·인증·AI의 실제 범위」 새로고침 시 초기화, 공유되지 않는 로컬 상태
 * 3. docs/development/frontend.md - 「화면과 상태」 서버 데이터는 TanStack Query, 전역 store 중복 금지
 * 4. docs/design/screens.md - 「재현 경로」 scenario=team-lifecycle 초기 상태
 * 5. docs/api/README.md - 상태는 API DTO 모양, 전이 규칙은 목업 서버와 같은 team-state 사용
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { useRef, useState, type ReactNode } from 'react';
import {
  DemoContext,
  type ActionResult,
  type DemoState,
} from '@/features/demo/demo-context';
import { createDemoRecords, type DemoDatabase } from '@/features/demo/fixtures';
import { lifecycleReferenceDatabase } from '@/features/demo/lifecycle-fixtures';
import {
  appendNotifications,
  transitionNotifications,
} from '@/features/demo/notification-state';
import {
  applyToTeam,
  cancelTeamApplication,
  closeTeamRecruitment,
  createDemoTeam,
  rejectTeamApplicant,
  reopenTeamRecruitment,
  selectTeamApplicant,
  type Transition,
} from '@/features/demo/team-state';
import { deriveDemoState } from '@/features/demo/demo-state';

// [출처 4] scenario=team-lifecycle은 새로 불러올 때만 예시 상태를 구성
const initialDatabase = (): DemoDatabase =>
  new URLSearchParams(globalThis.location?.search).get('scenario') ===
  'team-lifecycle'
    ? lifecycleReferenceDatabase()
    : createDemoRecords();

type Snapshot = { signedIn: boolean; db: DemoDatabase };

// [출처 2, 3, 5] 로그인·프로필·팀·지원·알림의 로컬 상태 전이
export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Snapshot>(() => ({
    signedIn: false,
    db: initialDatabase(),
  }));
  const latest = useRef(state);
  const eventSequence = useRef(0);
  // One synchronous transition prevents two actions in the same render from using an old seat count.
  const update = (next: Snapshot) => {
    latest.current = next;
    setState(next);
  };
  // [출처 5] 성공한 업무 변경만 반영하고 그 변경의 알림을 함께 추가
  const commit = (transition: Transition): ActionResult => {
    const current = latest.current;
    if (!current.signedIn)
      return {
        ok: false,
        error: { code: 'UNAUTHENTICATED', message: '로그인이 필요해요.' },
      };
    if ('error' in transition) return { ok: false, error: transition.error };
    const additions = transitionNotifications(
      current.db,
      transition.db,
      `event-${++eventSequence.current}`,
      new Date().toISOString().replace(/\.\d{3}Z$/, 'Z'),
    );
    update({
      ...current,
      db: {
        ...transition.db,
        notifications: appendNotifications(
          transition.db.notifications,
          additions,
        ),
      },
    });
    return { ok: true };
  };
  const me = () => latest.current.db.account.id;
  const notSignedIn: Transition = {
    error: { code: 'UNAUTHENTICATED', message: '로그인이 필요해요.' },
  };
  const guarded = (run: (db: DemoDatabase) => Transition) =>
    commit(latest.current.signedIn ? run(latest.current.db) : notSignedIn);

  const value: DemoState = {
    ...deriveDemoState(state.db, state.signedIn),
    signIn: () => update({ ...latest.current, signedIn: true }),
    signOut: () => update({ ...latest.current, signedIn: false }),
    saveProfile: (profile) => {
      const current = latest.current;
      update({
        ...current,
        db: {
          ...current.db,
          profiles: current.db.profiles.map((item) =>
            item.accountId === profile.accountId ? profile : item,
          ),
        },
      });
    },
    markNotificationsRead: (ids) => {
      const current = latest.current;
      if (!current.signedIn) return;
      const readAt = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
      update({
        ...current,
        db: {
          ...current.db,
          notifications: current.db.notifications.map((item) =>
            ids.includes(item.id) &&
            item.recipientAccountId === current.db.account.id &&
            !item.readAt
              ? { ...item, readAt }
              : item,
          ),
        },
      });
    },
    apply: (teamId, roleCode, message) =>
      guarded((db) =>
        applyToTeam(db, me(), teamId, roleCode, message, crypto.randomUUID()),
      ),
    selectApplicant: (applicationId) =>
      guarded((db) =>
        selectTeamApplicant(db, applicationId, me(), crypto.randomUUID()),
      ),
    rejectApplicant: (applicationId) =>
      guarded((db) => rejectTeamApplicant(db, applicationId, me())),
    cancelApplication: (applicationId) =>
      guarded((db) => cancelTeamApplication(db, applicationId, me())),
    closeRecruitment: (teamId) =>
      guarded((db) => closeTeamRecruitment(db, teamId, me())),
    reopenRecruitment: (teamId) =>
      guarded((db) => reopenTeamRecruitment(db, teamId, me())),
    createTeam: (team) => {
      const teamId = crypto.randomUUID();
      const result = guarded((db) =>
        createDemoTeam(db, team, me(), {
          teamId,
          membershipId: crypto.randomUUID(),
        }),
      );
      return result.ok ? teamId : '';
    },
    reset: () => update({ signedIn: true, db: initialDatabase() }),
    // 워크스페이스 빈 상태 확인: 팀은 그대로 두고 본인의 소속·지원·알림만 비움.
    // 본인이 팀장인 팀은 남은 첫 팀원이 팀장을 맡습니다(화면 확인용 상태 조작).
    emptyWorkspace: () => {
      const current = latest.current;
      const accountId = current.db.account.id;
      const ended = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');
      const successor = new Map<string, string>();
      for (const team of current.db.teams) {
        if (team.ownerAccountId !== accountId) continue;
        const next = current.db.memberships.find(
          (item) =>
            item.teamId === team.id &&
            !item.endedAt &&
            item.accountId !== accountId,
        );
        if (next) successor.set(team.id, next.accountId);
      }
      update({
        signedIn: true,
        db: {
          ...current.db,
          teams: current.db.teams.map((team) =>
            successor.has(team.id)
              ? { ...team, ownerAccountId: successor.get(team.id)! }
              : team,
          ),
          memberships: current.db.memberships.map((item) =>
            item.accountId === accountId && !item.endedAt
              ? { ...item, endedAt: ended }
              : successor.get(item.teamId) === item.accountId
                ? { ...item, membershipRole: 'leader' as const, roleCode: null }
                : item,
          ),
          applications: current.db.applications.filter(
            (item) => item.applicantAccountId !== accountId,
          ),
          notifications: current.db.notifications.filter(
            (item) => item.recipientAccountId !== accountId,
          ),
        },
      });
    },
  };

  return <DemoContext value={value}>{children}</DemoContext>;
}
