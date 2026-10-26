/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/ApplicantReviewProvider.tsx - 검토 결과 세션 상태 원본
 * 2. docs/design/verification.md - 화면 이동 후 결과 유지, 로그아웃 시 제거
 *
 * 지원자 AI 검토 API는 docs/api/ai.md에서 미구현·SSE 검토안이라, 검토 결과는 화면 데모로 현재 세션에만 보관합니다.
 */

import { useState, type ReactNode } from 'react';
import { useSession } from '@/features/auth/queries';
import {
  ApplicantReviewContext,
  type ApplicantReviewFacts,
} from '@/features/demo/applicant-review-state';

// [출처 2] 현재 세션의 검토 결과 보관. 계정이 바뀌면 결과만 비우고 화면은 다시 마운트하지 않습니다
// (가입 직후 자동 로그인에서 완료 화면이 사라지지 않도록).
export function ApplicantReviewProvider({ children }: { children: ReactNode }) {
  const { account } = useSession();
  const owner = account?.id ?? null;
  const [store, setStore] = useState<{
    owner: string | null;
    results: Record<string, ApplicantReviewFacts>;
  }>({ owner, results: {} });
  // 로그아웃(owner null)과 다른 계정 로그인 모두 결과를 비웁니다.
  if (store.owner !== owner) setStore({ owner, results: {} });
  const results = store.owner === owner ? store.results : {};
  return (
    <ApplicantReviewContext
      value={{
        results,
        save: (id, result) =>
          setStore((previous) => ({
            owner,
            results: {
              ...(previous.owner === owner ? previous.results : {}),
              [id]: result,
            },
          })),
      }}
    >
      {children}
    </ApplicantReviewContext>
  );
}
