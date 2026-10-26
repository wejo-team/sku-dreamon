/**
 * [참조 출처]
 * 1. docs/api/profiles.md#profile-endpoints - GET/PUT /me/profile(미저장 404), PUT /me/profile/visibility
 * 2. docs/api/profiles.md#directory-endpoints - GET /people, GET /people/{accountId}(비공개·미존재 404)
 * 3. docs/development/frontend.md - 「API와 query」 mutation 성공 시 영향받은 query 갱신
 * 4. docs/api/conventions.md#versioned-action - 프로필 수정·공개 전환 409 후 다시 조회
 */

import {
  queryOptions,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query';
import {
  getMyProfile,
  getPerson,
  listPeople,
  putMyProfile,
  putMyProfileVisibility,
  type PeopleQuery,
  type Profile,
  type ProfileWrite,
  type VisibilityWrite,
} from '@/features/profiles/api';
import { ApiError } from '@/lib/api';
import { isConflict, queryKeys } from '@/lib/query-keys';

// [출처 1] 아직 저장한 프로필이 없으면(404) null
export const myProfileQueryOptions = queryOptions({
  queryKey: queryKeys.myProfile,
  queryFn: async ({ signal }): Promise<Profile | null> => {
    try {
      return await getMyProfile(signal);
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) return null;
      throw error;
    }
  },
});

export const peopleQueryOptions = (query: PeopleQuery = {}) =>
  queryOptions({
    queryKey: queryKeys.people(query),
    queryFn: ({ signal }) => listPeople(query, signal),
  });

export const personQueryOptions = (accountId: string) =>
  queryOptions({
    queryKey: queryKeys.person(accountId),
    queryFn: ({ signal }) => getPerson(accountId, signal),
  });

// [출처 1, 3] 저장 결과로 내 프로필을 바꾸고, 공개 범위가 반영되는 사람·팀·지원 조회를 다시 받습니다.
function useProfileMutation<Input>(
  request: (input: Input) => Promise<Profile>,
) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: request,
    onSuccess: async (profile) => {
      client.setQueryData(queryKeys.myProfile, profile);
      await Promise.all(
        [['auth'], ['people'], ['teams'], ['applications']].map((queryKey) =>
          client.invalidateQueries({ queryKey }),
        ),
      );
    },
    // [출처 4] 다른 변경이 먼저 저장됐다면 최신 프로필 버전을 다시 받습니다.
    onError: (error) =>
      isConflict(error)
        ? client.invalidateQueries({ queryKey: queryKeys.myProfile })
        : undefined,
  });
}

export const useSaveProfile = () =>
  useProfileMutation((body: ProfileWrite) => putMyProfile(body));

export const useSaveVisibility = () =>
  useProfileMutation((body: VisibilityWrite) => putMyProfileVisibility(body));
