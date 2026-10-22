/**
 * [참조 출처]
 * 1. design-reference/src/pages/DesignPreviewPage.tsx - 정의되지 않은 경로의 EmptyState
 * 2. docs/design/screens.md - 「시작·없는 경로」 찾을 수 없는 경로에서 탐색으로 돌아가기
 */

import { ActionLink, EmptyState } from '@/components/common/CommonUi';

// [출처 1, 2] 공통 Shell 안에서 안내와 탐색 복귀 링크만 표시합니다.
export function NotFoundPage() {
  return (
    <EmptyState
      title="페이지를 찾을 수 없어요"
      description="탐색으로 돌아가 다시 시작해 주세요."
    >
      <ActionLink to="/explore">탐색으로</ActionLink>
    </EmptyState>
  );
}
