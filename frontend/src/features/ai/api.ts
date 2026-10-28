// AI 스트림과 실행 제어 API를 실제 서버 계약으로 호출합니다.
import { apiRequest, apiRequestRaw, ApiError } from '@/lib/api';
import { Id, PositiveSafeInteger, success } from '@/lib/api-contract';
import {
  AiEvent,
  AiPurpose,
  AiRequestView,
  AiResult,
  ChatStart,
  TargetStart,
  RetryStart,
  ResultValidation,
} from './contract';
import { AiStreamError, readAiStream, type StreamIdentity } from './stream';

type OnEvent = (event: AiEvent) => void;
async function stream(
  path: string,
  input: unknown,
  expected: StreamIdentity,
  onEvent: OnEvent,
  signal?: AbortSignal,
) {
  let response: Response;
  try {
    response = await apiRequestRaw(path, {
      method: 'POST',
      json: input,
      headers: { Accept: 'text/event-stream' },
      signal,
    });
  } catch (error) {
    if (
      error instanceof ApiError ||
      signal?.aborted ||
      (error instanceof DOMException && error.name === 'AbortError')
    )
      throw error;
    throw new AiStreamError('interrupted');
  }
  await readAiStream(response, expected, onEvent, signal);
}
export function startChat(
  input: ChatStart,
  onEvent: OnEvent,
  signal?: AbortSignal,
) {
  const body = ChatStart.parse(input);
  return stream(
    '/ai/chat/stream',
    body,
    { requestId: body.requestId, attempt: 1, purpose: 'chat' },
    onEvent,
    signal,
  );
}
export function startApplicantReview(
  applicationId: string,
  input: TargetStart,
  onEvent: OnEvent,
  signal?: AbortSignal,
) {
  const body = TargetStart.parse(input);
  return stream(
    `/applications/${Id.parse(applicationId)}/ai-reviews/stream`,
    body,
    { requestId: body.requestId, attempt: 1, purpose: 'applicant_review' },
    onEvent,
    signal,
  );
}
export function startApplicantRecommendations(
  teamId: string,
  input: TargetStart,
  onEvent: OnEvent,
  signal?: AbortSignal,
) {
  const body = TargetStart.parse(input);
  return stream(
    `/teams/${Id.parse(teamId)}/applicant-recommendations/stream`,
    body,
    {
      requestId: body.requestId,
      attempt: 1,
      purpose: 'applicant_recommendation',
    },
    onEvent,
    signal,
  );
}
export function retryAi(
  requestId: string,
  input: RetryStart,
  purpose: AiPurpose,
  onEvent: OnEvent,
  signal?: AbortSignal,
) {
  const body = RetryStart.parse(input);
  if (body.input.requestId !== requestId) throw new AiStreamError('protocol');
  return stream(
    `/ai/requests/${Id.parse(requestId)}/retries/stream`,
    body,
    {
      requestId,
      attempt: body.expectedAttempt + 1,
      purpose: AiPurpose.parse(purpose),
    },
    onEvent,
    signal,
  );
}
export async function getAiRequest(requestId: string, signal?: AbortSignal) {
  return success(AiRequestView).parse(
    await apiRequest(`/ai/requests/${Id.parse(requestId)}`, { signal }),
  ).data;
}
export async function cancelAi(
  requestId: string,
  expectedAttempt: number,
  signal?: AbortSignal,
) {
  return success(AiRequestView).parse(
    await apiRequest(`/ai/requests/${Id.parse(requestId)}/cancellation`, {
      method: 'PUT',
      json: { expectedAttempt: PositiveSafeInteger.parse(expectedAttempt) },
      signal,
    }),
  ).data;
}
export async function validateAiResult(
  requestId: string,
  attempt: number,
  result: AiResult,
  signal?: AbortSignal,
) {
  return success(ResultValidation).parse(
    await apiRequest(`/ai/requests/${Id.parse(requestId)}/validation`, {
      method: 'POST',
      json: {
        attempt: PositiveSafeInteger.parse(attempt),
        result: AiResult.parse(result),
      },
      signal,
    }),
  ).data;
}
