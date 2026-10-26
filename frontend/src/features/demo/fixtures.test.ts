/**
 * [참조 출처]
 * 1. docs/api/README.md#consistency - 필드·타입·필수값·NULL이 계약과 일치하는지 대조
 * 2. docs/development/testing.md - 「의미 있는 테스트」 데이터 무결성
 * 3. docs/design/screens.md - 「재현 경로」 scenario=team-lifecycle 목업도 같은 계약을 따름
 *
 * 모든 목업 레코드가 영역별 API 응답 스키마를 그대로 통과하는지 확인해, 목업과 계약이 어긋나지 않게 합니다.
 */

import { describe, expect, it } from 'vitest';
import { Account } from '@/features/auth/api';
import { AcademicUnit, Catalogs } from '@/features/catalogs/api';
import { ContestDetail, ContestSummary } from '@/features/contests/api';
import { Profile } from '@/features/profiles/api';
import { TeamDetail, TeamMember, TeamSummary } from '@/features/teams/api';
import { Application } from '@/features/applications/api';
import { Notification } from '@/features/notifications/api';
import {
  createDemoRecords,
  deriveContest,
  deriveTeam,
  toContestSummary,
  toNotificationDto,
  toTeamMember,
  toTeamSummary,
  type DemoDatabase,
} from '@/features/demo/fixtures';
import { lifecycleReferenceDatabase } from '@/features/demo/lifecycle-fixtures';
import { historyNotifications } from '@/features/demo/notification-state';

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
      expect(() =>
        ContestDetail.parse(deriveContest(seed, records)),
      ).not.toThrow();
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
      expect(() => TeamDetail.parse(team)).not.toThrow();
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

  // [출처 1, 3] 목록 카드 변환·비공개 구성원·수명주기 시나리오·가져온 이력까지 같은 스키마로 검증
  it.each([
    ['default records', createDemoRecords()],
    ['team-lifecycle scenario', lifecycleReferenceDatabase()],
  ] as [string, DemoDatabase][])(
    'summaries, hidden members and history in %s',
    (_, db) => {
      for (const seed of db.contests)
        expect(() =>
          ContestSummary.parse(toContestSummary(deriveContest(seed, db))),
        ).not.toThrow();
      for (const record of db.teams) {
        const team = deriveTeam(record, db);
        expect(() => TeamDetail.parse(team)).not.toThrow();
        expect(() => TeamSummary.parse(toTeamSummary(team))).not.toThrow();
        for (const membership of db.memberships.filter(
          (item) => item.teamId === team.id,
        ))
          expect(() =>
            TeamMember.parse(
              toTeamMember(membership, db.profiles, () => false),
            ),
          ).not.toThrow();
      }
      for (const profile of db.profiles)
        expect(() => Profile.parse(profile)).not.toThrow();
      for (const application of db.applications)
        expect(() => Application.parse(application)).not.toThrow();
      const history = historyNotifications(db, () => crypto.randomUUID());
      for (const notification of [...db.notifications, ...history])
        expect(() =>
          Notification.parse(toNotificationDto(notification)),
        ).not.toThrow();
    },
  );
});
