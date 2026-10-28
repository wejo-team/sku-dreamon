// docs/api/ai.md: 검토·추천은 명시적 요청이며 원본 결과를 검증 요청에 보존합니다.
import { useCallback, useEffect, useRef, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import {
  cancelAi,
  getAiRequest,
  retryAi,
  startApplicantRecommendations,
  startApplicantReview,
  validateAiResult,
} from '@/features/ai/api';
import type {
  AiEvent,
  AiFailure,
  AiResult,
  TargetStart,
} from '@/features/ai/contract';
import type { Account } from '@/features/auth/api';
import { ApiError } from '@/lib/api';
import { queryKeys, sessionGeneration } from '@/lib/query-keys';

type Purpose = 'applicant_review' | 'applicant_recommendation';
type Snapshot = { requestId: string; attempt: number; original: AiResult };
type Request = { input: TargetStart; attempt: number };
type State = {
  phase: 'idle' | 'pending' | 'checking' | 'finished' | 'failed' | 'canceled';
  text: string;
  message: string;
  request?: Request;
  failure?: AiFailure;
};
const idle: State = { phase: 'idle', text: '', message: '' };
const changed =
  '지원 정보나 검토 권한이 변경되어 이전 결과를 숨겼어요. 최신 정보로 다시 요청해 주세요.';
const denied = (error: unknown) =>
  error instanceof ApiError && [401, 403, 404].includes(error.status);
function errorMessage(error: unknown) {
  if (denied(error)) return changed;
  if (error instanceof ApiError && error.code === 'AI_NOT_CONFIGURED')
    return 'AI 서비스가 아직 준비되지 않았어요. 잠시 후 다시 요청해 주세요.';
  if (error instanceof ApiError && error.status === 409)
    return '요청 상태가 변경됐어요. 상태를 확인한 뒤 다시 요청해 주세요.';
  return '응답을 확인하지 못했어요. 연결 상태를 확인한 뒤 다시 시도해 주세요.';
}

export function useTargetAi({
  purpose,
  targetId,
  ownerId,
  generation,
  revision,
}: {
  purpose: Purpose;
  targetId: string;
  ownerId: string;
  generation: number;
  revision: string;
}) {
  const client = useQueryClient();
  const cacheKey = [
    'ai',
    'target-result',
    ownerId,
    generation,
    purpose,
    targetId,
  ] as const;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(
    () => client.getQueryData<Snapshot>(cacheKey) ?? null,
  );
  const [result, setResult] = useState<AiResult | null>(null);
  const [state, setState] = useState<State>(idle);
  const [validationError, setValidationError] = useState('');
  const [validating, setValidating] = useState(false);
  const [copied, setCopied] = useState(false);
  const [canceling, setCanceling] = useState(false);
  const stream = useRef<AbortController | null>(null);
  const validationAbort = useRef<AbortController | null>(null);
  const visible = useRef(true);
  const starting = useRef(false);
  const operation = useRef(0);
  const validation = useRef(0);
  const mounted = useRef(true);
  const { mutateAsync } = useMutation({
    mutationFn: (call: () => Promise<unknown>) => call(),
  });
  const execute = useCallback(
    <T>(call: () => Promise<T>) => mutateAsync(call) as Promise<T>,
    [mutateAsync],
  );
  const current = useCallback(
    () =>
      mounted.current &&
      sessionGeneration(client) === generation &&
      client.getQueryData<Account | null>(queryKeys.me)?.id === ownerId,
    [client, generation, ownerId],
  );
  const clearSnapshot = useCallback(() => {
    client.removeQueries({
      queryKey: ['ai', 'target-result', ownerId, generation, purpose, targetId],
      exact: true,
    });
    setSnapshot(null);
    setResult(null);
  }, [client, ownerId, generation, purpose, targetId]);

  const validate = useCallback(
    async (saved: Snapshot): Promise<AiResult | null> => {
      if (!visible.current) return null;
      const ticket = ++validation.current;
      validationAbort.current?.abort();
      const controller = new AbortController();
      validationAbort.current = controller;
      setResult(null);
      setValidating(true);
      setValidationError('');
      setCopied(false);
      try {
        // 해시 검증에는 표시용 갱신 DTO가 아닌 최초 수신 결과를 그대로 보냅니다.
        const checked = await execute(() =>
          validateAiResult(
            saved.requestId,
            saved.attempt,
            saved.original,
            controller.signal,
          ),
        );
        if (!current() || !visible.current || ticket !== validation.current)
          return null;
        if (
          !checked.valid ||
          !checked.result ||
          checked.result.kind !== purpose
        ) {
          clearSnapshot();
          setValidationError(changed);
          return null;
        }
        setResult(checked.result);
        setState((previous) => ({
          ...previous,
          phase: 'finished',
          text: '',
          message: '',
        }));
        return checked.result;
      } catch (error) {
        if (!current() || ticket !== validation.current) return null;
        if (denied(error)) clearSnapshot();
        setValidationError(errorMessage(error));
        return null;
      } finally {
        if (current() && ticket === validation.current) setValidating(false);
      }
    },
    [current, execute, purpose, clearSnapshot],
  );

  const retire = useCallback(() => {
    mounted.current = false;
    operation.current++;
    validation.current++;
    stream.current?.abort();
    validationAbort.current?.abort();
  }, []);
  useEffect(() => {
    mounted.current = true;
    return retire;
  }, [retire]);
  useEffect(() => {
    let active = true;
    void Promise.resolve().then(() => {
      if (snapshot && active && current()) void validate(snapshot);
    });
    const revalidate = () => {
      if (document.visibilityState !== 'hidden' && current()) {
        visible.current = true;
        if (snapshot) void validate(snapshot);
      }
    };
    const hide = () => {
      visible.current = false;
      validation.current++;
      validationAbort.current?.abort();
      setResult(null);
      setValidating(false);
      setCopied(false);
      setState((previous) => ({ ...previous, text: '' }));
    };
    const visibilityChanged = () =>
      document.visibilityState === 'hidden' ? hide() : revalidate();
    window.addEventListener('focus', revalidate);
    window.addEventListener('blur', hide);
    document.addEventListener('visibilitychange', visibilityChanged);
    return () => {
      active = false;
      window.removeEventListener('focus', revalidate);
      window.removeEventListener('blur', hide);
      document.removeEventListener('visibilitychange', visibilityChanged);
    };
  }, [snapshot, revision, validate, current]);

  async function reconcile(request: Request) {
    if (canceling) return;
    const ticket = ++operation.current;
    try {
      const status = await execute(() => getAiRequest(request.input.requestId));
      if (!current() || ticket !== operation.current) return;
      const retryable =
        status.status === 'failed' && status.attempt === request.attempt
          ? status.failure
          : undefined;
      setState({
        phase: status.status === 'pending' ? 'checking' : 'failed',
        request,
        text: '',
        failure: retryable ?? undefined,
        message:
          status.status === 'pending'
            ? '연결이 끊겼지만 요청은 처리 중이에요. 상태를 확인하거나 취소할 수 있어요.'
            : status.status === 'canceled'
              ? '요청이 취소되었어요.'
              : (retryable?.message ??
                '완성된 응답을 받지 못했어요. 새로 요청해 주세요.'),
      });
    } catch (error) {
      if (current() && ticket === operation.current)
        setState({
          phase: 'failed',
          request,
          text: '',
          message: errorMessage(error),
        });
    }
  }

  async function run(retry = false) {
    if (
      !current() ||
      starting.current ||
      state.phase === 'pending' ||
      state.phase === 'checking' ||
      validating
    )
      return;
    const previous = state.request;
    if (
      retry &&
      (!previous || !state.failure?.retryable || previous.attempt >= 3)
    )
      return;
    starting.current = true;
    const input =
      retry && previous ? previous.input : { requestId: crypto.randomUUID() };
    const attempt = retry && previous ? previous.attempt + 1 : 1;
    const request = { input, attempt };
    const ticket = ++operation.current;
    validation.current++;
    validationAbort.current?.abort();
    stream.current?.abort();
    const controller = new AbortController();
    stream.current = controller;
    clearSnapshot();
    setValidationError('');
    setCopied(false);
    setState({
      phase: 'pending',
      text: '',
      message: '등록된 정보를 확인하고 있어요.',
      request,
    });
    let finalResult: AiResult | null = null;
    const onEvent = (event: AiEvent) => {
      if (
        !current() ||
        ticket !== operation.current ||
        controller.signal.aborted
      )
        return;
      if (event.event === 'answer.delta' && visible.current)
        setState((value) => ({ ...value, text: value.text + event.text }));
      if (event.event === 'progress')
        setState((value) => ({
          ...value,
          message:
            event.stage === 'writing'
              ? '검토 내용을 작성하고 있어요.'
              : '등록된 정보를 확인하고 있어요.',
        }));
      if (event.event === 'result') finalResult = event.result;
      if (event.event === 'done' && finalResult) {
        const saved = {
          requestId: input.requestId,
          attempt,
          original: finalResult,
        };
        client.setQueryData(cacheKey, saved);
        setSnapshot(saved);
        setState({ phase: 'finished', text: '', message: '', request });
      }
      if (event.event === 'error')
        setState({
          phase: 'failed',
          text: '',
          message: event.failure.message,
          failure: event.failure,
          request,
        });
      if (event.event === 'invalidated')
        setState({ phase: 'failed', text: '', message: changed, request });
      if (event.event === 'canceled')
        setState({
          phase: 'canceled',
          text: '',
          message: '요청을 취소했어요.',
          request,
        });
    };
    try {
      await execute(() =>
        retry && previous
          ? retryAi(
              input.requestId,
              { expectedAttempt: previous.attempt, input },
              purpose,
              onEvent,
              controller.signal,
            )
          : purpose === 'applicant_review'
            ? startApplicantReview(targetId, input, onEvent, controller.signal)
            : startApplicantRecommendations(
                targetId,
                input,
                onEvent,
                controller.signal,
              ),
      );
    } catch (error) {
      if (
        !current() ||
        ticket !== operation.current ||
        controller.signal.aborted
      )
        return;
      if (error instanceof ApiError)
        setState({
          phase: 'failed',
          text: '',
          message: errorMessage(error),
          request,
        });
      else await reconcile(request);
    } finally {
      starting.current = false;
    }
  }

  async function cancel() {
    if (!state.request || !current() || canceling) return;
    const request = state.request;
    const ticket = ++operation.current;
    stream.current?.abort();
    setCanceling(true);
    setState({
      phase: 'checking',
      text: '',
      message: '취소 상태를 확인하고 있어요.',
      request,
    });
    try {
      const status = await execute(() =>
        cancelAi(request.input.requestId, request.attempt),
      );
      if (!current() || ticket !== operation.current) return;
      setState({
        phase: 'canceled',
        text: '',
        message:
          status.status === 'canceled'
            ? '요청을 취소했어요.'
            : '요청 처리가 이미 끝났어요. 결과가 필요하면 새로 요청해 주세요.',
        request,
      });
    } catch (error) {
      if (!current() || ticket !== operation.current) return;
      if (denied(error))
        setState({
          phase: 'failed',
          text: '',
          message: errorMessage(error),
          request,
        });
      else await reconcile(request);
    } finally {
      if (current()) setCanceling(false);
    }
  }

  async function copy(format: (value: AiResult) => string) {
    if (!snapshot || !current()) return;
    const checked = await validate(snapshot);
    if (!checked || !current()) return;
    try {
      await navigator.clipboard.writeText(format(checked));
      if (current()) setCopied(true);
    } catch {
      if (current())
        setValidationError(
          '복사하지 못했어요. 브라우저의 클립보드 권한을 확인해 주세요.',
        );
    }
  }
  return {
    state,
    canceling,
    result,
    validating,
    validationError,
    copied,
    run,
    cancel,
    copy,
    revalidate: () => snapshot && validate(snapshot),
    checkStatus: () => state.request && reconcile(state.request),
    canRetry:
      !!state.failure?.retryable &&
      !!state.request &&
      state.request.attempt < 3,
    canValidate: !!snapshot,
  };
}
