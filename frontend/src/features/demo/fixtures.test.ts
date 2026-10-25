/**
 * [참조 출처]
 * 1. docs/api/README.md#consistency - 필드·타입·필수값·NULL이 계약과 일치하는지 대조
 * 2. docs/development/testing.md - 「의미 있는 테스트」 데이터 무결성
 *
 * 모든 목업 레코드가 영역별 API 응답 스키마를 그대로 통과하는지 확인해, 목업과 계약이 어긋나지 않게 합니다.
 */

import { describe, expect, it } from 'vitest';
import { Account } from '@/features/auth/api';
import { AcademicUnit, Catalogs } from '@/features/catalogs/api';
import { Contest } from '@/features/contests/api';
import { Profile } from '@/features/profiles/api';
import { Team, TeamMember } from '@/features/teams/api';
import { Application } from '@/features/applications/api';
import { Notification } from '@/features/notifications/api';
import {
  createDemoRecords,
  deriveContest,
  deriveTeam,
  toNotificationDto,
  toTeamMember,
} from '@/features/demo/fixtures';

const records = createDemoRecords();

describe('demo fixtures follow the API contract', () => {
  it('account, catalogs and academic units', () => {
    expect(() => Account.parse(records.account)).not.toThrow();
    expect(() => Catalogs.parse(records.catalogs)).not.toThrow();
    for (const unit of records.academicUnits)
      expect(() => AcademicUnit.parse(unit)).not.toThrow();
    // 루트는 단과대학, 모든 부모 ID가 실제 항목을 가리킴
    const ids = new Set(records.academicUnits.map((unit) => unit.id));
    expect(
      records.academicUnits.every(
        (unit) => unit.parentId === null || ids.has(unit.parentId),
      ),
    ).toBe(true);
  });

  it.each(records.contests.map((seed) => [seed.title, seed] as const))(
    'contest %s',
    (_, seed) => {
      expect(() => Contest.parse(deriveContest(seed, records))).not.toThrow();
    },
  );

  it('profiles, applications and notifications', () => {
    for (const profile of records.profiles)
      expect(() => Profile.parse(profile)).not.toThrow();
    for (const application of records.applications)
      expect(() => Application.parse(application)).not.toThrow();
    for (const notification of records.notifications)
      expect(() =>
        Notification.parse(toNotificationDto(notification)),
      ).not.toThrow();
  });

  it('teams and current members with server-computed values', () => {
    for (const record of records.teams) {
      const team = deriveTeam(record, records);
      expect(() => Team.parse(team)).not.toThrow();
      for (const membership of records.memberships.filter(
        (item) => item.teamId === team.id,
      ))
        expect(() =>
          TeamMember.parse(
            toTeamMember(membership, records.profiles, () => true),
          ),
        ).not.toThrow();
    }
    const counts = records.teams.map((record) => deriveTeam(record, records));
    expect(
      counts.map((team) => [team.name, team.memberCount, team.isRecruiting]),
    ).toEqual([
      ['캠퍼스 메이커스', 2, true],
      ['그린웨이브', 2, true],
      ['로컬 크루', 3, false],
    ]);
  });
});
