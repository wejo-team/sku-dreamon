/**
 * [참조 출처]
 * 1. docs/api/auth.md#account-endpoints - 가입 201·로그인 200·로그아웃 204·GET /me, 409 LOGIN_ID_TAKEN, 401 INVALID_CREDENTIALS
 * 2. docs/api/auth.md#credentials - loginId 정규화(trim·소문자·^[a-z0-9]{4,24}$), password NFC 15~128 코드 포인트
 * 3. docs/api/catalogs.md#catalog-endpoints - GET /catalogs, GET /catalogs/academic-units
 * 4. docs/api/contests.md#queries - 공모전 검색 대상·필터·정렬(created_desc, deadline_asc)
 * 5. docs/api/profiles.md#profile-endpoints - 프로필 저장 버전 규칙(최초 "0"), 공개 전환 no-op 200
 * 6. docs/api/profiles.md#experience - 경험 상태·본문 정규화
 * 7. docs/api/profiles.md#directory-endpoints - 공개 프로필만, 정렬 updatedAt DESC, accountId ASC
 * 8. docs/design/handoff.md - 공개 UI 확인용 계정(dreamondemo)은 실제 계정이 아님
 */

import { z } from 'zod';
import { Credentials, type Account } from '@/features/auth/api';
import { RegistrationStatus } from '@/features/contests/api';
import {
  ProfileWrite,
  VisibilityWrite,
  type Profile,
} from '@/features/profiles/api';
import {
  demoPassword,
  normalizeLoginId,
  normalizePassword,
} from '@/features/demo/auth-policy';
import {
  MockRouter,
  conflict,
  fail,
  invalid,
  noContent,
  notFound,
  ok,
  paginate,
  searchText,
  validate,
} from '@/lib/api-mock/http';
import {
  assertVersion,
  bumpVersion,
  catalogHas,
  contestById,
  contestSummaries,
  db,
  newId,
  nowIso,
  profileOf,
  requireSession,
  state,
} from '@/lib/api-mock/state';

const LOGIN_ID = /^[a-z0-9]{4,24}$/;

// [출처 2] 입력 정규화 후 형식 검사. 실패는 422(원문을 오류에 넣지 않음)
function normalizedCredentials(body: unknown) {
  const raw = validate(Credentials, body);
  const loginId = normalizeLoginId(raw.loginId);
  if (!LOGIN_ID.test(loginId))
    invalid(['body', 'loginId'], '아이디 형식이 올바르지 않아요.');
  const password = normalizePassword(raw.password);
  const length = Array.from(password).length;
  if (length < 15 || length > 128)
    invalid(['body', 'password'], '비밀번호 길이가 올바르지 않아요.');
  return { loginId, password };
}

// 목업 계정 저장소: 데모 계정 + 목업에서 가입한 계정
const signedUp = new Map<string, { account: Account; password: string }>();

function accountById(accountId: string): Account | undefined {
  const demo = db().account;
  if (demo.id === accountId)
    return { ...demo, hasProfile: !!profileOf(demo.id) };
  for (const entry of signedUp.values())
    if (entry.account.id === accountId)
      return { ...entry.account, hasProfile: !!profileOf(accountId) };
  return undefined;
}

export function registerAccountRoutes(router: MockRouter) {
  router
    // [출처 1, 2] 가입 → 201, 자동 로그인
    .on('POST', '/accounts', ({ body }) => {
      const { loginId, password } = normalizedCredentials(body);
      if (loginId === db().account.loginId || signedUp.has(loginId))
        conflict('LOGIN_ID_TAKEN', '이미 사용 중인 아이디예요.');
      const account: Account = {
        id: newId(),
        loginId,
        isDemo: false,
        hasProfile: false,
        schoolVerification: 'unverified',
        createdAt: nowIso(),
      };
      signedUp.set(loginId, { account, password });
      state.sessionAccountId = account.id;
      return ok({ account }, 201);
    })
    // [출처 1, 2] 아이디 중복 확인
    .on('GET', '/auth/login-id-availability', ({ query }) => {
      const raw = query.get('loginId');
      if (raw === null) invalid(['query', 'loginId'], 'loginId가 필요해요.');
      const normalizedLoginId = normalizeLoginId(raw!);
      if (!LOGIN_ID.test(normalizedLoginId))
        invalid(['query', 'loginId'], '아이디 형식이 올바르지 않아요.');
      return ok({
        normalizedLoginId,
        available:
          normalizedLoginId !== db().account.loginId &&
          !signedUp.has(normalizedLoginId),
      });
    })
    // [출처 1, 8] 로그인. 아이디 존재 여부를 구분하지 않는 INVALID_CREDENTIALS
    .on('POST', '/auth/login', ({ body }) => {
      const { loginId, password } = normalizedCredentials(body);
      const demo = db().account;
      const entry =
        loginId === demo.loginId && password === demoPassword
          ? { account: demo }
          : signedUp.get(loginId)?.password === password
            ? signedUp.get(loginId)
            : undefined;
      if (!entry)
        fail(
          401,
          'INVALID_CREDENTIALS',
          '아이디 또는 비밀번호를 확인해 주세요.',
        );
      state.sessionAccountId = entry!.account.id;
      return ok({ account: accountById(entry!.account.id)! });
    })
    // [출처 1] 로그아웃 → 204
    .on('POST', '/auth/logout', () => {
      requireSession();
      state.sessionAccountId = null;
      return noContent();
    })
    .on('GET', '/me', () => ok(accountById(requireSession())!))
    // [출처 3]
    .on('GET', '/catalogs', () => ok(db().catalogs))
    .on('GET', '/catalogs/academic-units', () => ok(db().academicUnits))
    // [출처 4] 공모전 목록: 제목·주최자·분야 표시명 검색
    .on('GET', '/contests', ({ query }) => {
      const q = searchText(query);
      const fieldCode = query.get('fieldCode');
      const sort = query.get('sort') ?? 'created_desc';
      if (!['created_desc', 'deadline_asc'].includes(sort))
        invalid(['query', 'sort'], 'sort 값이 올바르지 않아요.');
      const statusRaw = query.get('registrationStatus');
      const status =
        statusRaw === null
          ? null
          : validate(RegistrationStatus, statusRaw, 'query');
      const fieldName = (code: string) =>
        db().catalogs.fields.find((item) => item.code === code)?.displayName ??
        '';
      const items = contestSummaries()
        .filter((item) => !fieldCode || item.fieldCodes.includes(fieldCode))
        .filter((item) => !status || item.registrationStatus === status)
        .filter(
          (item) =>
            !q ||
            [item.title, item.organizer, ...item.fieldCodes.map(fieldName)]
              .join(' ')
              .toLowerCase()
              .includes(q),
        )
        .sort((left, right) =>
          sort === 'deadline_asc'
            ? left.endsAt.localeCompare(right.endsAt) ||
              left.id.localeCompare(right.id)
            : right.createdAt.localeCompare(left.createdAt) ||
              right.id.localeCompare(left.id),
        );
      return pageResponse(paginate(items, query));
    })
    .on('GET', '/contests/{contestId}', ({ params }) =>
      ok(contestById(params.contestId!) ?? notFound()),
    )
    // [출처 5] 본인 프로필
    .on('GET', '/me/profile', () =>
      ok(profileOf(requireSession()) ?? notFound()),
    )
    .on('PUT', '/me/profile', ({ body }) => {
      const accountId = requireSession();
      const write = validate(ProfileWrite, body);
      const existing = profileOf(accountId);
      assertVersion(existing?.version ?? '0', write.expectedVersion);
      // [출처 5] 선택 코드는 현재 선택 가능한 카탈로그 항목이어야 함
      const codes: [Parameters<typeof catalogHas>[0], (string | null)[]][] = [
        ['fields', write.fieldCodes],
        ['roles', write.roleCodes],
        ['skills', write.skillCodes],
        ['academicStatuses', [write.academicStatusCode]],
        ['grades', [write.gradeCode]],
        ['weeklyAvailabilityRanges', [write.weeklyAvailabilityCode]],
        ['avatarPresets', [write.profileImageCode]],
      ];
      for (const [list, values] of codes)
        for (const code of values)
          if (code !== null && !catalogHas(list, code))
            conflict(
              'INVALID_CATALOG_SELECTION',
              '선택지를 다시 확인해 주세요.',
            );
      if (
        write.academicUnitId !== null &&
        !db().academicUnits.some((unit) => unit.id === write.academicUnitId)
      )
        conflict('INVALID_ACADEMIC_PATH', '학사 정보를 다시 확인해 주세요.');
      // [출처 6] 공백 제거 후 빈 본문은 unspecified·null
      const body500 = write.experienceBody?.trim() || null;
      const experienceState =
        write.experienceState === 'provided' && !body500
          ? 'unspecified'
          : write.experienceState;
      const saved: Profile = {
        realName: write.realName.trim(),
        profileImageCode: write.profileImageCode,
        academicStatusCode: write.academicStatusCode,
        gradeCode: write.gradeCode,
        weeklyAvailabilityCode: write.weeklyAvailabilityCode,
        academicUnitId: write.academicUnitId,
        fieldCodes: write.fieldCodes,
        roleCodes: write.roleCodes,
        skillCodes: write.skillCodes,
        portfolio: write.portfolio,
        introduction: write.introduction?.trim() || null,
        experienceState,
        experienceBody: experienceState === 'provided' ? body500 : null,
        accountId,
        version: existing ? bumpVersion(existing.version) : '1',
        isPublic: existing?.isPublic ?? false,
        isDemo: existing?.isDemo ?? false,
        updatedAt: nowIso(),
      };
      db().profiles = [
        ...db().profiles.filter((item) => item.accountId !== accountId),
        saved,
      ];
      return ok(saved);
    })
    // [출처 5] 공개 전환. 버전을 먼저 비교하고 같은 상태면 변경 없이 200
    .on('PUT', '/me/profile/visibility', ({ body }) => {
      const accountId = requireSession();
      const write = validate(VisibilityWrite, body);
      const existing = profileOf(accountId) ?? notFound();
      assertVersion(existing.version, write.expectedVersion);
      if (existing.isPublic === write.isPublic) return ok(existing);
      const saved: Profile = {
        ...existing,
        isPublic: write.isPublic,
        version: bumpVersion(existing.version),
        updatedAt: nowIso(),
      };
      db().profiles = db().profiles.map((item) =>
        item.accountId === accountId ? saved : item,
      );
      return ok(saved);
    })
    // [출처 7] 공개 사람 탐색
    .on('GET', '/people', ({ query }) => {
      requireSession();
      const q = searchText(query);
      const fieldCode = query.get('fieldCode');
      const roleCode = query.get('roleCode');
      const label = (list: 'fields' | 'roles' | 'skills', code: string) =>
        db().catalogs[list].find((item) => item.code === code)?.displayName ??
        '';
      const items = db()
        .profiles.filter((item) => item.isPublic)
        .filter((item) => !fieldCode || item.fieldCodes.includes(fieldCode))
        .filter((item) => !roleCode || item.roleCodes.includes(roleCode))
        .filter(
          (item) =>
            !q ||
            [
              item.realName,
              item.introduction ?? '',
              ...item.fieldCodes.map((code) => label('fields', code)),
              ...item.roleCodes.map((code) => label('roles', code)),
              ...item.skillCodes.map((code) => label('skills', code)),
            ]
              .join(' ')
              .toLowerCase()
              .includes(q),
        )
        .sort(
          (left, right) =>
            right.updatedAt.localeCompare(left.updatedAt) ||
            left.accountId.localeCompare(right.accountId),
        )
        .map((item) => ({
          accountId: item.accountId,
          realName: item.realName,
          isDemo: item.isDemo,
          profileImageCode: item.profileImageCode,
          introduction: item.introduction,
          fieldCodes: item.fieldCodes,
          roleCodes: item.roleCodes,
          skillCodes: item.skillCodes,
        }));
      return pageResponse(paginate(items, query));
    })
    // [출처 7] 비공개·미존재는 같은 404
    .on('GET', '/people/{accountId}', ({ params }) => {
      requireSession();
      const person = profileOf(params.accountId!);
      return ok(person?.isPublic ? person : notFound());
    });
}

export const pageResponse = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

export const parseOptionalQuery = <T extends z.ZodTypeAny>(
  schema: T,
  value: string | null,
  key: string,
): z.infer<T> | null => {
  if (value === null) return null;
  const result = schema.safeParse(value);
  if (!result.success) invalid(['query', key], `${key} 값이 올바르지 않아요.`);
  return result.data;
};
