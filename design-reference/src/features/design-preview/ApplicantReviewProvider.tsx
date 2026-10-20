import { useState, type ReactNode } from 'react';
import { usePreview } from './preview-context';
import {
  ApplicantReviewContext,
  type ApplicantReviewResult,
} from './applicant-review-state';

export function ApplicantReviewProvider({ children }: { children: ReactNode }) {
  const { signedIn } = usePreview();
  return (
    <ReviewSession key={signedIn ? 'member' : 'guest'}>
      {children}
    </ReviewSession>
  );
}

function ReviewSession({ children }: { children: ReactNode }) {
  const [results, setResults] = useState<Record<string, ApplicantReviewResult>>(
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
