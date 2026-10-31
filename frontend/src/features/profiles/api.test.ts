// 교과목 확장 배포 전후의 프로필 응답과 구버전 편집 요청의 보존 계약을 검증합니다.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  Profile,
  getMyProfile,
  getPerson,
  putMyProfile,
  putMyProfileVisibility,
} from '@/features/profiles/api';
import { fixtureProfiles } from '@/features/demo/fixtures';
import { toFormValues, toProfileWrite } from '@/features/account/profile-form';
import { resetCsrfToken } from '@/lib/api';

const legacy = fixtureProfiles()[0]!;
const selectedCourses = [{ code: 'GE1394', name: 'AI리터러시와가치설계' }];

function respond(profile: unknown) {
  const fetch = vi
    .fn<typeof globalThis.fetch>()
    .mockImplementation(async (url) =>
      Response.json({
        data: String(url).endsWith('/auth/csrf')
          ? { csrfToken: 'profile-compat-csrf' }
          : profile,
      }),
    );
  vi.stubGlobal('fetch', fetch);
  return fetch;
}

beforeEach(() => resetCsrfToken());

describe('profile expansion compatibility', () => {
  it.each([
    ['legacy response', legacy],
    ['empty course response', { ...legacy, courses: [] }],
    ['selected course response', { ...legacy, courses: selectedCourses }],
  ])('reads %s for the owner and public detail', async (_, profile) => {
    respond(profile);
    await expect(getMyProfile()).resolves.toEqual(profile);
    await expect(getPerson(legacy.accountId)).resolves.toEqual(profile);
  });

  it.each([
    null,
    'GE1394',
    [{ code: '', name: '과목' }],
    [{ code: 1394, name: '과목' }],
    [{ code: 'GE1394', name: '' }],
    [{ code: 'GE1394', name: '과목', grade: 'A' }],
  ])('rejects malformed course data %j', (courses) => {
    expect(() => Profile.parse({ ...legacy, courses })).toThrow();
  });

  it('keeps unrelated response fields strict', () => {
    expect(() =>
      Profile.parse({
        ...legacy,
        courses: selectedCourses,
        unknownField: true,
      }),
    ).toThrow();
  });

  it('omits course writes after editing an expanded response and accepts expanded save responses', async () => {
    const expanded = { ...legacy, courses: selectedCourses };
    const fetch = respond(expanded);
    const current = await getMyProfile();
    const values = toFormValues(current, () => []);
    const write = toProfileWrite(
      { ...values, introduction: '소개 수정' },
      current,
    );
    await expect(putMyProfile(write)).resolves.toEqual(expanded);
    await expect(
      putMyProfileVisibility({
        expectedVersion: current.version,
        isPublic: true,
      }),
    ).resolves.toEqual(expanded);
    const profileSave = fetch.mock.calls.find(
      ([url, init]) =>
        String(url).endsWith('/me/profile') && init?.method === 'PUT',
    );
    expect(profileSave).toBeDefined();
    const body = JSON.parse(String(profileSave![1]?.body));
    expect(body.introduction).toBe('소개 수정');
    expect(body).not.toHaveProperty('courses');
    expect(body).not.toHaveProperty('courseCodes');
  });
});
