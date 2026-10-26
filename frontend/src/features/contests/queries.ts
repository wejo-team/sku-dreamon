/**
 * [참조 출처]
 * 1. docs/api/contests.md#endpoints - GET /contests(Page<ContestSummary>), GET /contests/{contestId}(ContestDetail)
 * 2. docs/api/contests.md#queries - q·fieldCode·registrationStatus·sort·page·pageSize
 * 3. docs/development/frontend.md - 「API와 query」 query key에 조회 조건 포함
 */

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
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

// [출처 1, 2] 팀 만들기 선택창: 접수 중 공모전을 서버에서 검색하고 페이지 단위로 더 받습니다.
export const openContestSearchOptions = (q: string) =>
  infiniteQueryOptions({
    queryKey: queryKeys.openContestSearch(q),
    queryFn: ({ pageParam, signal }) =>
      listContests(
        { registrationStatus: 'open', q, page: pageParam, pageSize: 20 },
        signal,
      ),
    initialPageParam: 1,
    getNextPageParam: ({ pagination }) =>
      pagination.page < pagination.totalPages ? pagination.page + 1 : undefined,
  });

export const contestQueryOptions = (contestId: string) =>
  queryOptions({
    queryKey: queryKeys.contest(contestId),
    queryFn: ({ signal }) => getContest(contestId, signal),
  });
