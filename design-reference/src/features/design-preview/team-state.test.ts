import { describe, expect, it } from 'vitest';
import {
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
  getPublicProfile,
  type Applicant,
} from './data';
import {
  applicantVisibleProfile,
  applyToTeam,
  cancelTeamApplication,
  createTeamIssue,
  isTeamMember,
  selectTeamApplicant,
  type TeamActivity,
} from './team-state';
const state = (): TeamActivity => ({
  teams: structuredClone(initialTeams),
  applications: structuredClone(initialApplications),
  applicants: structuredClone(initialApplicants),
});

describe('team reference transitions', () => {
  it('confirms selection and consumes a seat in the same transition', () => {
    const before = state();
    const next = selectTeamApplicant(before, 'app-seoyeon', initialProfile)!;
    const team = next.teams.find((item) => item.id === 'greenwave')!;
    expect(team.members).toBe(3);
    expect(isTeamMember(team, 'seoyeon')).toBe(true);
    expect(
      next.applicants.find((item) => item.id === 'app-seoyeon')?.status,
    ).toBe('선발');
    expect(selectTeamApplicant(next, 'app-seoyeon', initialProfile)).toBeNull();
    expect(before.teams.find((item) => item.id === 'greenwave')?.members).toBe(
      2,
    );
  });
  it('allows only one of two selections for the last seat', () => {
    const before = state();
    before.teams = before.teams.map((team) =>
      team.id === 'greenwave' ? { ...team, capacity: 3 } : team,
    );
    const first = selectTeamApplicant(before, 'app-seoyeon', initialProfile)!;
    expect(selectTeamApplicant(first, 'app-sua', initialProfile)).toBeNull();
    expect(first.teams.find((team) => team.id === 'greenwave')?.members).toBe(
      3,
    );
    expect(first.applicants.find((item) => item.id === 'app-sua')?.status).toBe(
      '검토중',
    );
  });
  it('rejects a second confirmed membership for the same contest', () => {
    const before = state();
    before.teams.push({
      ...before.teams[0]!,
      id: 'other-green-team',
      contestId: 'green',
      memberProfiles: [{ id: 'seoyeon', name: '김서연', role: '개발' }],
    });
    expect(
      selectTeamApplicant(before, 'app-seoyeon', initialProfile),
    ).toBeNull();
  });
  it('cancels a selected application, revokes membership, and returns exactly one seat without reopening', () => {
    const before = state();
    const application = before.applications.find(
      (item) => item.status === '선발',
    )!;
    const next = cancelTeamApplication(before, application.id)!;
    const oldTeam = before.teams.find(
      (team) => team.id === application.teamId,
    )!;
    const team = next.teams.find((item) => item.id === application.teamId)!;
    expect(isTeamMember(team)).toBe(false);
    expect(team.members).toBe(oldTeam.members - 1);
    expect(team.status).toBe(oldTeam.status);
    expect(
      next.applications.find((item) => item.id === application.id)?.status,
    ).toBe('지원취소');
    expect(cancelTeamApplication(next, application.id)).toBeNull();
  });
  it('allows an unadvertised role, and reapplication gets a fresh identity', () => {
    const first = applyToTeam(
      state(),
      initialProfile,
      'makers',
      '마케팅',
      '',
      'new-1',
    )!;
    expect(first).not.toBeNull();
    expect(first.teams.find((team) => team.id === 'makers')?.members).toBe(2);
    const cancelled = cancelTeamApplication(first, 'new-1')!;
    const second = applyToTeam(
      cancelled,
      initialProfile,
      'makers',
      '기획',
      '다시 지원해요',
      'new-2',
    )!;
    expect(
      second.applications.find((item) => item.id === 'new-2')?.status,
    ).toBe('지원완료');
    expect(cancelTeamApplication(second, 'new-1')).toBeNull();
    expect(selectTeamApplicant(second, 'new-1', initialProfile)).toBeNull();
    expect(
      applyToTeam(second, initialProfile, 'makers', '기획', '', 'new-3'),
    ).toBeNull();
  });
  it('accepts applications during review, but blocks deadline, full capacity, and missing profile', () => {
    const before = state();
    before.teams = before.teams.map((team) =>
      team.id === 'makers' ? { ...team, status: '지원자검토' } : team,
    );
    expect(
      applyToTeam(before, initialProfile, 'makers', '기획', '', 'review-new'),
    ).not.toBeNull();
    expect(
      applyToTeam(
        before,
        { ...initialProfile, interests: [] },
        'makers',
        '기획',
        '',
        'missing',
      ),
    ).toBeNull();
    expect(
      applyToTeam(
        before,
        initialProfile,
        'makers',
        '기획',
        'x'.repeat(1001),
        'long',
      ),
    ).toBeNull();
    before.teams = before.teams.map((team) =>
      team.id === 'makers' ? { ...team, capacity: team.members } : team,
    );
    expect(
      applyToTeam(before, initialProfile, 'makers', '기획', '', 'full'),
    ).toBeNull();
    before.teams = before.teams.map((team) =>
      team.id === 'makers'
        ? { ...team, capacity: 10, recruitmentDeadline: '2026-10-17' }
        : team,
    );
    expect(
      applyToTeam(before, initialProfile, 'makers', '기획', '', 'expired'),
    ).toBeNull();
  });
  it('validates the official target capacity without requiring all members at creation', () => {
    const input = {
      name: '새로운 팀',
      summary: '공모전 아이디어를 함께 구체화해요',
      contestId: 'campus',
      roles: ['기획'],
      interests: [],
      capacity: 4,
      recruitmentDeadline: '2026-11-01',
      kind: 'entry' as const,
    };
    expect(createTeamIssue(input, initialTeams)).toBeNull();
    expect(createTeamIssue({ ...input, capacity: 1 }, initialTeams)).toMatch(
      /공식 참가 인원/,
    );
    expect(createTeamIssue({ ...input, capacity: 100 }, initialTeams)).toMatch(
      /공식 참가 인원/,
    );
    expect(
      createTeamIssue(
        { ...input, recruitmentDeadline: '2026-12-01' },
        initialTeams,
      ),
    ).toMatch(/마감/);
    expect(
      createTeamIssue({ ...input, contestId: 'green' }, initialTeams),
    ).toMatch(/이미/);
  });
});

describe('applicant visibility', () => {
  const fixture = (): Applicant => ({
    ...initialApplicants[0]!,
    profile: {
      ...initialProfile,
      name: '비공개 지원자',
      intro: '지원자의 자기소개',
      experienceState: 'provided',
      experience: '지원자의 경험',
      academicStatus: '재학',
      grade: '3학년',
      college: '이공대학',
      department: '소프트웨어학과',
      major: '컴퓨터공학',
      skills: ['개발', '기타'],
      skillOther: '사용자 테스트',
      interests: ['기타'],
      interestOther: '지역 커뮤니티',
      availability: '수 18:00~21:00',
      visibility: { discoverable: false },
      portfolio: 'https://example.com/private',
      portfolioTitle: '비공개 링크',
    },
  });
  it('shares the full private profile in applicant review while excluding it from discovery', () => {
    const applicant = fixture();
    expect(getPublicProfile(applicant.profile!)).toBeNull();
    expect(applicantVisibleProfile(applicant, initialProfile)).toMatchObject({
      name: '비공개 지원자',
      intro: '지원자의 자기소개',
      experience: '지원자의 경험',
      experienceState: 'provided',
      academicStatus: '재학',
      grade: '3학년',
      college: '이공대학',
      department: '소프트웨어학과',
      major: '컴퓨터공학',
      skills: ['개발', '기타'],
      skillOther: '사용자 테스트',
      interests: ['기타'],
      interestOther: '지역 커뮤니티',
      availability: '수 18:00~21:00',
      portfolio: 'https://example.com/private',
      portfolioTitle: '비공개 링크',
    });
  });
  it('uses the current self profile instead of a stored application snapshot', () => {
    const applicant = {
      ...fixture(),
      personId: 'me',
      status: '지원취소' as const,
    };
    const current = {
      ...initialProfile,
      name: '수정된 이름',
      intro: '수정된 자기소개',
      visibility: { discoverable: false },
      availability: '금 18:00~21:00',
      portfolio: 'https://example.com/current',
      portfolioTitle: '현재 포트폴리오',
    };
    expect(applicantVisibleProfile(applicant, current)).toMatchObject({
      name: '수정된 이름',
      intro: '수정된 자기소개',
      availability: '금 18:00~21:00',
      portfolio: 'https://example.com/current',
    });
    expect(
      applicantVisibleProfile(applicant, {
        ...current,
        visibility: { discoverable: true },
      }),
    ).toEqual(applicantVisibleProfile(applicant, current));
    expect(
      applicantVisibleProfile(applicant, { ...current, portfolio: '' })
        .portfolio,
    ).toBe('');
  });
});
