// UTF-8·줄·이벤트 경계를 누적 처리하고 현재 AI 실행의 종료 순서를 확인합니다.
import { AiEvent, type AiPurpose } from './contract';

export class AiStreamError extends Error {
  constructor(readonly kind: 'interrupted' | 'protocol') {
    super(
      kind === 'interrupted'
        ? '답변 연결이 끊겼어요. 실행 상태를 확인해 주세요.'
        : 'AI 응답 형식을 확인하지 못했어요.',
    );
    this.name = 'AiStreamError';
  }
}
export type StreamIdentity = {
  requestId: string;
  attempt: number;
  purpose: AiPurpose;
};

export async function readAiStream(
  response: Response,
  expected: StreamIdentity,
  onEvent: (event: AiEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (
    response.headers
      .get('Content-Type')
      ?.toLowerCase()
      .split(';')[0]
      ?.trim() !== 'text/event-stream' ||
    !response.body
  ) {
    await response.body?.cancel();
    throw new AiStreamError('protocol');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8', { fatal: true });
  let buffer = '';
  let eventName = '';
  let data: string[] = [];
  let frameLength = 0;
  let sequence = 0;
  let started = false;
  let hasResult = false;
  let terminal = false;
  let abortError: unknown;
  const onAbort = () => {
    abortError = signal?.reason ?? new DOMException('Aborted', 'AbortError');
    void reader.cancel().catch(() => {});
  };
  signal?.addEventListener('abort', onAbort, { once: true });
  if (signal?.aborted) onAbort();

  function dispatch() {
    if (data.length === 0) {
      eventName = '';
      frameLength = 0;
      return;
    }
    let event: AiEvent;
    try {
      const payload: unknown = JSON.parse(data.join('\n'));
      if (
        typeof payload !== 'object' ||
        payload === null ||
        Array.isArray(payload) ||
        'event' in payload
      )
        throw new Error();
      event = AiEvent.parse({ ...payload, event: eventName });
    } catch {
      throw new AiStreamError('protocol');
    }
    data = [];
    eventName = '';
    frameLength = 0;
    if (
      event.requestId !== expected.requestId ||
      event.attempt !== expected.attempt ||
      event.sequence !== sequence + 1 ||
      terminal
    )
      throw new AiStreamError('protocol');
    sequence = event.sequence;
    if (!started) {
      if (event.event !== 'started' || event.purpose !== expected.purpose)
        throw new AiStreamError('protocol');
      started = true;
    } else if (event.event === 'started') throw new AiStreamError('protocol');
    if (event.event === 'result') {
      if (hasResult || event.result.kind !== expected.purpose)
        throw new AiStreamError('protocol');
      hasResult = true;
    } else if (
      (event.event === 'answer.delta' || event.event === 'progress') &&
      hasResult
    )
      throw new AiStreamError('protocol');
    if (event.event === 'done') {
      if (!hasResult) throw new AiStreamError('protocol');
      terminal = true;
    } else if (['error', 'canceled', 'invalidated'].includes(event.event))
      terminal = true;
    onEvent(event);
  }
  function line(value: string) {
    if (!value) {
      dispatch();
      return;
    }
    frameLength += value.length;
    if (frameLength > 1_048_576) throw new AiStreamError('protocol');
    if (value.startsWith(':')) return;
    const colon = value.indexOf(':');
    const field = colon < 0 ? value : value.slice(0, colon);
    let payload = colon < 0 ? '' : value.slice(colon + 1);
    if (payload.startsWith(' ')) payload = payload.slice(1);
    if (field === 'event') eventName = payload;
    else if (field === 'data') data.push(payload);
  }
  function consume(end = false) {
    let match: RegExpExecArray | null;
    while (!terminal && !abortError && (match = /\r\n|\r|\n/.exec(buffer))) {
      if (!end && match[0] === '\r' && match.index === buffer.length - 1) break;
      line(buffer.slice(0, match.index));
      buffer = buffer.slice(match.index + match[0].length);
    }
    if (buffer.length + frameLength > 1_048_576)
      throw new AiStreamError('protocol');
  }
  try {
    while (!terminal) {
      if (abortError) throw abortError;
      const chunk = await reader.read();
      if (abortError) throw abortError;
      if (chunk.done) {
        buffer += decoder.decode();
        consume(true);
        if (abortError) throw abortError;
        // 빈 줄로 끝나지 않은 마지막 이벤트는 완성된 SSE 이벤트가 아닙니다.
        if (!terminal) throw new AiStreamError('interrupted');
        break;
      }
      buffer += decoder.decode(chunk.value, { stream: true });
      consume();
      if (abortError) throw abortError;
    }
  } catch (error) {
    if (abortError) throw abortError;
    if (
      error instanceof AiStreamError ||
      (error instanceof DOMException && error.name === 'AbortError')
    )
      throw error;
    throw new AiStreamError(
      error instanceof TypeError ? 'interrupted' : 'protocol',
    );
  } finally {
    signal?.removeEventListener('abort', onAbort);
    await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
