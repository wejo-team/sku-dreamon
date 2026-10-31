// 서버가 과목 기능 이전 버전으로 돌아가도 일반 프로필 편집과 선택 초안을 보존합니다.
import { screen, within } from '@testing-library/react';
import { Route, Routes } from 'react-router';
import { describe, expect, it, vi } from 'vitest';
import { ProfilePage, PublicProfilePage, SignupPage } from './AccountPages';
import { createDemoRecords } from '@/features/demo/fixtures';
import { Profile } from '@/features/profiles/api';
import { toFormValues, toProfileWrite } from './profile-form';
import { ME, myProfile, renderWithApi, settled } from '@/test/render';
import { fill, setupUser } from '@/test/user';
import { queryKeys } from '@/lib/query-keys';

const course = { code: 'CS1001', name: '자료구조' };

function renderRollback(path: string, legacy: boolean) {
  const records = createDemoRecords();
  records.courses = [{ ...course, aliases: [], departments: [] }];
  records.profiles.find((profile) => profile.accountId === ME)!.courses = [
    course,
  ];
  records.profiles.find((profile) => profile.accountId === ME)!.isPublic = true;
  const view = renderWithApi(
    <Routes>
      <Route path="/profile" element={<ProfilePage />} />
      <Route path="/profile/public" element={<PublicProfilePage />} />
      <Route path="/signup" element={<SignupPage />} />
    </Routes>,
    { path, signedIn: path !== '/signup', db: records },
  );
  const server = { legacy };
  const writes: Record<string, unknown>[] = [];
  const send = globalThis.fetch;
  vi.stubGlobal('fetch', async (input: string, init: RequestInit = {}) => {
    const pathname = new URL(input, 'http://test.invalid').pathname;
    if (server.legacy && pathname.endsWith('/catalogs/courses'))
      return Response.json({ detail: 'Not Found' }, { status: 404 });
    if (pathname.endsWith('/me/profile') && init.method === 'PUT') {
      const body = JSON.parse(String(init.body)) as Record<string, unknown>;
      writes.push(body);
      if (server.legacy && 'courseCodes' in body)
        return Response.json(
          {
            detail: [
              {
                loc: ['body', 'courseCodes'],
                type: 'extra_forbidden',
                msg: '입력값을 확인해 주세요.',
              },
            ],
          },
          { status: 422 },
        );
    }
    const response = await send(input, init);
    if (
      server.legacy &&
      response.ok &&
      (pathname.endsWith('/me/profile') || pathname.includes('/people/'))
    ) {
      const body = await response.json();
      delete body.data.courses;
      return Response.json(body);
    }
    return response;
  });
  return { ...view, server, writes };
}

async function signupWithoutCourses(loginId = 'rollbackstudent') {
  const user = setupUser();
  await fill(user, screen.getByLabelText('아이디 (필수)'), loginId);
  await fill(user, screen.getByLabelText('비밀번호 (필수)'), 'Rollback2026!');
  await fill(user, screen.getByLabelText('이름 (필수)'), '김학생');
  await user.click(
    within(screen.getByRole('group', { name: /관심 분야/ })).getByLabelText(
      '교육',
    ),
  );
  await user.click(
    within(screen.getByRole('group', { name: /희망 역할/ })).getByLabelText(
      '기획',
    ),
  );
  return user;
}

describe('course service rollback', () => {
  it('distinguishes unsupported profiles from empty selections while keeping unknown fields strict', () => {
    const saved = createDemoRecords().profiles[0]!;
    const legacy = { ...saved };
    delete legacy.courses;
    const parsed = Profile.parse(legacy);
    expect(parsed.courses).toBeUndefined();
    expect(Profile.parse({ ...legacy, courses: [] }).courses).toEqual([]);
    expect(() => Profile.parse({ ...legacy, unexpected: true })).toThrow();
    const values = toFormValues(parsed, () => []);
    expect(toProfileWrite(values, parsed)).not.toHaveProperty('courseCodes');
    expect(toProfileWrite(values, null)).not.toHaveProperty('courseCodes');
    expect(toProfileWrite(values, saved)).toHaveProperty('courseCodes', []);
  });

  it('reads a legacy profile and edits other fields without clearing stored courses', async () => {
    const { client, writes } = renderRollback('/profile', true);
    await settled(client);
    expect(
      screen.getByText('지금은 수강과목을 확인할 수 없어요.'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('아직 수강과목을 선택하지 않았어요.'),
    ).not.toBeInTheDocument();
    const user = setupUser();
    await user.click(screen.getByRole('button', { name: '프로필 수정' }));
    await user.clear(screen.getByLabelText('자기소개 (선택)'));
    await fill(
      user,
      screen.getByLabelText('자기소개 (선택)'),
      '수강과목은 보존하고 소개만 수정',
    );
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    await screen.findByRole('button', { name: '프로필 수정' });
    expect(writes).toHaveLength(1);
    expect(writes[0]).not.toHaveProperty('courseCodes');
    expect(myProfile().courses).toEqual([course]);
    expect(myProfile().introduction).toBe('수강과목은 보존하고 소개만 수정');
    await user.click(screen.getByRole('link', { name: '공개된 모습 보기' }));
    expect(
      await screen.findByText('지금은 수강과목을 확인할 수 없어요.'),
    ).toBeInTheDocument();
  });

  it('allows signup without course selection against the legacy server and explains catalog 404', async () => {
    const { client, writes } = renderRollback('/signup', true);
    await settled(client);
    expect(
      await screen.findByText(
        '지금은 수강과목 선택을 사용할 수 없어요. 과목 선택 없이 계속할 수 있어요.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('선택한 과목 0개')).not.toBeInTheDocument();
    const user = await signupWithoutCourses();
    await user.click(screen.getByRole('button', { name: '회원가입' }));
    await screen.findByRole('link', { name: '프로필 완성하기' });
    expect(writes).toHaveLength(1);
    expect(writes[0]).not.toHaveProperty('courseCodes');
  });

  it.each([false, true])(
    'preserves an edit draft when rollback is discovered by %s refetch',
    async (refetch) => {
      const { client, server, writes } = renderRollback(
        '/profile?edit=details',
        false,
      );
      await settled(client);
      const user = setupUser();
      await user.clear(screen.getByLabelText('자기소개 (선택)'));
      await fill(
        user,
        screen.getByLabelText('자기소개 (선택)'),
        '저장 전 초안',
      );
      server.legacy = true;
      if (refetch) {
        await client.invalidateQueries({ queryKey: queryKeys.myProfile });
        await settled(client);
      }
      await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
      expect(
        await screen.findByText(/서비스가 업데이트되어 새로고침이 필요해요/),
      ).toBeInTheDocument();
      expect(screen.getByLabelText('자기소개 (선택)')).toHaveValue(
        '저장 전 초안',
      );
      expect(
        screen.getByRole('button', { name: '자료구조 (CS1001) 선택 해제' }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole('button', { name: '변경사항 저장' }),
      ).toBeDisabled();
      expect(
        screen.getByRole('button', { name: '새로고침' }),
      ).toBeInTheDocument();
      expect(writes).toHaveLength(refetch ? 0 : 1);
      expect(myProfile().courses).toEqual([course]);
      expect(myProfile().introduction).not.toBe('저장 전 초안');
    },
  );

  it('keeps selected signup courses visible after rollback and never retries without them', async () => {
    const { client, server, writes } = renderRollback('/signup', false);
    await settled(client);
    const user = await signupWithoutCourses('rollbackselected');
    await user.click(
      screen.getByRole('checkbox', { name: '자료구조 (CS1001)' }),
    );
    server.legacy = true;
    await user.click(screen.getByRole('button', { name: '회원가입' }));
    expect(
      await screen.findByText(/서비스가 업데이트되어 새로고침이 필요해요/),
    ).toBeInTheDocument();
    expect(screen.getByText('자료구조 (CS1001)')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '프로필 다시 저장' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '새로고침' }),
    ).toBeInTheDocument();
    expect(writes).toHaveLength(1);
    expect(writes[0]).toHaveProperty('courseCodes', ['CS1001']);
  });

  it('does not overwrite unseen courses when course support returns during a legacy edit', async () => {
    const { client, server, writes } = renderRollback(
      '/profile?edit=details',
      true,
    );
    await settled(client);
    const user = setupUser();
    await user.clear(screen.getByLabelText('자기소개 (선택)'));
    await fill(
      user,
      screen.getByLabelText('자기소개 (선택)'),
      '지원 복구 전 초안',
    );
    server.legacy = false;
    await client.invalidateQueries({ queryKey: queryKeys.myProfile });
    await settled(client);
    await user.click(screen.getByRole('button', { name: '변경사항 저장' }));
    expect(
      screen.getByRole('button', { name: '변경사항 저장' }),
    ).toBeDisabled();
    expect(screen.getByLabelText('자기소개 (선택)')).toHaveValue(
      '지원 복구 전 초안',
    );
    expect(writes).toHaveLength(0);
    expect(myProfile().courses).toEqual([course]);
  });
});
