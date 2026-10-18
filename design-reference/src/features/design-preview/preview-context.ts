import { createContext, useContext } from 'react';
import type { Applicant, Application, Profile, Team } from './data';
import type { NewTeam } from './team-state';

export type PreviewState = {
  signedIn: boolean;
  profile: Profile;
  teams: Team[];
  applications: Application[];
  applicants: Applicant[];
  signIn: () => void;
  signOut: () => void;
  saveProfile: (profile: Profile) => void;
  apply: (teamId: string, role: string, message: string) => boolean;
  selectApplicant: (id: string) => boolean;
  cancelApplication: (id: string) => boolean;
  closeRecruitment: (id: string) => boolean;
  createTeam: (team: NewTeam) => string;
  reset: () => void;
  emptyWorkspace: () => void;
};
export const PreviewContext = createContext<PreviewState | null>(null);
export function usePreview() {
  const value = useContext(PreviewContext);
  if (!value) throw new Error('PreviewProvider가 필요합니다.');
  return value;
}
