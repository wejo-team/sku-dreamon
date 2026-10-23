import { describe, expect, it } from 'vitest';
import {
  contests,
  initialApplicants,
  initialApplications,
  initialProfile,
  initialTeams,
  getPublicProfile,
  type Applicant,
} from '@/features/demo/data';
import {
  applicantVisibleProfile,
  applyToTeam,
  cancelTeamApplication,
  createTeamIssue,
  isTeamMember,
  selectTeamApplicant,
  recruitmentIssue,
  recruitmentReopeningIssue,
  reopenTeamRecruitment,
  teamRecruitmentDeadline,
  type TeamActivity,
} from '@/features/demo/team-state';
import { lifecycleReferenceActivity } from '@/features/demo/lifecycle-fixtures';
import {
  appendNotifications,
  transitionNotifications,
} from '@/features/demo/notification-state';
const publicProfile = { ...initialProfile, visibility: { discoverable: true } };
const state = (): TeamActivity => ({
  teams: structuredClone(initialTeams),
  applications: structuredClone(initialApplications),
  applicants: structuredClone(initialApplicants),
});

describe('explicit recruitment reopening and parallel applications', () => {
  it('allows parallel applications to different teams of the same contest without consuming seats', () => {
    const before = state();
    before.teams.push({ ...before.teams[0]!, id: 'other-campus-team' });
    const first = applyToTeam(
      before,
      publicProfile,
      'makers',
      '기획',
      '',
      'first',
    )!;
    const second = applyToTeam(
      first,
      publicProfile,
      'other-campus-team',
      '기획',
      '',
      'second',
    )!;
    expect(second.applications.slice(-2).map((item) => item.status)).toEqual([
      '지원완료',
      '지원완료',
    ]);
    expect(second.teams).toEqual(before.teams);
    expect(
      applyToTeam(second, publicProfile, 'makers', '기획', '', 'duplicate'),
    ).toBeNull();
  });

  it('only discards the selected person’s other pending applications for the same contest, including mirrored records', () => {
    const before = state();
    const applicant = before.applicants[0]!;
    before.teams.push({
      ...before.teams[1]!,
      id: 'other-green-team',
      owner: false,
    });
    const other = {
      ...applicant,
      id: 'other-pending',
      teamId: 'other-green-team',
      status: '지원완료' as const,
    };
    const records = [
      other,
      { ...other, id: 'other-reviewing', status: '검토중' as const },
      { ...other, id: 'other-contest', teamId: 'makers' },
      ...(['지원취소', '미선발', '폐기'] as const).map((status) => ({
        ...other,
        id: `history-${status}`,
        status,
      })),
      { ...other, id: 'another-person', personId: 'sua' },
    ];
    before.applicants.push(...records);
    before.applications.push(...records);
    const next = selectTeamApplicant(before, applicant.id, initialProfile)!;
    for (const collection of [next.applicants, next.applications]) {
      expect(
        collection.find((item) => item.id === 'other-pending')?.status,
      ).toBe('폐기');
      expect(
        collection.find((item) => item.id === 'other-reviewing')?.status,
      ).toBe('폐기');
      for (const old of records.slice(2)) {
        expect(collection.find((item) => item.id === old.id)).toEqual(old);
      }
    }
    expect(selectTeamApplicant(next, other.id, initialProfile)).toBeNull();
    const notifications = transitionNotifications(
      before,
      next,
      'selection-event',
      '2026-10-19T00:00:00Z',
    );
    expect(
      notifications.map((item) => [item.applicationId, item.status]),
    ).toEqual([
      ['other-pending', '폐기'],
      ['other-reviewing', '폐기'],
      [applicant.id, '선발'],
    ]);
    expect(
      notifications.every(
        (item) =>
          item.recipient.kind === 'person' &&
          item.recipient.personId === applicant.personId,
      ),
    ).toBe(true);
    expect(appendNotifications(notifications, notifications)).toEqual(
      notifications,
    );
    expect(
      transitionNotifications(next, next, 'retry', '2026-10-19T00:00:01Z'),
    ).toEqual([]);
    const full = {
      ...before,
      teams: before.teams.map((team) =>
        team.id === 'greenwave' ? { ...team, members: team.capacity } : team,
      ),
    };
    expect(selectTeamApplicant(full, applicant.id, initialProfile)).toBeNull();
    expect(
      before.applications.find((item) => item.id === other.id)?.status,
    ).toBe('지원완료');
  });

  it('closes on the last selected seat and keeps it closed when that seat is returned', () => {
    const before = state();
    before.teams = before.teams.map((team) =>
      team.id === 'greenwave'
        ? { ...team, capacity: 3, status: '지원자검토' }
        : team,
    );
    const selected = selectTeamApplicant(
      before,
      'app-seoyeon',
      initialProfile,
    )!;
    expect(selected.teams.find((team) => team.id === 'greenwave')?.status).toBe(
      '모집마감',
    );
    const memberView = {
      ...selected,
      teams: selected.teams.map((team) =>
        team.id === 'greenwave'
          ? {
              ...team,
              owner: false,
              memberProfiles: team.memberProfiles.map((member) => ({
                ...member,
                id:
                  member.id === 'seoyeon'
                    ? 'me'
                    : member.id === 'me'
                      ? 'leader'
                      : member.id,
              })),
            }
          : team,
      ),
      applications: [{ ...selected.applicants[0]!, personId: 'me' }],
    };
    const cancelled = cancelTeamApplication(memberView, 'app-seoyeon')!;
    const team = cancelled.teams.find((item) => item.id === 'greenwave')!;
    expect(team.members).toBe(2);
    expect(team.status).toBe('모집마감');
    expect(recruitmentIssue(team)).toMatch(/모집이 마감/);
    expect(reopenTeamRecruitment(cancelled, team.id)).toBeNull();
    const leaderView = {
      ...cancelled,
      teams: cancelled.teams.map((item) =>
        item.id === team.id ? { ...item, owner: true } : item,
      ),
    };
    const reopened = reopenTeamRecruitment(leaderView, team.id)!;
    expect(
      recruitmentIssue(reopened.teams.find((item) => item.id === team.id)!),
    ).toBeNull();
    expect(reopened.applications).toEqual(cancelled.applications);
  });

  it('keeps discarded history unchanged after selected cancellation and explicit reopening', () => {
    const before = lifecycleReferenceActivity();
    const cancelled = cancelTeamApplication(before, 'application-localcrew')!;
    expect(
      cancelled.applications.find((item) => item.status === '폐기'),
    ).toEqual(before.applications.find((item) => item.status === '폐기'));
    const reopened = reopenTeamRecruitment(cancelled, 'greenwave')!;
    expect(reopened.applicants).toEqual(cancelled.applicants);
    expect(reopened.applications).toEqual(cancelled.applications);
    expect(reopenTeamRecruitment(reopened, 'greenwave')).toBeNull();
  });

  it('does not reinterpret the unresolved team-finalized state when a member cancels', () => {
    const before = state();
    before.teams = before.teams.map((team) =>
      team.id === 'localcrew' ? { ...team, status: '팀원확정' } : team,
    );
    const next = cancelTeamApplication(before, 'application-localcrew')!;
    expect(next.teams.find((team) => team.id === 'localcrew')?.status).toBe(
      '팀원확정',
    );
  });

  it('checks authority, seats and exact time boundaries when reopening', () => {
    const team = {
      ...initialTeams[1]!,
      status: '모집마감' as const,
      recruitmentDeadline: '2026-10-18',
    };
    const cutoff = Date.parse('2026-10-18T15:00:00Z');
    expect(recruitmentReopeningIssue(team, cutoff - 1)).toBeNull();
    expect(recruitmentReopeningIssue(team, cutoff)).toMatch(/기한/);
    expect(
      recruitmentReopeningIssue({ ...team, owner: false }, cutoff - 1),
    ).toMatch(/팀장만/);
    expect(
      recruitmentReopeningIssue(
        { ...team, members: team.capacity },
        cutoff - 1,
      ),
    ).toMatch(/정원/);
    expect(
      recruitmentReopeningIssue({ ...team, contestId: 'upcoming' }),
    ).toMatch(/접수가 시작/);
    expect(
      recruitmentReopeningIssue({
        ...team,
        contestId: 'solo',
        capacity: 1,
        members: 1,
      }),
    ).toMatch(/정원/);
    expect(
      recruitmentReopeningIssue(team, Date.parse('2026-12-01T00:00:00Z')),
    ).toMatch(/공모전 접수가 마감/);
  });
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
      publicProfile,
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
      publicProfile,
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
      applyToTeam(second, publicProfile, 'makers', '기획', '', 'new-3'),
    ).toBeNull();
  });
  it('accepts applications during review, but blocks deadline, full capacity, and missing profile', () => {
    const before = state();
    before.teams = before.teams.map((team) =>
      team.id === 'makers' ? { ...team, status: '지원자검토' } : team,
    );
    expect(
      applyToTeam(before, publicProfile, 'makers', '기획', '', 'review-new'),
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
        publicProfile,
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
      applyToTeam(before, publicProfile, 'makers', '기획', '', 'full'),
    ).toBeNull();
    before.teams = before.teams.map((team) =>
      team.id === 'makers'
        ? { ...team, capacity: 10, recruitmentDeadline: '2026-10-17' }
        : team,
    );
    expect(
      applyToTeam(before, publicProfile, 'makers', '기획', '', 'expired'),
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
      skills: ['프로그래밍', 'UI/UX'],
      interests: ['사회·문화'],
      availability: '5~10시간 미만',
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
      skills: ['프로그래밍', 'UI/UX'],
      interests: ['사회·문화'],
      availability: '5~10시간 미만',
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
      availability: '10~20시간 미만',
      portfolio: 'https://example.com/current',
      portfolioTitle: '현재 포트폴리오',
    };
    expect(applicantVisibleProfile(applicant, current)).toMatchObject({
      name: '수정된 이름',
      intro: '수정된 자기소개',
      availability: '10~20시간 미만',
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

describe('normalized team policies', () => {
  const input = {
    name: '새 도전',
    summary: '공모전을 함께 준비하고 완성해요.',
    contestId: 'campus',
    roles: ['기획'],
    interests: ['교육', 'IT·기술'],
    capacity: 3,
    recruitmentDeadline: '2026-11-01',
  };
  it('requires a public profile only for a new application and allows unspecified academic fields', () => {
    expect(
      applyToTeam(state(), initialProfile, 'makers', '기획', '', 'private'),
    ).toBeNull();
    const next = applyToTeam(
      state(),
      { ...publicProfile, academicStatus: '', grade: '' },
      'makers',
      '기획',
      '',
      'new',
    );
    expect(next?.applications.at(-1)?.status).toBe('지원완료');
    expect(
      cancelTeamApplication(state(), initialApplications[0]!.id),
    ).not.toBeNull();
  });
  it('does not introduce the undecided cross-team application restriction', () => {
    const before = state();
    before.teams.push({
      ...initialTeams[0]!,
      id: 'same-contest-member',
      owner: true,
    });
    expect(
      applyToTeam(before, publicProfile, 'makers', '기획', '', 'new'),
    ).not.toBeNull();
  });
  it('enforces name, summary and role boundaries without treating whitespace as content', () => {
    expect(createTeamIssue({ ...input, name: ' 가 ' }, [])).toMatch(/2~40/);
    expect(createTeamIssue({ ...input, summary: ' '.repeat(12) }, [])).toMatch(
      /10~/,
    );
    expect(createTeamIssue({ ...input, name: '가'.repeat(41) }, [])).toMatch(
      /2~40/,
    );
    expect(createTeamIssue({ ...input, roles: [] }, [])).toMatch(/역할/);
    expect(createTeamIssue({ ...input, roles: ['임의역할'] }, [])).toMatch(
      /역할/,
    );
    expect(createTeamIssue({ ...input, roles: ['기획', '기획'] }, [])).toMatch(
      /역할/,
    );
  });
  it('uses fixed official one-person capacity, omits roles and applies no arbitrary unlimited ceiling', () => {
    expect(
      createTeamIssue(
        { ...input, contestId: 'solo', capacity: 1, roles: [] },
        [],
      ),
    ).toBeNull();
    expect(
      createTeamIssue({ ...input, contestId: 'solo', capacity: 2 }, []),
    ).toMatch(/공식 참가 인원/);
    expect(
      createTeamIssue({ ...input, contestId: 'solo', capacity: 1 }, []),
    ).toMatch(/1명/);
    expect(
      createTeamIssue({ ...input, contestId: 'open-lab', capacity: 1000 }, []),
    ).toBeNull();
    expect(createTeamIssue({ ...input, capacity: NaN }, [])).toMatch(/정원/);
    expect(createTeamIssue({ ...input, contestId: 'upcoming' }, [])).toMatch(
      /접수 중/,
    );
  });
  it('closes at the exact team or contest boundary, whichever is earlier', () => {
    const team = { ...initialTeams[0]!, recruitmentDeadline: '2026-10-18' };
    const cutoff = Date.parse('2026-10-18T15:00:00Z');
    expect(recruitmentIssue(team, cutoff - 1)).toBeNull();
    expect(recruitmentIssue(team, cutoff)).toMatch(/기한/);
    const solo = {
      ...team,
      contestId: 'solo',
      recruitmentDeadline: '2026-11-20',
    };
    expect(teamRecruitmentDeadline(solo)).toBe(
      Date.parse('2026-11-20T09:00:00Z'),
    );
    expect(contests.find((contest) => contest.id === 'local')?.minMembers).toBe(
      2,
    );
    expect(initialTeams.find((item) => item.id === 'localcrew')?.members).toBe(
      3,
    );
  });
});
