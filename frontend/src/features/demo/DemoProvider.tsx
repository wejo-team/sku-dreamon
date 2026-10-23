/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/PreviewProvider.tsx - 메모리 상태 원본
 * 2. docs/design/handoff.md - 「데이터·인증·AI의 실제 범위」 새로고침 시 초기화, 공유되지 않는 로컬 상태
 * 3. docs/development/frontend.md - 「화면과 상태」 서버 데이터는 TanStack Query, 전역 store 중복 금지
 * 4. docs/design/screens.md - 「재현 경로」 scenario=team-lifecycle 초기 상태
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { useRef, useState, type ReactNode } from 'react';
import {
  contests,
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
} from '@/features/demo/data';
import { DemoContext } from '@/features/demo/demo-context';
import { lifecycleReferenceActivity } from '@/features/demo/lifecycle-fixtures';
import {
  appendNotifications,
  initialNotifications,
  isNotificationRecipient,
  transitionNotifications,
} from '@/features/demo/notification-state';
import {
  applyToTeam,
  cancelTeamApplication,
  createTeamIssue,
  reopenTeamRecruitment,
  selectTeamApplicant,
  type TeamActivity,
} from '@/features/demo/team-state';

const initialState = () => {
  const activity =
    new URLSearchParams(globalThis.location?.search).get('scenario') ===
    'team-lifecycle'
      ? lifecycleReferenceActivity()
      : {
          teams: initialTeams,
          applications: initialApplications,
          applicants: initialApplicants,
        };
  return {
    signedIn: false,
    profile: initialProfile,
    ...activity,
    notifications: initialNotifications(activity),
  };
};

// [출처 2, 3, 4] 로그인·프로필·팀·지원·알림의 로컬 상태 전이
export function DemoProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(initialState);
  const latest = useRef(state);
  const sequence = useRef(0);
  const eventSequence = useRef(0);
  // One synchronous transition prevents two actions in the same render from using an old seat count.
  const update = (next: typeof state) => {
    latest.current = next;
    setState(next);
  };
  const recordActivity = (current: typeof state, next: TeamActivity) => {
    const additions = transitionNotifications(
      current,
      next,
      `event-${++eventSequence.current}`,
      new Date().toISOString(),
    );
    update({
      ...current,
      ...next,
      notifications: appendNotifications(current.notifications, additions),
    });
  };
  return (
    <DemoContext
      value={{
        ...state,
        signIn: () => update({ ...latest.current, signedIn: true }),
        signOut: () => update({ ...latest.current, signedIn: false }),
        saveProfile: (profile) => update({ ...latest.current, profile }),
        markNotificationsRead: (ids) => {
          const current = latest.current;
          if (!current.signedIn) return;
          update({
            ...current,
            notifications: current.notifications.map((item) =>
              ids.includes(item.id) &&
              isNotificationRecipient(item, current.teams)
                ? { ...item, read: true }
                : item,
            ),
          });
        },
        apply: (teamId, role, message) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = applyToTeam(
            current,
            current.profile,
            teamId,
            role,
            message,
            `application-${teamId}-${++sequence.current}`,
          );
          if (!next) return false;
          recordActivity(current, next);
          return true;
        },
        selectApplicant: (id) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = selectTeamApplicant(current, id, current.profile);
          if (!next) return false;
          recordActivity(current, next);
          return true;
        },
        cancelApplication: (id) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = cancelTeamApplication(current, id);
          if (!next) return false;
          recordActivity(current, next);
          return true;
        },
        closeRecruitment: (id) => {
          const current = latest.current;
          const team = current.teams.find((item) => item.id === id);
          if (!current.signedIn || !team?.owner || team.status === '모집마감')
            return false;
          update({
            ...current,
            teams: current.teams.map((item) =>
              item.id === id ? { ...item, status: '모집마감' } : item,
            ),
          });
          return true;
        },
        reopenRecruitment: (id) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = reopenTeamRecruitment(current, id);
          if (!next) return false;
          update({ ...current, ...next });
          return true;
        },
        createTeam: (team) => {
          const current = latest.current;
          if (!current.signedIn || createTeamIssue(team, current.teams))
            return '';
          const contest = contests.find((item) => item.id === team.contestId)!;
          const id = `team-${++sequence.current}`;
          update({
            ...current,
            teams: [
              ...current.teams,
              {
                ...team,
                name: team.name.trim(),
                summary: team.summary.trim(),
                interests: [...contest.interests],
                roles: team.capacity === 1 ? [] : [...team.roles],
                id,
                owner: true,
                members: 1,
                memberProfiles: [
                  { id: 'me', name: current.profile.name, role: '팀장' },
                ],
                status: team.capacity === 1 ? '모집마감' : '모집중',
              },
            ],
          });
          return id;
        },
        reset: () => update({ ...initialState(), signedIn: true }),
        emptyWorkspace: () =>
          update({
            ...latest.current,
            signedIn: true,
            teams: latest.current.teams.map((team) => ({
              ...team,
              owner: false,
              memberProfiles: team.memberProfiles.filter(
                (member) => member.id !== 'me',
              ),
              members:
                team.members -
                (team.memberProfiles.some((member) => member.id === 'me')
                  ? 1
                  : 0),
            })),
            applications: [],
            applicants: [],
            notifications: [],
          }),
      }}
    >
      {children}
    </DemoContext>
  );
}
