/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ApplicantReviewProvider.tsx - 검토 결과 세션 상태 원본
 * 2. docs/design/verification.md - 화면 이동 후 결과 유지, 로그아웃 시 제거
 *
 * 화면 확인용 메모리 상태·예시 데이터입니다. 서버 계약이 아니며 API 연동 시 기능별 TanStack Query로 교체합니다(handoff.md 「제품 구현에 옮기는 순서」 3단계).
 */

import { useState, type ReactNode } from 'react';
import { useDemo } from '@/features/demo/demo-context';
import {
  ApplicantReviewContext,
  type ApplicantReviewFacts,
} from '@/features/demo/applicant-review-state';

// [출처 2] 현재 세션의 검토 결과 보관
export function ApplicantReviewProvider({ children }: { children: ReactNode }) {
  const { signedIn } = useDemo();
  return (
    <ReviewSession key={signedIn ? 'member' : 'guest'}>
      {children}
    </ReviewSession>
  );
}

function ReviewSession({ children }: { children: ReactNode }) {
  const [results, setResults] = useState<Record<string, ApplicantReviewFacts>>(
    {},
  );
  return (
    <ApplicantReviewContext
      value={{
        results,
        save: (id, result) =>
          setResults((previous) => ({ ...previous, [id]: result })),
      }}
    >
      {children}
    </ApplicantReviewContext>
  );
}
