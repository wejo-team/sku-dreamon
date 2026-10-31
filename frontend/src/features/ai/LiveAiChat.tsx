// docs/specs/matching.md AC16/21~26/28/33~35: 실제 스트림·현재 권한·탭 메모리 대화.
import { useLayoutEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router';
import {
  ArrowDown,
  ArrowUp,
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
import { Button } from '@/components/ui/button';
import { Bubble, BubbleContent } from '@/components/ui/bubble';
import {
  Message,
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
import { DemoBadge } from '@/components/common/CommonUi';
import { useLabels } from '@/features/catalogs/queries';
import { profileTextLength } from '@/features/demo/profile-fields';
import type { ResourceCard, RichResourceCard } from './contract';
import { AiResultCards } from './AiResultCards';
import { chatClipboardText } from './clipboard';
import {
  LiveChatContext,
  useLiveChat,
  useLiveChatController,
  type LiveChatTurn,
} from './live-chat';

export function LiveAiChatProvider({ children }: { children: ReactNode }) {
  const controller = useLiveChatController();
  return <LiveChatContext value={controller}>{children}</LiveChatContext>;
}

function LiveCard({ card }: { card: ResourceCard }) {
  const { fieldLabel, roleLabel } = useLabels();
  const path =
    card.kind === 'contest'
      ? 'contests'
      : card.kind === 'team'
        ? 'teams'
        : 'people';
  const labels = [
    ...card.fieldCodes.map(fieldLabel),
    ...card.roleCodes.map(roleLabel),
  ];
  return (
    <Link
      className="preview-card preview-ai-result"
      to={`/${path}/${card.resourceId}?from=%2Fai`}
    >
      <div className="preview-ai-result-heading">
        <span className="preview-ai-result-icon" aria-hidden="true">
          {card.kind === 'contest' ? (
            <CalendarDays size={20} />
          ) : (
            <Users size={20} />
          )}
        </span>
        <div className="min-w-0 break-words">
          <div className="preview-row">
            <h3>{card.title}</h3>
            <DemoBadge
              isDemo={card.isDemo}
              kind={card.kind === 'person' ? 'account' : card.kind}
            />
          </div>
          {!!labels.length && <p>{labels.join(' · ')}</p>}
        </div>
        <ChevronRight size={16} aria-hidden="true" />
      </div>
      <p className="preview-ai-result-reason break-words">{card.reason}</p>
    </Link>
  );
}

function LiveReplyActions({ turn }: { turn: LiveChatTurn }) {
  const { controller } = useLiveChat();
  const labels = useLabels();
  const [copying, setCopying] = useState(false);
  const [status, setStatus] = useState<'idle' | 'copied' | 'error'>('idle');
  const copy = async () => {
    setCopying(true);
    setStatus('idle');
    try {
      if (
        await controller.copy(turn.input.requestId, (result) =>
          chatClipboardText(result, labels),
        )
      )
        setStatus('copied');
    } catch {
      setStatus('error');
    } finally {
      setCopying(false);
    }
  };
  return (
    <MessageFooter className="preview-ai-actions">
      <Button
        variant="ghost"
        onClick={() => void copy()}
        aria-label="답변 복사"
        disabled={copying || !turn.result}
      >
        {status === 'copied' ? (
          <Check size={15} aria-hidden="true" />
        ) : (
          <Copy size={15} aria-hidden="true" />
        )}
        <span>
          {copying ? '확인 중' : status === 'copied' ? '복사됨' : '복사'}
        </span>
      </Button>
      {status !== 'idle' && (
        <span
          role="status"
          className={status === 'copied' ? 'sr-only' : 'preview-ai-copy-error'}
        >
          {status === 'copied'
            ? '답변을 복사했어요.'
            : '복사하지 못했어요. 다시 시도해 주세요.'}
        </span>
      )}
    </MessageFooter>
  );
}

const starters = [
  {
    text: 'IT 공모전 찾아줘',
    label: 'IT 공모전',
    icon: CalendarDays,
  },
  { text: '개발자를 모집하는 팀 찾아줘', label: '개발자 모집 팀', icon: Users },
  {
    text: '디자인에 관심 있는 사람 찾아줘',
    label: '디자인 관심 사람',
    icon: Palette,
  },
];

export function LiveAiConversation() {
  const { controller, state } = useLiveChat();
  const { turns, draft, activeId, notice } = state;
  const pending = activeId !== null;
  const length = profileTextLength(draft);
  const tooLong = length > 1000;
  useLayoutEffect(() => {
    controller.setVisible(true);
    return () => controller.setVisible(false);
  }, [controller]);
  return (
    <section className="preview-ai" aria-label="AI 탐색 대화">
      <h1 className="sr-only">AI</h1>
      <MessageScrollerProvider
        key={state.conversationId}
        autoScroll
        defaultScrollPosition={turns.length ? 'last-anchor' : 'start'}
        scrollMargin={20}
      >
        <MessageScroller className="preview-ai-conversation">
          <MessageScrollerViewport
            className="preview-ai-scroll"
            aria-label="AI 대화 스크롤 영역"
          >
            {!turns.length ? (
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
                      onClick={() => controller.send(text)}
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
                aria-relevant="additions text"
              >
                {turns.map((turn) => (
                  <MessageScrollerItem
                    key={turn.input.clientMessageId}
                    messageId={turn.input.clientMessageId}
                    scrollAnchor
                  >
                    <Message align="end">
                      <MessageContent>
                        <Bubble
                          align="end"
                          variant="muted"
                          className="preview-ai-user-message"
                        >
                          <BubbleContent>
                            <span className="sr-only">나: </span>
                            <p>{turn.input.content}</p>
                          </BubbleContent>
                        </Bubble>
                      </MessageContent>
                    </Message>
                    <Message className="preview-ai-assistant-message mt-6">
                      <MessageContent>
                        <MessageHeader className="preview-ai-speaker">
                          <MessageCircle size={16} aria-hidden="true" />
                          <span>드림온 AI</span>
                        </MessageHeader>
                        {turn.status === 'pending' && (
                          <>
                            {!!turn.partial && (
                              <p className="preview-ai-response break-words">
                                {turn.partial}
                              </p>
                            )}
                            <div role="status" className="preview-ai-pending">
                              <span
                                className="preview-ai-pending-dot"
                                aria-hidden="true"
                              />
                              {turn.phase}
                            </div>
                          </>
                        )}
                        {turn.status === 'checking' && (
                          <p role="status" className="preview-muted">
                            현재 정보를 확인하고 있어요…
                          </p>
                        )}
                        {turn.result && (
                          <>
                            <p className="preview-ai-response break-words">
                              {turn.result.answer}
                            </p>
                            {turn.status === 'empty' && (
                              <p className="preview-muted">
                                조건에 맞는 결과가 없어요. 조건을 바꾸어 다시
                                요청할 수 있어요.
                              </p>
                            )}
                            {!!turn.result.cards.length &&
                              (turn.result.cards.every(
                                (card): card is RichResourceCard =>
                                  'details' in card,
                              ) ? (
                                <AiResultCards cards={turn.result.cards} />
                              ) : (
                                <div className="preview-ai-results">
                                  {turn.result.cards.map((card) => (
                                    <LiveCard
                                      key={`${card.kind}-${card.resourceId}`}
                                      card={card}
                                    />
                                  ))}
                                </div>
                              ))}
                            {turn.result.referencesChanged && (
                              <p className="preview-muted">
                                이전 근거가 바뀌어 현재 정보를 다시 확인했어요.
                              </p>
                            )}
                          </>
                        )}
                        {turn.original && <LiveReplyActions turn={turn} />}
                        {turn.error && (
                          <Alert
                            role={
                              turn.status === 'canceled' ? 'status' : 'alert'
                            }
                            className="preview-ai-error"
                          >
                            <AlertDescription>{turn.error}</AlertDescription>
                            {turn.status === 'validation_failed' ? (
                              <Button
                                variant="outline"
                                onClick={() =>
                                  void controller.validate(turn.input.requestId)
                                }
                              >
                                <RotateCcw size={16} aria-hidden="true" />
                                다시 확인
                              </Button>
                            ) : (
                              turn.recovery && (
                                <Button
                                  variant="outline"
                                  disabled={pending}
                                  onClick={() =>
                                    controller.retry(turn.input.requestId)
                                  }
                                >
                                  <RotateCcw size={16} aria-hidden="true" />
                                  {turn.recovery === 'retry'
                                    ? '다시 시도'
                                    : turn.recovery === 'status'
                                      ? '상태 확인'
                                      : '같은 내용으로 다시 요청'}
                                </Button>
                              )
                            )}
                          </Alert>
                        )}
                      </MessageContent>
                    </Message>
                  </MessageScrollerItem>
                ))}
              </MessageScrollerContent>
            )}
          </MessageScrollerViewport>
          {!!turns.length && (
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
          controller.send(draft);
        }}
      >
        <InputGroup className="preview-ai-prompt" aria-label="메시지 작성">
          <InputGroupTextarea
            aria-label="AI에게 보낼 메시지"
            placeholder="어떤 도전을 찾고 있나요?"
            rows={1}
            aria-invalid={tooLong || undefined}
            aria-describedby={
              tooLong ? 'chat-length-error' : notice ? 'chat-notice' : undefined
            }
            value={draft}
            onChange={(event) => controller.setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (
                event.key === 'Enter' &&
                !event.shiftKey &&
                !event.nativeEvent.isComposing &&
                event.nativeEvent.keyCode !== 229
              ) {
                event.preventDefault();
                controller.send(draft);
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
              onClick={controller.clear}
              disabled={!turns.length && !draft}
            >
              <SquarePen size={20} aria-hidden="true" />
            </InputGroupButton>
            {pending ? (
              <InputGroupButton
                type="button"
                variant="outline"
                size="icon-sm"
                aria-label="응답 중지"
                onClick={controller.stop}
                disabled={turns.some(
                  (turn) =>
                    turn.input.requestId === activeId &&
                    turn.status === 'canceled',
                )}
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
            메시지는 1,000자까지 보낼 수 있어요. 현재 {length.toLocaleString()}
            자이며, 입력한 내용은 그대로 보관돼요.
          </p>
        )}
        {notice && (
          <p
            id="chat-notice"
            role="alert"
            className="px-2 pt-2 text-sm text-destructive"
          >
            {notice}
          </p>
        )}
      </form>
    </section>
  );
}
