// 현재 탭의 대화만 보관합니다. 서버 기록 조회·브라우저 영속 저장소는 사용하지 않습니다.
// docs/api/ai.md: 원입력 재시도, done 경계, 최초 result를 이용한 현재 권한 재검증.
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useSyncExternalStore,
} from 'react';
import { useQueryClient, type QueryClient } from '@tanstack/react-query';
import { ApiError } from '@/lib/api';
import { queryKeys, sessionGeneration } from '@/lib/query-keys';
import {
  startChat,
  retryAi,
  getAiRequest,
  cancelAi,
  validateAiResult,
} from './api';
import {
  ChatStart,
  type AiEvent,
  type AiRequestView,
  type ChatResult,
} from './contract';

type TurnStatus =
  | 'pending'
  | 'succeeded'
  | 'empty'
  | 'failed'
  | 'canceled'
  | 'invalidated'
  | 'checking'
  | 'validation_failed';
type Recovery = 'retry' | 'new' | 'status' | null;
export type LiveChatTurn = {
  input: ChatStart;
  attempt: number;
  status: TurnStatus;
  phase: string;
  partial: string;
  original: ChatResult | null;
  result: ChatResult | null;
  outcome: 'succeeded' | 'empty';
  error: string | null;
  recovery: Recovery;
};
type Snapshot = {
  identity: string;
  conversationId: string;
  turns: LiveChatTurn[];
  draft: string;
  activeId: string | null;
  notice: string | null;
};
type Active = { requestId: string; attempt: number; abort: AbortController };
const changedMessage =
  '정보나 접근 권한이 바뀌어 이전 답변을 지웠어요. 현재 조건으로 다시 요청해 주세요.';
const failureMessage = (error: unknown) =>
  error instanceof ApiError && error.code === 'AI_NOT_CONFIGURED'
    ? 'AI 연결이 아직 준비되지 않았어요. 잠시 후 다시 요청해 주세요.'
    : '답변을 끝까지 받지 못했어요. 실행 상태를 확인해 주세요.';

// 이 객체의 수명은 Provider 한 개뿐이며 전역/영속 저장소가 아닙니다.
// 전송과 제어 요청은 MutationCache를 거쳐 기존 401·세션 generation 처리를 적용합니다.
export class LiveChatController {
  private state: Snapshot;
  private listeners = new Set<() => void>();
  private epoch = 0;
  private active: Active | null = null;
  private visible = false;
  private focused = true;
  private controls = new Map<string, number>();
  private validations = new Map<string, Promise<ChatResult | null>>();
  private validationControllers = new Set<AbortController>();
  constructor(private readonly client: QueryClient) {
    this.state = this.empty();
  }
  private identity() {
    const account = this.client.getQueryData<{ id: string } | null>(
      queryKeys.me,
    );
    return `${account?.id ?? ''}:${sessionGeneration(this.client)}`;
  }
  private empty(): Snapshot {
    return {
      identity: this.identity(),
      conversationId: crypto.randomUUID(),
      turns: [],
      draft: '',
      activeId: null,
      notice: null,
    };
  }
  private publish(state: Snapshot) {
    this.state = state;
    this.listeners.forEach((listener) => listener());
  }
  private updateTurn(
    id: string,
    attempt: number,
    patch: Partial<LiveChatTurn>,
  ) {
    this.publish({
      ...this.state,
      turns: this.state.turns.map((turn) =>
        turn.input.requestId === id && turn.attempt === attempt
          ? { ...turn, ...patch }
          : turn,
      ),
    });
  }
  private current(epoch: number) {
    return epoch === this.epoch && this.state.identity === this.identity();
  }
  private authenticated() {
    return !!this.client.getQueryData(queryKeys.me) && this.current(this.epoch);
  }
  private displayable() {
    return (
      this.visible && this.focused && document.visibilityState !== 'hidden'
    );
  }
  private nextControl(requestId: string) {
    const sequence = (this.controls.get(requestId) ?? 0) + 1;
    this.controls.set(requestId, sequence);
    return sequence;
  }
  private request<T>(operation: () => Promise<T>) {
    return this.client
      .getMutationCache()
      .build(this.client, {
        mutationFn: operation,
        retry: false,
        gcTime: 0,
      })
      .execute(undefined);
  }
  private abort() {
    this.active?.abort.abort();
    this.active = null;
    this.validationControllers.forEach((controller) => controller.abort());
    this.validationControllers.clear();
    this.validations.clear();
    this.controls.clear();
  }
  private sessionChanged = () => {
    if (this.state.identity === this.identity()) return;
    this.epoch++;
    this.abort();
    this.publish(this.empty());
  };
  connect = () => {
    const unsubscribe = this.client
      .getQueryCache()
      .subscribe(this.sessionChanged);
    this.sessionChanged();
    const focus = () => {
      this.focused = true;
      if (this.visible) this.revalidateAll();
    };
    const blur = () => {
      this.focused = false;
      this.hideResults();
    };
    const visibility = () =>
      document.visibilityState === 'hidden' ? blur() : focus();
    window.addEventListener('focus', focus);
    window.addEventListener('blur', blur);
    document.addEventListener('visibilitychange', visibility);
    return () => {
      unsubscribe();
      window.removeEventListener('focus', focus);
      window.removeEventListener('blur', blur);
      document.removeEventListener('visibilitychange', visibility);
      this.epoch++;
      this.abort();
      this.publish(this.empty());
    };
  };
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  getSnapshot = () => this.state;
  setDraft = (draft: string) =>
    this.publish({ ...this.state, draft, notice: null });
  setVisible = (visible: boolean) => {
    this.visible = visible;
    if (visible) this.revalidateAll();
    else this.hideResults();
  };
  private hideResults() {
    // 화면 이탈 이전에 시작한 재검증은 복귀 후 표시 권한의 근거가 아닙니다.
    this.validationControllers.forEach((controller) => controller.abort());
    this.validationControllers.clear();
    this.validations.clear();
    this.publish({
      ...this.state,
      turns: this.state.turns.map((turn) =>
        turn.original
          ? { ...turn, result: null, partial: '', status: 'checking' }
          : turn.status === 'pending'
            ? { ...turn, partial: '' }
            : turn,
      ),
    });
  }
  revalidateAll = () => {
    if (!this.authenticated()) return;
    this.hideResults();
    this.state.turns.forEach((turn) => {
      if (turn.original) void this.validate(turn.input.requestId);
    });
  };
  validate = (requestId: string): Promise<ChatResult | null> => {
    const turn = this.state.turns.find(
      (item) => item.input.requestId === requestId,
    );
    if (!turn?.original || !this.authenticated() || !this.displayable())
      return Promise.resolve(null);
    const existing = this.validations.get(requestId);
    if (existing) return existing;
    const epoch = this.epoch;
    const original = turn.original;
    const controller = new AbortController();
    this.validationControllers.add(controller);
    this.updateTurn(requestId, turn.attempt, {
      result: null,
      partial: '',
      status: 'checking',
      error: null,
    });
    const promise = this.request(() =>
      validateAiResult(requestId, turn.attempt, original, controller.signal),
    )
      .then((validation) => {
        if (
          !this.current(epoch) ||
          !this.displayable() ||
          controller.signal.aborted ||
          !this.state.turns.some(
            (item) =>
              item.input.requestId === requestId &&
              item.attempt === turn.attempt &&
              item.original === original,
          )
        )
          return null;
        if (!validation.valid || validation.result?.kind !== 'chat') {
          this.updateTurn(requestId, turn.attempt, {
            status: 'invalidated',
            original: null,
            result: null,
            partial: '',
            error: changedMessage,
            recovery: 'new',
          });
          return null;
        }
        this.updateTurn(requestId, turn.attempt, {
          status: turn.outcome,
          result: validation.result,
          error: null,
        });
        return validation.result;
      })
      .catch((error: unknown) => {
        if (
          !this.current(epoch) ||
          !this.displayable() ||
          controller.signal.aborted ||
          !this.state.turns.some(
            (item) =>
              item.input.requestId === requestId &&
              item.attempt === turn.attempt &&
              item.original === original,
          )
        )
          return null;
        if (
          error instanceof ApiError &&
          [401, 403, 404, 409].includes(error.status)
        ) {
          this.updateTurn(requestId, turn.attempt, {
            status: 'invalidated',
            original: null,
            result: null,
            partial: '',
            error: changedMessage,
            recovery: 'new',
          });
        } else {
          this.updateTurn(requestId, turn.attempt, {
            status: 'validation_failed',
            result: null,
            partial: '',
            error:
              '현재 정보를 확인하지 못해 답변을 숨겼어요. 다시 확인해 주세요.',
          });
        }
        return null;
      })
      .finally(() => {
        this.validationControllers.delete(controller);
        if (this.validations.get(requestId) === promise)
          this.validations.delete(requestId);
      });
    this.validations.set(requestId, promise);
    return promise;
  };
  copy = async (requestId: string, format?: (result: ChatResult) => string) => {
    const epoch = this.epoch;
    const result = await this.validate(requestId);
    if (!result || !this.current(epoch)) return false;
    await navigator.clipboard.writeText(
      format
        ? format(result)
        : [
            result.answer,
            ...result.cards.map((card) => `${card.title}\n${card.reason}`),
          ].join('\n\n'),
    );
    return this.current(epoch);
  };
  send = (raw: string) => {
    if (!this.authenticated() || this.active || this.state.activeId) return;
    const content = raw.normalize('NFC').trim();
    const history = this.state.turns.map((turn) => turn.input.content);
    if (
      history.length > 20 ||
      history.reduce(
        (sum, item) => sum + [...item].length,
        [...content].length,
      ) > 12000
    ) {
      this.publish({
        ...this.state,
        notice:
          '대화가 길어졌어요. 입력한 내용은 그대로 보관했어요. 새 대화를 시작해 주세요.',
      });
      return;
    }
    const input = ChatStart.safeParse({
      requestId: crypto.randomUUID(),
      conversationId: this.state.conversationId,
      clientMessageId: crypto.randomUUID(),
      content,
      resultFormat: 'rich',
      history,
      previousResults: this.state.turns
        .filter((turn) => !!turn.original)
        .map((turn) => ({
          requestId: turn.input.requestId,
          attempt: turn.attempt,
        })),
    });
    if (!input.success) {
      this.publish({
        ...this.state,
        notice: '메시지는 올바른 문자로 1~1,000자까지 보낼 수 있어요.',
      });
      return;
    }
    const turn: LiveChatTurn = {
      input: input.data,
      attempt: 1,
      status: 'pending',
      phase: '조건에 맞는 항목을 찾고 있어요…',
      partial: '',
      original: null,
      result: null,
      outcome: 'succeeded',
      error: null,
      recovery: null,
    };
    this.publish({
      ...this.state,
      turns: [...this.state.turns, turn],
      draft: '',
      notice: null,
    });
    void this.execute(turn, false);
  };
  retry = (requestId: string) => {
    if (!this.authenticated() || this.active || this.state.activeId) return;
    const turn = this.state.turns.find(
      (item) => item.input.requestId === requestId,
    );
    if (!turn) return;
    if (turn.recovery === 'status') {
      void this.checkStatus(requestId);
      return;
    }
    if (turn.recovery === 'retry') {
      const next = {
        ...turn,
        attempt: turn.attempt + 1,
        status: 'pending' as const,
        partial: '',
        original: null,
        result: null,
        error: null,
        recovery: null,
      };
      this.updateTurn(requestId, turn.attempt, next);
      void this.execute(next, true);
    } else if (turn.recovery === 'new') {
      // 원문이 유실된 완료/취소 요청은 결과를 복원하지 않고 새 메시지 ID로 실행합니다.
      const next = {
        ...turn,
        input: {
          ...turn.input,
          requestId: crypto.randomUUID(),
          clientMessageId: crypto.randomUUID(),
        },
        attempt: 1,
        status: 'pending' as const,
        partial: '',
        original: null,
        result: null,
        error: null,
        recovery: null,
      };
      this.updateTurn(requestId, turn.attempt, next);
      void this.execute(next, false);
    }
  };
  private async execute(turn: LiveChatTurn, retry: boolean) {
    const epoch = this.epoch;
    const active = {
      requestId: turn.input.requestId,
      attempt: turn.attempt,
      abort: new AbortController(),
    };
    this.active = active;
    this.publish({ ...this.state, activeId: active.requestId, notice: null });
    let original: ChatResult | null = null;
    let terminal: AiEvent | null = null;
    const onEvent = (event: AiEvent) => {
      if (
        !this.current(epoch) ||
        this.active !== active ||
        event.requestId !== active.requestId ||
        event.attempt !== active.attempt
      )
        return;
      if (event.event === 'progress')
        this.updateTurn(active.requestId, active.attempt, {
          phase:
            event.stage === 'writing'
              ? '답변을 작성하고 있어요…'
              : event.stage === 'validating'
                ? '현재 정보를 확인하고 있어요…'
                : '조건에 맞는 항목을 찾고 있어요…',
        });
      else if (event.event === 'answer.delta') {
        const current = this.state.turns.find(
          (item) => item.input.requestId === active.requestId,
        );
        this.updateTurn(active.requestId, active.attempt, {
          partial: (current?.partial ?? '') + event.text,
          phase: '답변을 작성하고 있어요…',
        });
      } else if (event.event === 'result' && event.result.kind === 'chat')
        original = event.result;
      else if (
        ['done', 'error', 'canceled', 'invalidated'].includes(event.event)
      )
        terminal = event;
    };
    try {
      await this.request(() =>
        retry
          ? retryAi(
              turn.input.requestId,
              { expectedAttempt: turn.attempt - 1, input: turn.input },
              'chat',
              onEvent,
              active.abort.signal,
            )
          : startChat(turn.input, onEvent, active.abort.signal),
      );
      if (!this.current(epoch) || this.active !== active) return;
      // Callback의 최종 이벤트를 별도 참조로 읽어 타입 축소와 실행 순서를 분리합니다.
      const event = terminal as AiEvent | null;
      if (event?.event === 'done' && original) {
        this.updateTurn(active.requestId, active.attempt, {
          partial: '',
          original,
          outcome: event.status,
          status: 'checking',
        });
        await this.validate(active.requestId);
      } else if (event?.event === 'invalidated') {
        this.updateTurn(active.requestId, active.attempt, {
          partial: '',
          original: null,
          result: null,
          status: 'invalidated',
          error: changedMessage,
          recovery: 'new',
        });
      } else if (event?.event === 'canceled') {
        this.updateTurn(active.requestId, active.attempt, {
          partial: '',
          status: 'canceled',
          error: '응답을 중지했어요.',
          recovery: 'new',
        });
      } else if (event?.event === 'error') {
        this.updateTurn(active.requestId, active.attempt, {
          partial: '',
          status: 'failed',
          error: event.failure.message,
          recovery:
            event.failure.retryable && turn.attempt < 3 ? 'retry' : 'new',
        });
      } else throw new Error('Incomplete AI response');
    } catch (error) {
      if (!this.current(epoch) || this.active !== active) return;
      if (error instanceof ApiError && error.code === 'AI_NOT_CONFIGURED') {
        this.updateTurn(active.requestId, active.attempt, {
          partial: '',
          original: null,
          result: null,
          status: 'failed',
          error: failureMessage(error),
          recovery: 'new',
        });
        return;
      }
      this.updateTurn(active.requestId, active.attempt, {
        partial: '',
        original: null,
        result: null,
        status: 'failed',
        error: failureMessage(error),
        recovery: 'status',
      });
      await this.checkStatus(active.requestId);
    } finally {
      if (this.current(epoch) && this.active === active) {
        this.active = null;
        this.publish({ ...this.state, activeId: null });
      }
    }
  }
  checkStatus = async (requestId: string) => {
    const turn = this.state.turns.find(
      (item) => item.input.requestId === requestId,
    );
    if (!turn || !this.authenticated()) return;
    const epoch = this.epoch;
    const control = this.nextControl(requestId);
    try {
      const view = await this.request(() => getAiRequest(requestId));
      if (!this.current(epoch) || this.controls.get(requestId) !== control)
        return;
      this.applyStatus(turn, view);
    } catch (error) {
      if (!this.current(epoch) || this.controls.get(requestId) !== control)
        return;
      this.updateTurn(requestId, turn.attempt, {
        status: 'failed',
        partial: '',
        original: null,
        result: null,
        recovery:
          error instanceof ApiError && error.status === 404 ? 'new' : 'status',
        error:
          error instanceof ApiError && error.status === 404
            ? '실행 정보를 찾을 수 없어요. 같은 내용으로 다시 요청할 수 있어요.'
            : '실행 상태를 확인하지 못했어요. 상태를 다시 확인해 주세요.',
      });
    }
  };
  private applyStatus(turn: LiveChatTurn, view: AiRequestView) {
    const patch: Partial<LiveChatTurn> = {
      partial: '',
      original: null,
      result: null,
      status: 'failed',
      attempt: view.attempt,
    };
    if (view.status === 'pending')
      Object.assign(patch, {
        error:
          '서버에서 요청을 정리하고 있어요. 잠시 후 상태를 다시 확인해 주세요.',
        recovery: 'status',
      });
    else if (view.status === 'failed')
      Object.assign(patch, {
        error: view.failure?.message ?? '답변을 준비하지 못했어요.',
        recovery: view.failure?.retryable && view.attempt < 3 ? 'retry' : 'new',
      });
    else if (view.status === 'canceled')
      Object.assign(patch, {
        status: 'canceled',
        error: '응답을 중지했어요.',
        recovery: 'new',
      });
    else
      Object.assign(patch, {
        error:
          '요청은 완료됐지만 답변을 끝까지 받지 못했어요. 같은 내용으로 다시 요청해 주세요.',
        recovery: 'new',
      });
    this.updateTurn(turn.input.requestId, turn.attempt, patch);
  }
  stop = () => {
    const active = this.active;
    if (!active) return;
    const epoch = this.epoch;
    const control = this.nextControl(active.requestId);
    const turn = this.state.turns.find(
      (item) => item.input.requestId === active.requestId,
    );
    this.active = null;
    active.abort.abort();
    this.updateTurn(active.requestId, active.attempt, {
      partial: '',
      original: null,
      result: null,
      status: 'canceled',
      error: '응답 중지를 요청했어요.',
      recovery: null,
    });
    // 서버의 중단 판정 전 같은 대화에 새 실행을 겹쳐 보내지 않습니다.
    void this.request(() => cancelAi(active.requestId, active.attempt))
      .then((view) => {
        if (
          turn &&
          this.current(epoch) &&
          this.controls.get(active.requestId) === control
        )
          this.applyStatus(turn, view);
      })
      .catch(() => {
        if (
          this.current(epoch) &&
          this.controls.get(active.requestId) === control
        )
          this.updateTurn(active.requestId, active.attempt, {
            error: '화면의 응답을 중지했어요. 서버 상태는 다시 확인해 주세요.',
            recovery: 'status',
          });
      })
      .finally(() => {
        if (this.current(epoch) && this.state.activeId === active.requestId)
          this.publish({ ...this.state, activeId: null });
      });
  };
  clear = () => {
    const active = this.active;
    this.epoch++;
    this.abort();
    this.publish(this.empty());
    if (active)
      void this.request(() => cancelAi(active.requestId, active.attempt)).catch(
        () => {},
      );
  };
}

export const LiveChatContext = createContext<LiveChatController | null>(null);
export function useLiveChatController() {
  const client = useQueryClient();
  const [controller] = useState(() => new LiveChatController(client));
  useEffect(() => controller.connect(), [controller]);
  return controller;
}
export function useLiveChat() {
  const controller = useContext(LiveChatContext);
  if (!controller) throw new Error('AiChatProvider가 필요합니다.');
  return {
    controller,
    state: useSyncExternalStore(controller.subscribe, controller.getSnapshot),
  };
}
