import { useRef, useState, type ReactNode } from 'react';
import {
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
} from './data';
import { PreviewContext } from './preview-context';
import {
  applyToTeam,
  cancelTeamApplication,
  createTeamIssue,
  selectTeamApplicant,
} from './team-state';

const initialState = () => ({
  signedIn: false,
  profile: initialProfile,
  teams: initialTeams,
  applications: initialApplications,
  applicants: initialApplicants,
});

export function PreviewProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(initialState);
  const latest = useRef(state);
  const sequence = useRef(0);
  // One synchronous transition prevents two actions in the same render from using an old seat count.
  const update = (next: typeof state) => {
    latest.current = next;
    setState(next);
  };
  return (
    <PreviewContext
      value={{
        ...state,
        signIn: () => update({ ...latest.current, signedIn: true }),
        signOut: () => update({ ...latest.current, signedIn: false }),
        saveProfile: (profile) => update({ ...latest.current, profile }),
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
          update({ ...current, ...next });
          return true;
        },
        selectApplicant: (id) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = selectTeamApplicant(current, id, current.profile);
          if (!next) return false;
          update({ ...current, ...next });
          return true;
        },
        cancelApplication: (id) => {
          const current = latest.current;
          if (!current.signedIn) return false;
          const next = cancelTeamApplication(current, id);
          if (!next) return false;
          update({ ...current, ...next });
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
        createTeam: (team) => {
          const current = latest.current;
          if (!current.signedIn || createTeamIssue(team, current.teams))
            return '';
          const id = `team-${++sequence.current}`;
          update({
            ...current,
            teams: [
              ...current.teams,
              {
                ...team,
                id,
                owner: true,
                members: 1,
                memberProfiles: [
                  { id: 'me', name: current.profile.name, role: '팀장' },
                ],
                status: '모집중',
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
          }),
      }}
    >
      {children}
    </PreviewContext>
  );
}
