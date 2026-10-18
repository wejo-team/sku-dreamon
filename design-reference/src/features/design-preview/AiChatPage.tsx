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
import { Link, useSearchParams } from 'react-router';
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
import { Avatar } from './PreviewUi';
import { ContestCover } from './ContestCover';
import { contests, getPublicProfile, people, previewPath } from './data';
import { usePreview } from './preview-context';
import {
  createDemoReply,
  currentRecommendation,
  type ChatRecommendation,
  type ChatReply,
  type ChatSearchState,
} from './chat-demo';

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

export function AiChatProvider({ children }: { children: ReactNode }) {
  const { signedIn } = usePreview();
  return (
    <ChatSession key={signedIn ? 'signed-in' : 'guest'}>{children}</ChatSession>
  );
}

function ChatSession({ children }: { children: ReactNode }) {
  const { teams, signedIn, profile } = usePreview();
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState('');
  const [pending, setPending] = useState(false);
  const [failedRequest, setFailedRequest] = useState<string | null>(null);
  const [params] = useSearchParams();
  const failedOnce = useRef(false);
  const search = useRef<ChatSearchState | undefined>(undefined);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const nextId = useRef(0);
  useEffect(
    () => () => {
      if (timer.current !== null) clearTimeout(timer.current);
    },
    [],
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
    if (!text || text.length > 1000 || timer.current !== null) return;
    if (!retry) {
      const message: Message = { id: nextId.current++, role: 'user', text };
      setMessages((current) => [...current, message]);
    }
    setDraft('');
    setFailedRequest(null);
    setPending(true);
    const mine = signedIn ? getPublicProfile(profile) : null;
    const visiblePeople = signedIn ? (mine ? [...people, mine] : people) : [];
    // A short local delay makes the prototype's sending and stop states reviewable.
    timer.current = setTimeout(() => {
      timer.current = null;
      try {
        // Reproducible failure state for handoff review; this is not a service API.
        if (params.get('scenario') === 'error' && !failedOnce.current) {
          failedOnce.current = true;
          throw new Error('Reference response failure');
        }
        const reply = createDemoReply(text, search.current, {
          contests,
          teams,
          people: visiblePeople,
        });
        if (!signedIn && reply.search.kind === 'people') {
          reply.text =
            '사람 탐색은 로그인 후 이용할 수 있어요. 공개 공모전과 팀은 바로 찾아볼 수 있어요.';
          reply.recommendations = [];
        }
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
      value={{
        messages,
        draft,
        setDraft,
        pending,
        failedRequest,
        send,
        stop,
        clear,
      }}
    >
      {children}
    </ChatContext>
  );
}

function RecommendationCard({ item }: { item: ChatRecommendation }) {
  const { teams, signedIn, profile } = usePreview();
  const mine = signedIn ? getPublicProfile(profile) : null;
  const person =
    item.kind === 'person' && signedIn
      ? (mine ? [...people, mine] : people).find(
          (value) => value.id === item.id,
        )
      : undefined;
  const contest =
    item.kind === 'contest'
      ? contests.find((value) => value.id === item.id)
      : undefined;
  const team =
    item.kind === 'team'
      ? teams.find((value) => value.id === item.id)
      : undefined;
  const current = currentRecommendation(item, {
    contests,
    teams,
    people: signedIn ? (mine ? [...people, mine] : people) : [],
  });
  if (!current || (!person && !contest && !team))
    return (
      <p className="preview-muted">
        이 추천의 정보가 변경되었어요. 다시 요청해 주세요.
      </p>
    );
  const title = person?.name ?? contest?.title ?? team!.name;
  const metadata =
    person?.roles.join(' · ') ??
    (contest
      ? `${contest.category} · D−${contest.days}`
      : `${team!.roles.join(' · ')} 모집 · ${team!.members}/${team!.capacity}명 · ${team!.recruitmentDeadline} 마감`);
  const path = person ? 'people' : contest ? 'contests' : 'teams';
  return (
    <Link
      className="preview-card preview-ai-result"
      to={previewPath(
        `/${path}/${item.id}?from=${encodeURIComponent(previewPath('/ai'))}`,
      )}
    >
      <div className="preview-ai-result-heading">
        {person ? (
          <Avatar
            name={person.name}
            personId={person.id}
            avatarId={person.avatarId}
          />
        ) : contest ? (
          <ContestCover
            className="preview-ai-result-cover"
            src={contest.cover}
          />
        ) : (
          <span className="preview-ai-result-icon" aria-hidden="true">
            <Users size={20} />
          </span>
        )}
        <div>
          <h3>{title}</h3>
          <p>{metadata}</p>
        </div>
        <ChevronRight size={16} aria-hidden="true" />
      </div>
      <p className="preview-ai-result-reason">{current.reason}</p>
    </Link>
  );
}

function ReplyActions({ reply }: { reply: ChatReply }) {
  const { teams, signedIn, profile } = usePreview();
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle');
  useEffect(() => {
    if (status !== 'copied') return;
    const timer = setTimeout(() => setStatus('idle'), 2000);
    return () => clearTimeout(timer);
  }, [status]);
  const copy = async () => {
    const mine = signedIn ? getPublicProfile(profile) : null;
    const publicPeople = signedIn ? (mine ? [...people, mine] : people) : [];
    const items = reply.recommendations.flatMap((item) => {
      const current = currentRecommendation(item, {
        contests,
        teams,
        people: publicPeople,
      });
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

export function AiChatPage() {
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
  return (
    <section className="preview-ai" aria-label="AI 탐색 대화">
      <header className="preview-ai-toolbar">
        <h1>AI</h1>
        <Button
          variant="ghost"
          onClick={clear}
          disabled={!messages.length && !draft}
        >
          <SquarePen size={17} aria-hidden="true" />새 대화
        </Button>
      </header>
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
            maxLength={1000}
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
            <span>공모전 · 팀 · 사람 탐색</span>
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
                disabled={!draft.trim()}
              >
                <ArrowUp size={19} aria-hidden="true" />
              </InputGroupButton>
            )}
          </InputGroupAddon>
        </InputGroup>
      </form>
    </section>
  );
}
