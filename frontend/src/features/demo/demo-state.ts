/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - 본인 알림만 노출, 수신자 정보는 응답에 없음
 * 2. docs/api/README.md - 화면 상태의 각 항목은 API DTO 모양
 *
 * 목업 저장소에서 화면이 읽는 값(DemoState의 읽기 항목)을 계산합니다. DemoProvider와 테스트가 함께 사용합니다.
 */

import type { DemoState } from '@/features/demo/demo-context';
import { toNotificationDto, type DemoDatabase } from '@/features/demo/fixtures';
import { isNotificationRecipient } from '@/features/demo/notification-state';
import {
  allContests,
  allTeams,
  profileOf,
  teamMembers,
} from '@/features/demo/team-state';

export type DemoReadState = Pick<
  DemoState,
  | 'signedIn'
  | 'db'
  | 'account'
  | 'profile'
  | 'contests'
  | 'teams'
  | 'applications'
  | 'notifications'
  | 'teamMembers'
>;

export function deriveDemoState(
  db: DemoDatabase,
  signedIn: boolean,
): DemoReadState {
  const accountId = db.account.id;
  return {
    signedIn,
    db,
    account: db.account,
    profile: profileOf(db, accountId)!,
    contests: allContests(db),
    teams: allTeams(db),
    applications: db.applications,
    // [출처 1] 현재 수신자 관계가 유지되는 본인 알림
    notifications: db.notifications
      .filter((item) => isNotificationRecipient(item, db, accountId))
      .map(toNotificationDto),
    teamMembers: (teamId) => teamMembers(db, teamId, accountId),
  };
}
