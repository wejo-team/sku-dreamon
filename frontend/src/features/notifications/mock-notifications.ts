/**
 * [참조 출처]
 * 1. docs/design/screens.md - 상단 알림함 명세
 * 2. design-reference/src/features/design-preview/notification-state.ts - 알림 예시 원본
 *
 * [PR #120 리뷰 반영] 알림 fixture를 공용 mock-data.ts에서 소비 기능 옆으로 옮겼습니다.
 * 화면 확인용 예시 타입·데이터이며 서버 응답 계약이 아닙니다. 실제 계약은 docs/api/notifications.md를 따르고,
 * API 연동 시 이 파일을 그대로 계약 타입으로 승격하지 않습니다.
 */

export interface NotificationItem {
  id: string;
  title: string;
  description: string;
  kind: 'application' | 'applicant';
  read: boolean;
  to: string;
  occurredAt?: string;
}

export const initialNotifications: NotificationItem[] = [
  {
    id: 'notif-1',
    title: '지원이 접수됐어요',
    description: '스마트 캠퍼스 지도 팀에 개발 역할로 지원이 완료되었어요.',
    kind: 'application',
    read: false,
    to: '/workspace?view=applications',
    occurredAt: '방금 전',
  },
  {
    id: 'notif-2',
    title: '다른 팀 선발로 대기 지원이 폐기됐어요',
    description: '성북 청년 공방 팀 지원이 폐기 처리되었어요.',
    kind: 'application',
    read: true,
    to: '/workspace?view=applications',
    occurredAt: '어제',
  },
];
