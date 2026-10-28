/**
 * [참조 출처]
 * 1. design-reference/src/features/design-preview/AiChatPage.tsx - AI 대화 원본
 * 2. docs/specs/matching.md#acceptance-criteria - 로그인 후 메시지 1,000자, 답변 카드 최대 3개, 중단·실패·재시도·빈 결과
 * 3. docs/design/tokens.md - 새 대화는 입력창 왼쪽 type="button" 도구 아이콘
 * 4. docs/design/screens.md - 「확인할 상태와 연결」 AI → 추천 카드 → 상세, 로그아웃 시 대화 제거
 * 5. docs/design/assets/ai-390.png, ai-welcome-390.png, ai-login-390.png, ai-overflow-320.png, people-ai-390.png - 실제 화면
 *
 * 7. docs/api/ai.md - 실제 모드는 LiveAiChat의 SSE·결과 재검증 경로를 사용합니다.
 *    로컬 응답은 명시적인 모의 모드에서만 사용합니다.
 */

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import {
  ArrowUp,
  ArrowDown,
  CalendarDays,
  Check,
  ChevronRight,
  Copy,
  MessageCircle,
  Palette,
  RotateCcw,
  Square,
  SquarePen,
  Users,
} from 'lucide-react';
import { Link, useLocation, useSearchParams } from 'react-router';
import { Button } from '@/components/ui/button';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import {
  Message as MessageRow,
  MessageContent,
  MessageHeader,
  MessageFooter,
} from '@/components/ui/message';
import {
  InputGroup,
  InputGroupAddon,
  InputGroupButton,
  InputGroupTextarea,
} from '@/components/ui/input-group';
import {
  MessageScrollerProvider,
  MessageScroller,
  MessageScrollerViewport,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerButton,
} from '@/components/ui/message-scroller';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Avatar, DemoBadge } from '@/components/common/CommonUi';
import { LoginGate } from '@/features/account/AccountPages';
import { ContestCover } from '@/components/common/ContestCover';
import { useQuery } from '@tanstack/react-query';
import { useSession } from '@/features/auth/queries';
import { useLabels } from '@/features/catalogs/queries';
import { contestsQueryOptions } from '@/features/contests/queries';
import { peopleQueryOptions } from '@/features/profiles/queries';
import {
  myTeamsQueryOptions,
  teamsQueryOptions,
} from '@/features/teams/queries';
import { myApplicationsQueryOptions } from '@/features/applications/queries';
import { summaryBadgeLabel } from '@/features/demo/contest-state';
import { isMockApi } from '@/lib/clock';
import { LiveAiChatProvider, LiveAiConversation } from './LiveAiChat';

// [출처 2, 4, 7] 추천 대상: 공모전, 팀, 로그인 후 현재 공개된 프로필. 본인 소속·지원 팀은 신규 지원 대상에서 제외
function useSearchData(enabled = true): SearchData {
  const { account, signedIn: session } = useSession();
  const signedIn = session && enabled;
  const { fieldLabel, roleLabel } = useLabels();
  const all = { pageSize: 100 };
  const contests =
    useQuery({ ...contestsQueryOptions(all), enabled }).data?.data ?? [];
  const teams =
    useQuery({ ...teamsQueryOptions(all), enabled }).data?.data ?? [];
  const people =
    useQuery({ ...peopleQueryOptions(all), enabled: signedIn }).data?.data ??
    [];
  const applications =
    useQuery({ ...myApplicationsQueryOptions(), enabled: signedIn }).data
      ?.data ?? [];
  const myTeams =
    useQuery({ ...myTeamsQueryOptions(), enabled: signedIn }).data?.data ?? [];
  return {
    contests,
    teams,
    people: signedIn ? people : [],
    labels: { fieldLabel, roleLabel },
    applications: applications.map((item) => item.application),
    accountId: account?.id,
    memberTeamIds: myTeams.map((item) => item.team.id),
  };
}
import { profileTextLength } from '@/features/demo/profile-fields';
import {
  createDemoReply,
  currentRecommendation,
  type ChatRecommendation,
  type ChatReply,
  type ChatSearchState,
  type SearchData,
} from '@/features/ai/chat-demo';

type Message =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; reply: ChatReply };
type ChatState = {
  messages: Message[];
  draft: string;
  setDraft: (value: string) => void;
  pending: boolean;
  failedRequest: string | null;
  send: (text: string, retry?: boolean) => void;
  stop: () => void;
  clear: () => void;
};
const ChatContext = createContext<ChatState | null>(null);

// [출처 4] 현재 세션의 대화·초안 보관
// 계정이 바뀌면 대화만 비우고 화면은 다시 마운트하지 않습니다(가입 직후 자동 로그인에서 완료 화면 유지).
export function AiChatProvider({ children }: { children: ReactNode }) {
  if (!isMockApi) return <LiveAiChatProvider>{children}</LiveAiChatProvider>;
  return <DemoAiChatProvider>{children}</DemoAiChatProvider>;
}

function DemoAiChatProvider({ children }: { children: ReactNode }) {
  const { account } = useSession();
  return <ChatSession owner={account?.id ?? null}>{children}</ChatSession>;
}

function ChatSession({
  owner,
  children,
}: {
  owner: string | null;
  children: ReactNode;
}) {
  const data = useSearchData(owner !== null);
  const latestData = useRef(data);
  useEffect(() => {
    latestData.current = data;
  }, [data]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [failedRequest, setFailedRequest] = useState<string | null>(null);
  const [params] = useSearchParams();
  const failedOnce = useRef(false);
  const search = useRef<ChatSearchState | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(0);
  const [sessionOwner, setSessionOwner] = useState(owner);
  if (sessionOwner !== owner) {
    setSessionOwner(owner);
    setMessages([]);
    setDraft('');
    setFailedRequest(null);
    setPending(false);
  }
  // 세션이 바뀌거나 화면을 떠나면 진행 중인 데모 응답과 검색 맥락을 버립니다.
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
      search.current = undefined;
    },
    [owner],
  );

  const stop = () => {
    if (timer.current === null) return;
    clearTimeout(timer.current);
    timer.current = null;
    setPending(false);
    const message: Message = {
      id: nextId.current++,
      role: 'assistant',
      reply: {
        text: '검색을 멈췄어요. 조건을 바꾸어 다시 요청할 수 있어요.',
        recommendations: [],
        suggestions: [],
        search: search.current ?? { kind: 'contests' },
      },
    };
    setMessages((current) => [...current, message]);
  };
  const send = (input: string, retry = false) => {
    const text = input.trim();
    if (!text || profileTextLength(text) > 1000 || timer.current !== null)
      return;
    if (!retry) {
      const message: Message = { id: nextId.current++, role: 'user', text };
      setMessages((current) => [...current, message]);
    }
    if (!retry) setDraft('');
    setFailedRequest(null);
    setPending(true);
    // A short local delay makes the prototype's sending and stop states reviewable.
    timer.current = setTimeout(() => {
      timer.current = null;
      try {
        // Reproducible failure state for handoff review; this is not a service API.
        if (params.get('scenario') === 'error' && !failedOnce.current) {
          failedOnce.current = true;
          throw new Error('Reference response failure');
        }
        const reply = createDemoReply(text, search.current, latestData.current);
        search.current = reply.search;
        const message: Message = {
          id: nextId.current++,
          role: 'assistant',
          reply,
        };
        setMessages((current) => [...current, message]);
      } catch {
        setFailedRequest(text);
      }
      setPending(false);
    }, 450);
  };
  const clear = () => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = null;
    search.current = undefined;
    setMessages([]);
    setDraft('');
    setFailedRequest(null);
    setPending(false);
  };
  return (
    <ChatContext
      value={
        owner === null
          ? null
          : {
              messages,
              draft,
              setDraft,
              pending,
              failedRequest,
              send,
              stop,
              clear,
            }
      }
    >
      {children}
    </ChatContext>
  );
}

function RecommendationCard({ item }: { item: ChatRecommendation }) {
  const { signedIn } = useSession();
  const data = useSearchData();
  const { fieldLabel, roleLabel } = data.labels;
  const { teams } = data;
  const person =
    item.kind === 'person' && signedIn
      ? data.people.find((value) => value.accountId === item.id)
      : undefined;
  const contest =
    item.kind === 'contest'
      ? data.contests.find((value) => value.id === item.id)
      : undefined;
  const team =
    item.kind === 'team'
      ? teams.find((value) => value.id === item.id)
      : undefined;
  const current = currentRecommendation(item, data);
  if (!current || (!person && !contest && !team))
    return (
      <p className="preview-muted">
        이 추천의 정보가 변경되었어요. 다시 요청해 주세요.
      </p>
    );
  const title = person?.realName ?? contest?.title ?? team!.name;
  const metadata = person
    ? person.roleCodes.map(roleLabel).join(' · ')
    : contest
      ? `${contest.fieldCodes.map(fieldLabel).join(' · ')} · ${summaryBadgeLabel(contest)}`
      : `${team!.roleCodes.map(roleLabel).join(' · ')} 모집 · ${team!.memberCount}/${team!.capacity}명 · ${team!.recruitmentDeadline.sourceDate} 마감`;
  const path = person ? 'people' : contest ? 'contests' : 'teams';
  return (
    <Link
      className="preview-card preview-ai-result"
      to={`/${path}/${item.id}?from=${encodeURIComponent('/ai')}`}
    >
      <div className="preview-ai-result-heading">
        {person ? (
          <Avatar name={person.realName} imageCode={person.profileImageCode} />
        ) : contest ? (
          <ContestCover
            className="preview-ai-result-cover"
            src={contest.posterUrl ?? undefined}
          />
        ) : (
          <span className="preview-ai-result-icon" aria-hidden="true">
            <Users size={20} />
          </span>
        )}
        <div>
          <div className="preview-row">
            <h3>{title}</h3>
            <DemoBadge
              isDemo={(person ?? contest ?? team!).isDemo}
              kind={person ? 'account' : contest ? 'contest' : 'team'}
            />
          </div>
          <p>{metadata}</p>
        </div>
        <ChevronRight size={16} aria-hidden="true" />
      </div>
      <p className="preview-ai-result-reason">{current.reason}</p>
    </Link>
  );
}

function ReplyActions({ reply }: { reply: ChatReply }) {
  const data = useSearchData();
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle');
  useEffect(() => {
    if (status !== 'copied') return;
    const timer = setTimeout(() => setStatus('idle'), 2000);
    return () => clearTimeout(timer);
  }, [status]);
  const copy = async () => {
    const items = reply.recommendations.flatMap((item) => {
      const current = currentRecommendation(item, data);
      return current ? [`${current.title}\n${current.reason}`] : [];
    });
    try {
      await navigator.clipboard.writeText([reply.text, ...items].join('\n\n'));
      setStatus('copied');
    } catch {
      setStatus('error');
    }
  };
  return (
    <MessageFooter className="preview-ai-actions">
      <Button variant="ghost" onClick={copy} aria-label="답변 복사">
        {status === 'copied' ? (
          <Check size={15} aria-hidden="true" />
        ) : (
          <Copy size={15} aria-hidden="true" />
        )}
        <span>{status === 'copied' ? '복사됨' : '복사'}</span>
      </Button>
      {status !== 'idle' && (
        <span
          role="status"
          className={status === 'copied' ? 'sr-only' : 'preview-ai-copy-error'}
        >
          {status === 'copied'
            ? '답변을 복사했어요.'
            : '복사하지 못했어요. 텍스트를 선택해 복사해 주세요.'}
        </span>
      )}
    </MessageFooter>
  );
}

const starters = [
  {
    text: '마감이 가까운 공모전 찾아줘',
    label: '마감 임박 공모전',
    icon: CalendarDays,
  },
  { text: '개발자를 모집하는 팀 찾아줘', label: '개발자 모집 팀', icon: Users },
  {
    text: '디자인에 관심 있는 사람 찾아줘',
    label: '디자인 관심 사람',
    icon: Palette,
  },
];

// [출처 2, 3, 4, 5] 로그인 전용 대화·추천 카드
export function AiChatPage() {
  const { signedIn } = useSession();
  const location = useLocation();
  if (!signedIn) {
    return (
      <LoginGate
        title="AI"
        rootPage
        returnTo={`${location.pathname}${location.search}${location.hash}`}
      />
    );
  }
  return isMockApi ? <AiConversation /> : <LiveAiConversation />;
}

function AiConversation() {
  const chat = useContext(ChatContext);
  if (!chat) throw new Error('AiChatProvider가 필요합니다.');
  const {
    messages,
    draft,
    setDraft,
    pending,
    failedRequest,
    send,
    stop,
    clear,
  } = chat;
  const last = messages.at(-1);
  const draftLength = profileTextLength(draft);
  const tooLong = draftLength > 1000;
  return (
    <section className="preview-ai" aria-label="AI 탐색 대화">
      <h1 className="sr-only">AI</h1>
      <p className="px-4 pt-2 text-xs text-muted-foreground">
        모의 응답 모드 · 실제 AI를 호출하지 않습니다.
      </p>
      <MessageScrollerProvider
        key={messages[0]?.id ?? 'empty'}
        // Replies arrive at once in this prototype; keep the question in view.
        autoScroll={false}
        defaultScrollPosition={messages.length ? 'last-anchor' : 'start'}
        scrollMargin={20}
      >
        <MessageScroller className="preview-ai-conversation">
          <MessageScrollerViewport
            className="preview-ai-scroll"
            aria-label="AI 대화 스크롤 영역"
          >
            {!messages.length ? (
              <div className="preview-ai-welcome">
                <span className="preview-ai-mark" aria-hidden="true">
                  <MessageCircle size={26} strokeWidth={1.6} />
                </span>
                <h2>어떤 도전을 찾고 있나요?</h2>
                <p>
                  관심 분야나 맡고 싶은 역할을 알려주세요.
                  <br />
                  공모전부터 함께할 사람까지 찾아볼게요.
                </p>
                <div className="preview-ai-starters" aria-label="추천 질문">
                  {starters.map(({ text, label, icon: Icon }) => (
                    <Button
                      key={text}
                      variant="outline"
                      aria-label={text}
                      onClick={() => send(text)}
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span>{label}</span>
                    </Button>
                  ))}
                </div>
              </div>
            ) : (
              <MessageScrollerContent
                className="preview-ai-messages"
                aria-label="대화 내용"
                aria-live="polite"
                aria-relevant="additions"
              >
                {messages.map((message) => (
                  <MessageScrollerItem
                    key={message.id}
                    messageId={String(message.id)}
                    scrollAnchor={message.role === 'user'}
                  >
                    {message.role === 'user' ? (
                      <MessageRow align="end">
                        <MessageContent>
                          <Bubble
                            align="end"
                            variant="muted"
                            className="preview-ai-user-message"
                          >
                            <BubbleContent>
                              <span className="sr-only">나: </span>
                              <p>{message.text}</p>
                            </BubbleContent>
                          </Bubble>
                        </MessageContent>
                      </MessageRow>
                    ) : (
                      <MessageRow className="preview-ai-assistant-message">
                        <MessageContent>
                          <MessageHeader className="preview-ai-speaker">
                            <MessageCircle size={16} aria-hidden="true" />
                            <span>드림온 AI</span>
                          </MessageHeader>
                          <p className="preview-ai-response">
                            {message.reply.text}
                          </p>
                          {!!message.reply.recommendations.length && (
                            <div className="preview-ai-results">
                              {message.reply.recommendations.map((item) => (
                                <RecommendationCard
                                  key={`${item.kind}-${item.id}`}
                                  item={item}
                                />
                              ))}
                            </div>
                          )}
                          <ReplyActions reply={message.reply} />
                          {!pending &&
                            !failedRequest &&
                            message === last &&
                            !!message.reply.suggestions.length && (
                              <div
                                className="preview-ai-followups"
                                aria-label="이어 물어보기"
                              >
                                {message.reply.suggestions.map((text) => (
                                  <Button
                                    key={text}
                                    variant="outline"
                                    onClick={() => send(text)}
                                  >
                                    {text}
                                    <ChevronRight
                                      size={14}
                                      aria-hidden="true"
                                    />
                                  </Button>
                                ))}
                              </div>
                            )}
                        </MessageContent>
                      </MessageRow>
                    )}
                  </MessageScrollerItem>
                ))}
                {pending && (
                  <MessageScrollerItem messageId="pending">
                    <div role="status" className="preview-ai-pending">
                      <span
                        className="preview-ai-pending-dot"
                        aria-hidden="true"
                      />
                      조건에 맞는 항목을 찾고 있어요…
                    </div>
                  </MessageScrollerItem>
                )}
                {failedRequest && (
                  <MessageScrollerItem messageId="error">
                    <Alert role="alert" className="preview-ai-error">
                      <AlertDescription>
                        답변을 준비하지 못했어요. 다시 시도해 주세요.
                      </AlertDescription>
                      <Button
                        variant="outline"
                        onClick={() => send(failedRequest, true)}
                      >
                        <RotateCcw size={16} aria-hidden="true" />
                        다시 시도
                      </Button>
                    </Alert>
                  </MessageScrollerItem>
                )}
              </MessageScrollerContent>
            )}
          </MessageScrollerViewport>
          {!!messages.length && (
            <MessageScrollerButton
              className="preview-ai-scroll-button"
              aria-label="최신 답변으로 이동"
              behavior="instant"
            >
              <ArrowDown size={18} aria-hidden="true" />
            </MessageScrollerButton>
          )}
        </MessageScroller>
      </MessageScrollerProvider>
      <form
        className="preview-ai-composer"
        onSubmit={(event) => {
          event.preventDefault();
          send(draft);
        }}
      >
        <InputGroup className="preview-ai-prompt" aria-label="메시지 작성">
          <InputGroupTextarea
            aria-label="AI에게 보낼 메시지"
            placeholder="어떤 도전을 찾고 있나요?"
            rows={1}
            aria-invalid={tooLong || undefined}
            aria-describedby={tooLong ? 'chat-length-error' : undefined}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing &&
                event.nativeEvent.keyCode !== 229
              ) {
                event.preventDefault();
                send(draft);
              }
            }}
          />
          <InputGroupAddon
            align="block-end"
            className="preview-ai-prompt-toolbar"
          >
            <InputGroupButton
              type="button"
              variant="ghost"
              size="icon-sm"
              aria-label="새 대화"
              title="새 대화"
              onClick={clear}
              disabled={!messages.length && !draft}
            >
              <SquarePen size={20} aria-hidden="true" />
            </InputGroupButton>
            {pending ? (
              <InputGroupButton
                type="button"
                variant="outline"
                size="icon-sm"
                aria-label="응답 중지"
                onClick={stop}
              >
                <Square size={16} aria-hidden="true" />
              </InputGroupButton>
            ) : (
              <InputGroupButton
                type="submit"
                variant="default"
                size="icon-sm"
                aria-label="메시지 보내기"
                disabled={!draft.trim() || tooLong}
              >
                <ArrowUp size={19} aria-hidden="true" />
              </InputGroupButton>
            )}
          </InputGroupAddon>
        </InputGroup>
        {tooLong && (
          <p
            id="chat-length-error"
            role="alert"
            className="px-2 pt-2 text-sm text-destructive"
          >
            메시지는 1,000자까지 보낼 수 있어요. 현재{' '}
            {draftLength.toLocaleString()}자이며, 입력한 내용은 그대로 보관돼요.
          </p>
        )}
      </form>
    </section>
  );
}
