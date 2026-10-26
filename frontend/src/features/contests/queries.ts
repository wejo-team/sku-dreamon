/**
 * [참조 출처]
 * 1. docs/api/contests.md#endpoints - GET /contests(Page<ContestSummary>), GET /contests/{contestId}(ContestDetail)
 * 2. docs/api/contests.md#queries - q·fieldCode·registrationStatus·sort·page·pageSize
 * 3. docs/development/frontend.md - 「API와 query」 query key에 조회 조건 포함
 */

import { queryOptions } from '@tanstack/react-query';
import {
  getContest,
  listContests,
  type ContestListQuery,
} from '@/features/contests/api';
import { queryKeys } from '@/lib/query-keys';

// [출처 1, 2, 3]
export const contestsQueryOptions = (query: ContestListQuery = {}) =>
  queryOptions({
    queryKey: queryKeys.contests(query),
    queryFn: ({ signal }) => listContests(query, signal),
  });

export const contestQueryOptions = (contestId: string) =>
  queryOptions({
    queryKey: queryKeys.contest(contestId),
    queryFn: ({ signal }) => getContest(contestId, signal),
  });
