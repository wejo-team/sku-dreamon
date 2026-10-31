import { act, fireEvent, screen, within } from '@testing-library/react';
import type { QueryClient } from '@tanstack/react-query';
import userEvent from '@testing-library/user-event';
import { Link, Route, Routes, useLocation } from 'react-router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AiChatPage } from '@/features/ai/AiChatPage';
import { LoginPage } from '@/features/account/AccountPages';
import { useApply } from '@/features/applications/queries';
import { useLogin, useLogout } from '@/features/auth/queries';
import { demoId, demoPassword } from '@/features/demo/auth-policy';
import { createDemoRecords, type DemoDatabase } from '@/features/demo/fixtures';
import { useSaveVisibility } from '@/features/profiles/queries';
import { demoIds, ME, myProfile, renderWithApi, settled } from '@/test/render';

// 이 파일은 명시적인 모의 대화 UI 회귀를 유지합니다. 실제 SSE는 별도 UI 테스트에서 검증합니다.
vi.mock('@/lib/clock', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/clock')>()),
  isMockApi: true,
}));

// 화면 밖 조작(로그인·로그아웃·지원·공개 전환)은 실제 API 함수로 목업 서버에 보냅니다.
function TestNavigation() {
  const login = useLogin();
  const logout = useLogout();
  const apply = useApply();
  const visibility = useSaveVisibility();
  const location = useLocation();
  const setPublic = (isPublic: boolean) =>
    visibility.mutate({ expectedVersion: myProfile().version, isPublic });
  return (
    <nav aria-label="테스트 탐색">
      <button
        onClick={() =>
          apply.mutate({
            teamId: demoIds.teams.greenwave,
            body: {
              requestId: crypto.randomUUID(),
              roleCode: 'development',
              message: null,
            },
          })
        }
      >
        추천 팀에 지원
      </button>
      <button onClick={() => setPublic(false)}>프로필 비공개</button>
      <button onClick={() => setPublic(true)}>프로필 공개</button>
      <button
        onClick={() =>
          login.mutate({ loginId: demoId, password: demoPassword })
        }
      >
        테스트 로그인
      </button>
      <span aria-label="현재 경로">
        {location.pathname}
        {location.search}
      </span>
      <Link to="/ai">대화로 돌아가기</Link>
      <Link to="/elsewhere">다른 화면 열기</Link>
      <button type="button" onClick={() => logout.mutate()}>
        로그아웃
      </button>
    </nav>
  );
}

// 팀은 그대로 두고 본인의 소속·지원·알림만 비운 목업 저장소.
// 본인이 팀장인 팀은 남은 첫 팀원이 팀장을 맡습니다.
function emptyWorkspace(records: DemoDatabase): DemoDatabase {
  const ended = '2026-10-18T08:00:00Z';
  const successor = new Map<string, string>();
  for (const team of records.teams) {
    if (team.ownerAccountId !== ME) continue;
    const next = records.memberships.find(
      (item) =>
        item.teamId === team.id && !item.endedAt && item.accountId !== ME,
    );
    if (next) successor.set(team.id, next.accountId);
  }
  return {
    ...records,
    teams: records.teams.map((team) =>
      successor.has(team.id)
        ? { ...team, ownerAccountId: successor.get(team.id)! }
        : team,
    ),
    memberships: records.memberships.map((item) =>
      item.accountId === ME && !item.endedAt
        ? { ...item, endedAt: ended }
        : successor.get(item.teamId) === item.accountId
          ? { ...item, membershipRole: 'leader' as const, roleCode: null }
          : item,
    ),
    applications: records.applications.filter(
      (item) => item.applicantAccountId !== ME,
    ),
    notifications: records.notifications.filter(
      (item) => item.recipientAccountId !== ME,
    ),
  };
}

let client: QueryClient;
// 진행 중인 목업 요청이 끝날 때까지 기다립니다.
const idle = () => settled(client);

async function renderChat(path = '/ai', signedIn = true, ownWorkspace = false) {
  const records = createDemoRecords();
  ({ client } = renderWithApi(
    <>
      <TestNavigation />
      <Routes>
        <Route path="/ai" element={<AiChatPage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/elsewhere" element={<p>다른 화면입니다.</p>} />
      </Routes>
    </>,
    {
      path,
      signedIn,
      db: signedIn && !ownWorkspace ? emptyWorkspace(records) : records,
    },
  ));
  await idle();
  return userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
}

async function finishReply() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1000);
  });
}

beforeEach(() => {
  // RTL drains a zero-delay task after userEvent; let that task settle in Vitest.
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  vi.clearAllTimers();
  vi.useRealTimers();
});

describe('design preview AI chat', () => {
  it('rejects blank messages and sends typed requests with Enter before showing recommendations', async () => {
    const user = await renderChat();
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    expect(
      screen.getByRole('button', { name: '메시지 보내기' }),
    ).toBeDisabled();
    await user.type(input, '   ');
    await user.keyboard('{Enter}');
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.clear(input);
    await user.type(input, '디자인 공모전 찾아줘');
    await user.keyboard('{Enter}');
    expect(input).toHaveValue('');
    expect(screen.getByRole('status')).toHaveTextContent('찾고 있어요');
    const log = screen.getByRole('log', { name: '대화 내용' });
    expect(within(log).getByText('디자인 공모전 찾아줘')).toBeInTheDocument();
    expect(within(log).queryByRole('link')).not.toBeInTheDocument();
    await finishReply();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(
      within(log).getByRole('link', {
        name: /우리 동네를 새롭게, 로컬 브랜딩/,
      }),
    ).toHaveAttribute('href', `/contests/${demoIds.contests.local}?from=%2Fai`);
  });

  it('preserves oversized pasted input, explains the limit and permits editing before sending', async () => {
    const user = await renderChat();
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    const oversized = '가'.repeat(1001);
    await user.click(input);
    await user.paste(oversized);
    expect(input).toHaveValue(oversized);
    expect(screen.getByRole('alert')).toHaveTextContent('메시지는 1,000자까지');
    expect(
      screen.getByRole('button', { name: '메시지 보내기' }),
    ).toBeDisabled();
    await user.keyboard('{Enter}');
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(input).toHaveValue(oversized);
    fireEvent.change(input, { target: { value: '공모전 찾아줘' } });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(input).toHaveValue('');
    await finishReply();
    expect(within(screen.getByRole('log')).getAllByRole('link')).toHaveLength(
      3,
    );
  });

  it('allows a private user to search while excluding owned teams and their private profile', async () => {
    const user = await renderChat('/ai', true, true);
    await user.click(screen.getByRole('button', { name: '프로필 비공개' }));
    await idle();
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    expect(
      within(screen.getByRole('log')).queryByRole('link', {
        name: /그린웨이브/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('log')).toHaveTextContent(
      '일치하는 모집 팀이 없어요',
    );
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    await user.type(input, '사람 전체 보기');
    await user.keyboard('{Enter}');
    await finishReply();
    expect(
      within(screen.getByRole('log')).queryByRole('link', { name: /김지우/ }),
    ).not.toBeInTheDocument();
    expect(
      within(screen.getByRole('log')).getByRole('link', { name: /정수아/ }),
    ).toBeInTheDocument();
  });

  it('uses a quick question to recommend matching teams and offers follow-up questions', async () => {
    const user = await renderChat();
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    expect(screen.getByRole('log')).toHaveTextContent(
      '개발자를 모집하는 팀 찾아줘',
    );
    await finishReply();
    const log = screen.getByRole('log');
    expect(
      within(log).getByRole('link', { name: /그린웨이브/ }),
    ).toHaveAttribute('href', `/teams/${demoIds.teams.greenwave}?from=%2Fai`);
    expect(
      within(log).queryByRole('link', { name: /캠퍼스 메이커스/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: '디자인 역할만' }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '디자인 역할만' }));
    await finishReply();
    expect(
      within(log).getByRole('link', { name: /캠퍼스 메이커스/ }),
    ).toBeInTheDocument();
  });

  it('keeps IME confirmation and Shift+Enter in the draft until an ordinary Enter submits', async () => {
    const user = await renderChat();
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    await user.click(input);
    fireEvent.compositionStart(input);
    fireEvent.change(input, { target: { value: '공모전 찾아줘' } });
    fireEvent.keyDown(input, {
      key: 'Enter',
      code: 'Enter',
      isComposing: true,
    });
    expect(input).toHaveValue('공모전 찾아줘');
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    fireEvent.compositionEnd(input);
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter', keyCode: 229 });
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    await user.keyboard('{End}');
    await user.keyboard('{Shift>}{Enter}{/Shift}');
    expect(input).toHaveValue('공모전 찾아줘\n');
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.keyboard('{Enter}');
    expect(screen.getByRole('log')).toHaveTextContent('공모전 찾아줘');
    expect(input).toHaveValue('');
    await finishReply();
    expect(within(screen.getByRole('log')).getAllByRole('link')).toHaveLength(
      3,
    );
  });

  it('stops a pending response without late recommendations and can send another request', async () => {
    const user = await renderChat();
    await user.click(screen.getByRole('button', { name: 'IT 공모전 찾아줘' }));
    await user.click(screen.getByRole('button', { name: '응답 중지' }));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(screen.getByRole('log')).toHaveTextContent('검색을 멈췄어요.');
    await finishReply();
    expect(
      within(screen.getByRole('log')).queryByRole('link'),
    ).not.toBeInTheDocument();
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '개발자를 모집하는 팀 찾아줘',
    );
    await user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    await finishReply();
    const links = within(screen.getByRole('log')).getAllByRole('link');
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveAccessibleName(/그린웨이브/);
  });

  it('starts a new conversation by clearing the draft and cancelling a pending response', async () => {
    const user = await renderChat();
    await user.click(screen.getByRole('button', { name: 'IT 공모전 찾아줘' }));
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    await user.type(input, '아직 보내지 않은 질문');
    await user.click(screen.getByRole('button', { name: '새 대화' }));
    expect(input).toHaveValue('');
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '응답 중지' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 대화' })).toBeDisabled();
    await finishReply();
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'IT 공모전 찾아줘' }),
    ).toBeInTheDocument();
  });

  it('retains the conversation and draft across screen navigation while a response completes', async () => {
    const user = await renderChat();
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '디자인 역할만',
    );
    await user.click(screen.getByRole('link', { name: '다른 화면 열기' }));
    expect(screen.getByText('다른 화면입니다.')).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    await finishReply();
    await user.click(screen.getByRole('link', { name: '대화로 돌아가기' }));
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue('디자인 역할만');
    const log = screen.getByRole('log');
    expect(
      within(log).getAllByText('개발자를 모집하는 팀 찾아줘'),
    ).toHaveLength(1);
    expect(
      within(log).getAllByRole('link', { name: /그린웨이브/ }),
    ).toHaveLength(1);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('clears account-specific conversation state and pending replies when signing out', async () => {
    const user = await renderChat();
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '이 계정의 미완성 질문',
    );
    await user.click(screen.getByRole('button', { name: '로그아웃' }));
    await idle();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: '로그인' })).toBeInTheDocument();
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    await finishReply();
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '테스트 로그인' }));
    await idle();
    expect(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue('');
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: '새 대화' })).toBeDisabled();
  });

  it('copies the answer and recommendation details and confirms success without changing the draft', async () => {
    const user = await renderChat();
    const writeText = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue(undefined);
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    const replyText = within(screen.getByRole('log')).getByText(
      /조건에 맞는 모집 팀 1개를 찾았어요\./,
    ).textContent;
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    await user.type(input, '아직 보내지 않은 질문');
    const copyButton = screen.getByRole('button', { name: '답변 복사' });
    await user.click(copyButton);
    expect(writeText).toHaveBeenCalledOnce();
    const copiedText = writeText.mock.calls[0]?.[0];
    expect(copiedText).toContain(replyText);
    expect(copiedText).toContain('그린웨이브');
    expect(copiedText).toContain('현재 개발 · 디자인 역할을 모집하고 있어요.');
    expect(copiedText).toContain('1/4명 · 2026-10-24 마감.');
    expect(copiedText).not.toContain('개발자를 모집하는 팀 찾아줘');
    expect(copiedText).not.toContain('아직 보내지 않은 질문');
    expect(await screen.findByRole('status')).toHaveTextContent(
      '답변을 복사했어요.',
    );
    expect(copyButton).toHaveTextContent('복사됨');
    expect(input).toHaveValue('아직 보내지 않은 질문');
  });

  it('removes an already-applied team from old cards and copied answers', async () => {
    const user = await renderChat();
    await user.click(screen.getByRole('button', { name: '프로필 공개' }));
    await idle();
    const writeText = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue(undefined);
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    expect(
      within(screen.getByRole('log')).getByRole('link', { name: /그린웨이브/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '추천 팀에 지원' }));
    await idle();
    expect(
      within(screen.getByRole('log')).queryByRole('link', {
        name: /그린웨이브/,
      }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('log')).toHaveTextContent(
      '이 추천의 정보가 변경되었어요',
    );
    await user.click(screen.getByRole('button', { name: '답변 복사' }));
    expect(writeText.mock.calls[0]?.[0]).not.toContain('그린웨이브');
    expect(writeText.mock.calls[0]?.[0]).not.toContain('현재 개발');
  });

  it('removes a newly private profile from old cards and copied answers', async () => {
    const user = await renderChat();
    await user.click(screen.getByRole('button', { name: '프로필 공개' }));
    await idle();
    const writeText = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockResolvedValue(undefined);
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '기획 역할 사람 찾아줘',
    );
    await user.keyboard('{Enter}');
    await finishReply();
    expect(
      within(screen.getByRole('log')).getByRole('link', { name: /김지우/ }),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '프로필 비공개' }));
    await idle();
    expect(
      within(screen.getByRole('log')).queryByRole('link', { name: /김지우/ }),
    ).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '답변 복사' }));
    expect(writeText.mock.calls[0]?.[0]).not.toContain('김지우');
    expect(writeText.mock.calls[0]?.[0]).not.toContain('공개한 관심 분야');
  });

  it('announces a clipboard failure and allows copying the same answer again', async () => {
    const user = await renderChat();
    const writeText = vi
      .spyOn(navigator.clipboard, 'writeText')
      .mockRejectedValueOnce(new Error('Clipboard access denied'))
      .mockResolvedValueOnce(undefined);
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    const copyButton = screen.getByRole('button', { name: '답변 복사' });
    await user.click(copyButton);
    expect(writeText).toHaveBeenCalledOnce();
    expect(await screen.findByRole('status')).toHaveTextContent(
      '복사하지 못했어요. 텍스트를 선택해 복사해 주세요.',
    );
    expect(copyButton).not.toHaveTextContent('복사됨');
    expect(
      within(screen.getByRole('log')).getByRole('link', { name: /그린웨이브/ }),
    ).toBeInTheDocument();
    await user.click(copyButton);
    expect(writeText).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('답변을 복사했어요.')).toHaveAttribute(
      'role',
      'status',
    );
    expect(copyButton).toHaveTextContent('복사됨');
    expect(screen.queryByText(/복사하지 못했어요/)).not.toBeInTheDocument();
  });

  it('requires login before mounting chat and returns to the original AI URL after login', async () => {
    const path = '/ai?scenario=error';
    const user = await renderChat(path, false);
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.queryByRole('log')).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'IT 공모전 찾아줘' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: '답변 복사' }),
    ).not.toBeInTheDocument();
    const login = screen.getByRole('link', { name: '로그인' });
    expect(login).toHaveAttribute(
      'href',
      `/login?returnTo=${encodeURIComponent(path)}`,
    );
    await user.click(login);
    await user.type(screen.getByLabelText('아이디'), 'dreamondemo');
    await user.type(screen.getByLabelText('비밀번호'), 'DreamonReview2026!');
    await user.click(screen.getByRole('button', { name: '로그인' }));
    expect(
      await screen.findByRole('textbox', { name: 'AI에게 보낼 메시지' }),
    ).toHaveValue('');
    expect(screen.getByLabelText('현재 경로')).toHaveTextContent(path);
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '답변을 준비하지 못했어요. 다시 시도해 주세요.',
    );
  });

  it('recommends visible people for a signed-in user', async () => {
    const user = await renderChat();
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      '디자인 역할 사람 찾아줘',
    );
    await user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    await finishReply();
    expect(
      within(screen.getByRole('log')).getByRole('link', { name: /정수아/ }),
    ).toHaveAttribute('href', `/people/${demoIds.accounts.sua}?from=%2Fai`);
  });

  it('retains an unsent oversized draft when retrying a previously failed request', async () => {
    const user = await renderChat('/ai?scenario=error');
    await user.click(screen.getByRole('button', { name: 'IT 공모전 찾아줘' }));
    await finishReply();
    const input = screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' });
    const draft = '가'.repeat(1001);
    fireEvent.change(input, { target: { value: draft } });
    await user.click(screen.getByRole('button', { name: '다시 시도' }));
    await finishReply();
    expect(input).toHaveValue(draft);
    expect(screen.getByRole('alert')).toHaveTextContent('메시지는 1,000자까지');
    expect(
      within(screen.getByRole('log')).getAllByText('IT 공모전 찾아줘'),
    ).toHaveLength(1);
    expect(within(screen.getByRole('log')).getAllByRole('link')).toHaveLength(
      3,
    );
  });

  it('retries a failed reply without duplicating the user message and replaces the error with results', async () => {
    const user = await renderChat('/ai?scenario=error');
    await user.click(
      screen.getByRole('button', { name: '개발자를 모집하는 팀 찾아줘' }),
    );
    await finishReply();
    expect(screen.getByRole('alert')).toHaveTextContent(
      '답변을 준비하지 못했어요. 다시 시도해 주세요.',
    );
    const log = screen.getByRole('log');
    expect(within(log).queryByRole('link')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: '다시 시도' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('찾고 있어요');
    await finishReply();
    expect(
      within(log).getAllByText('개발자를 모집하는 팀 찾아줘'),
    ).toHaveLength(1);
    expect(
      within(log).getByRole('link', { name: /그린웨이브/ }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
});

it.each([
  ['디자인 공모전 찾아줘', '시연 공고'],
  ['개발자를 모집하는 팀 찾아줘', '시연 팀'],
  ['디자인 역할 사람 찾아줘', '시연 계정'],
])(
  'labels API demo resources in existing recommendation cards: %s',
  async (message, label) => {
    const user = await renderChat();
    await user.type(
      screen.getByRole('textbox', { name: 'AI에게 보낼 메시지' }),
      message,
    );
    await user.click(screen.getByRole('button', { name: '메시지 보내기' }));
    await finishReply();
    const cards = within(screen.getByRole('log')).getAllByRole('link');
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      expect(within(card).getByText(label)).toBeInTheDocument();
      expect(card).toHaveAccessibleName(new RegExp(label));
    }
  },
);
