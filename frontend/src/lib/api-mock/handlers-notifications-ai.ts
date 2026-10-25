/**
 * [참조 출처]
 * 1. docs/api/notifications.md#notification-endpoints - 본인 알림만, 정렬 occurredAt DESC, id DESC, 타인·없는 ID 404
 * 2. docs/api/notifications.md#notification-fields - NotificationPage.unreadCount는 필터와 무관한 전체 미읽음 수,
 *    여러 ID 읽음은 전부 성공 또는 전부 실패, 이미 읽은 항목은 최초 readAt 유지
 * 3. docs/api/ai.md#conversation-endpoints - 202 + Location: /api/v1/ai/requests/{id}, 현재 대화만 허용
 * 4. docs/api/ai.md#request-lifecycle - clientMessageId 재전송 동일 결과·다른 본문 409, 진행 중 요청 409, 재시도·중단 규칙
 * 5. docs/api/ai.md#applicant-endpoints - 지원자 검토·후보 추천은 받은 팀장만, 지원 상태를 바꾸지 않음
 * 6. docs/api/ai.md#result-fields - ChatResult 카드 최대 3개, ApplicantReviewResult·ApplicantRecommendationResult
 *
 * AI 응답은 실제 모델을 호출하지 않는 목업입니다(docs/design/handoff.md 「데이터·인증·AI의 실제 범위」).
 */

import {
  AiCancel,
  AiRetry,
  ConversationCreate,
  MessageCreate,
  type AiMessage,
  type AiRequest,
  type ResourceCard,
} from '@/features/ai/api';
import { ReadNotifications } from '@/features/notifications/api';
import {
  toNotificationDto,
  type NotificationRecord,
} from '@/features/demo/fixtures';
import {
  MockRouter,
  booleanQuery,
  conflict,
  forbidden,
  notFound,
  ok,
  paginate,
  validate,
} from '@/lib/api-mock/http';
import {
  contestSummaries,
  db,
  newId,
  nowIso,
  profileOf,
  requireSession,
  teamById,
} from '@/lib/api-mock/state';

const toNotification = (record: NotificationRecord) =>
  toNotificationDto(record);

const mine = (accountId: string) =>
  db().notifications.filter((item) => item.recipientAccountId === accountId);
const unreadCount = (accountId: string) =>
  mine(accountId).filter((item) => !item.readAt).length;

function markRead(ids: string[], accountId: string) {
  const owned = new Set(mine(accountId).map((item) => item.id));
  // [출처 2] 하나라도 타인·없는 ID면 전체 변경 없이 404
  if (ids.some((id) => !owned.has(id))) notFound();
  const readAt = nowIso();
  db().notifications = db().notifications.map((item) =>
    ids.includes(item.id) && !item.readAt ? { ...item, readAt } : item,
  );
}

// ─── AI 목업 상태 ────────────────────────────────────────────
type ConversationRecord = {
  id: string;
  ownerAccountId: string;
  createdAt: string;
  active: boolean;
  messages: AiMessage[];
};
const conversations = new Map<string, ConversationRecord>();
const requests = new Map<string, AiRequest & { ownerAccountId: string }>();

export function resetAiMock() {
  conversations.clear();
  requests.clear();
}

const location = (id: string) => ({ Location: `/api/v1/ai/requests/${id}` });
// 소유자 ID는 서버 내부 정보이므로 AiRequest 응답에서 뺍니다.
const publicRequest = (
  record: AiRequest & { ownerAccountId: string },
): AiRequest => {
  const request: Partial<typeof record> = { ...record };
  delete request.ownerAccountId;
  return request as AiRequest;
};

// [출처 6] 메시지의 단어와 일치하는 공모전·팀·공개 사람을 최대 3개 카드로
function chatCards(content: string, accountId: string): ResourceCard[] {
  const text = content.toLowerCase();
  const fieldName = (code: string) =>
    db().catalogs.fields.find((item) => item.code === code)?.displayName ?? '';
  const roleName = (code: string) =>
    db().catalogs.roles.find((item) => item.code === code)?.displayName ?? '';
  const matches = (words: string[]) =>
    words.some((word) => word && text.includes(word.toLowerCase()));
  const cards: ResourceCard[] = [];
  for (const contest of contestSummaries())
    if (
      contest.registrationStatus === 'open' &&
      matches([...contest.fieldCodes.map(fieldName), '공모전'])
    )
      cards.push({
        kind: 'contest',
        resourceId: contest.id,
        title: contest.title,
        reason: '요청한 분야와 관련된 접수 중인 공모전이에요.',
        fieldCodes: contest.fieldCodes,
        roleCodes: [],
        isDemo: contest.isDemo,
      });
  for (const record of db().teams) {
    const team = teamById(record.id)!;
    if (
      team.isRecruiting &&
      team.ownerAccountId !== accountId &&
      matches([...team.roleCodes.map(roleName), '팀'])
    )
      cards.push({
        kind: 'team',
        resourceId: team.id,
        title: team.name,
        reason: '요청한 역할을 모집 중인 팀이에요.',
        fieldCodes: team.fieldCodes,
        roleCodes: team.roleCodes,
        isDemo: team.isDemo,
      });
  }
  for (const profile of db().profiles)
    if (
      profile.isPublic &&
      profile.accountId !== accountId &&
      matches([...profile.roleCodes.map(roleName), '사람'])
    )
      cards.push({
        kind: 'person',
        resourceId: profile.accountId,
        title: profile.realName,
        reason: '공개 프로필의 희망 역할이 요청과 맞아요.',
        fieldCodes: profile.fieldCodes,
        roleCodes: profile.roleCodes,
        isDemo: profile.isDemo,
      });
  return cards.slice(0, 3);
}

function activeConversation(id: string, accountId: string) {
  const conversation = conversations.get(id);
  // [출처 3] 교체·로그아웃된 대화는 ID를 알아도 404
  if (
    !conversation ||
    !conversation.active ||
    conversation.ownerAccountId !== accountId
  )
    notFound();
  return conversation!;
}

function ownedRequest(id: string, accountId: string) {
  const request = requests.get(id);
  if (!request || request.ownerAccountId !== accountId) notFound();
  if (
    request!.conversationId &&
    !conversations.get(request!.conversationId)?.active
  )
    notFound();
  return request!;
}

// 목업은 요청을 접수한 뒤 즉시 처리 결과를 준비합니다(pending → succeeded/empty).
function completeChat(
  request: AiRequest & { ownerAccountId: string },
  content: string,
) {
  const cards = chatCards(content, request.ownerAccountId);
  const generatedAt = nowIso();
  const result = {
    kind: 'chat' as const,
    answer: cards.length
      ? '조건에 맞는 항목을 찾았어요.'
      : '조건에 맞는 결과를 찾지 못했어요. 다른 분야나 역할로 다시 물어봐 주세요.',
    cards,
    generatedAt,
    referencesChanged: false,
  };
  Object.assign(request, {
    status: cards.length ? 'succeeded' : 'empty',
    result,
    failure: null,
    updatedAt: generatedAt,
  });
  const conversation = conversations.get(request.conversationId!)!;
  conversation.messages.push({
    id: newId(),
    clientMessageId: null,
    role: 'assistant',
    content: result.answer,
    sequence: conversation.messages.length + 1,
    createdAt: generatedAt,
  });
}

function receivedApplication(applicationId: string, accountId: string) {
  const application = db().applications.find(
    (item) => item.id === applicationId,
  );
  if (!application) notFound();
  const team = teamById(application!.teamId)!;
  // [출처 5] 지원자 본인 등 관계는 있으나 팀장이 아니면 403, 관계 밖이면 404
  if (team.ownerAccountId !== accountId) {
    if (application!.applicantAccountId === accountId) forbidden();
    notFound();
  }
  return application!;
}

export function registerNotificationAndAiRoutes(router: MockRouter) {
  router
    // [출처 1, 2]
    .on('GET', '/me/notifications', ({ query }) => {
      const accountId = requireSession();
      const unreadOnly = booleanQuery(query, 'unreadOnly');
      const items = mine(accountId)
        .filter((item) => !unreadOnly || !item.readAt)
        .sort(
          (left, right) =>
            right.occurredAt.localeCompare(left.occurredAt) ||
            right.id.localeCompare(left.id),
        )
        .map(toNotification);
      return new Response(
        JSON.stringify({
          ...paginate(items, query),
          unreadCount: unreadCount(accountId),
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    })
    .on('GET', '/me/notifications/unread-count', () =>
      ok({ unreadCount: unreadCount(requireSession()) }),
    )
    .on('PUT', '/me/notifications/{notificationId}/read', ({ params }) => {
      const accountId = requireSession();
      markRead([params.notificationId!], accountId);
      return ok(
        toNotification(
          mine(accountId).find((item) => item.id === params.notificationId)!,
        ),
      );
    })
    .on('PUT', '/me/notifications/read', ({ body }) => {
      const accountId = requireSession();
      const input = validate(ReadNotifications, body);
      markRead(input.notificationIds, accountId);
      return ok({
        updatedIds: input.notificationIds,
        unreadCount: unreadCount(accountId),
      });
    })
    // [출처 3] 새 대화. 이전 대화를 지정하면 비활성화
    .on('POST', '/ai/conversations', ({ body }) => {
      const accountId = requireSession();
      const input = validate(ConversationCreate, body);
      if (input.previousConversationId)
        activeConversation(input.previousConversationId, accountId).active =
          false;
      const conversation: ConversationRecord = {
        id: newId(),
        ownerAccountId: accountId,
        createdAt: nowIso(),
        active: true,
        messages: [],
      };
      conversations.set(conversation.id, conversation);
      return ok(
        { id: conversation.id, createdAt: conversation.createdAt },
        201,
      );
    })
    .on('GET', '/ai/conversations/{conversationId}', ({ params }) => {
      const accountId = requireSession();
      const conversation = activeConversation(
        params.conversationId!,
        accountId,
      );
      return ok({
        conversation: {
          id: conversation.id,
          createdAt: conversation.createdAt,
        },
        messages: conversation.messages,
        requests: [...requests.values()]
          .filter((item) => item.conversationId === conversation.id)
          .map(publicRequest),
      });
    })
    // [출처 3, 4] 메시지 전송 → 202 + Location
    .on(
      'POST',
      '/ai/conversations/{conversationId}/messages',
      ({ params, body }) => {
        const accountId = requireSession();
        const conversation = activeConversation(
          params.conversationId!,
          accountId,
        );
        const input = validate(MessageCreate, body);
        const previous = conversation.messages.find(
          (item) => item.clientMessageId === input.clientMessageId,
        );
        if (previous) {
          if (previous.content !== input.content)
            conflict(
              'MESSAGE_ID_CONFLICT',
              '같은 메시지 ID에 다른 내용을 보냈어요.',
            );
          const replay = [...requests.values()].find(
            (item) => item.messageId === previous.id,
          )!;
          return ok(publicRequest(replay), 202, location(replay.id));
        }
        if (
          [...requests.values()].some(
            (item) =>
              item.conversationId === conversation.id &&
              item.status === 'pending',
          )
        )
          conflict(
            'REQUEST_ALREADY_RUNNING',
            '이전 요청이 아직 처리 중이에요.',
          );
        const createdAt = nowIso();
        const message: AiMessage = {
          id: newId(),
          clientMessageId: input.clientMessageId,
          role: 'user',
          content: input.content,
          sequence: conversation.messages.length + 1,
          createdAt,
        };
        conversation.messages.push(message);
        const request = {
          id: newId(),
          ownerAccountId: accountId,
          purpose: 'chat' as const,
          conversationId: conversation.id,
          messageId: message.id,
          teamId: null,
          applicationId: null,
          attempt: 1,
          status: 'pending' as AiRequest['status'],
          createdAt,
          updatedAt: createdAt,
          result: null,
          failure: null,
        };
        requests.set(request.id, request);
        const accepted = publicRequest(request);
        completeChat(request, input.content);
        return ok(accepted, 202, location(request.id));
      },
    )
    .on('GET', '/ai/requests/{requestId}', ({ params }) =>
      ok(publicRequest(ownedRequest(params.requestId!, requireSession()))),
    )
    // [출처 4] 실패한 현재 시도만 재시도
    .on('POST', '/ai/requests/{requestId}/retries', ({ params, body }) => {
      const request = ownedRequest(params.requestId!, requireSession());
      const input = validate(AiRetry, body);
      if (request.status !== 'failed' || !request.failure?.retryable)
        conflict('REQUEST_NOT_RETRYABLE', '재시도할 수 없는 요청이에요.');
      if (input.expectedAttempt !== request.attempt)
        conflict('ATTEMPT_CONFLICT', '현재 시도와 맞지 않아요.');
      Object.assign(request, {
        attempt: request.attempt + 1,
        status: 'pending',
        failure: null,
        updatedAt: nowIso(),
      });
      return ok(publicRequest(request), 202, location(request.id));
    })
    // [출처 4] 같은 시도가 이미 끝났으면 현재 상태 200, 다른 시도는 409
    .on('PUT', '/ai/requests/{requestId}/cancellation', ({ params, body }) => {
      const request = ownedRequest(params.requestId!, requireSession());
      const input = validate(AiCancel, body);
      if (input.expectedAttempt !== request.attempt)
        conflict('ATTEMPT_CONFLICT', '현재 시도와 맞지 않아요.');
      if (request.status === 'pending')
        Object.assign(request, { status: 'canceled', updatedAt: nowIso() });
      return ok(publicRequest(request));
    })
    // [출처 5] 기존 지원서 AI 검토
    .on('POST', '/applications/{applicationId}/ai-reviews', ({ params }) => {
      const accountId = requireSession();
      const application = receivedApplication(params.applicationId!, accountId);
      if (
        [...requests.values()].some(
          (item) =>
            item.applicationId === application.id && item.status === 'pending',
        )
      )
        conflict('REQUEST_ALREADY_RUNNING', '이전 검토가 아직 처리 중이에요.');
      const profile = profileOf(application.applicantAccountId)!;
      const now = nowIso();
      const request = {
        id: newId(),
        ownerAccountId: accountId,
        purpose: 'applicant_review' as const,
        conversationId: null,
        messageId: null,
        teamId: application.teamId,
        applicationId: application.id,
        attempt: 1,
        status: 'succeeded' as AiRequest['status'],
        createdAt: now,
        updatedAt: now,
        result: {
          kind: 'applicant_review' as const,
          applicationId: application.id,
          summary: `${profile.realName} 님의 최신 프로필과 지원 메시지를 바탕으로 정리했어요.`,
          evidence: [
            application.message ?? '지원 메시지가 없어요.',
            profile.introduction ?? '자기소개가 없어요.',
          ],
          profileVersions: [
            {
              accountId: profile.accountId,
              usedVersion: profile.version,
              currentVersion: profile.version,
            },
          ],
          isStale: false,
          isSelectionCandidate: ['submitted', 'reviewing'].includes(
            application.status,
          ),
          generatedAt: now,
        },
        failure: null,
      };
      requests.set(request.id, request);
      return ok(publicRequest(request), 202, location(request.id));
    })
    .on('GET', '/applications/{applicationId}/ai-review', ({ params }) => {
      const accountId = requireSession();
      const application = db().applications.find(
        (item) => item.id === params.applicationId,
      );
      const team = application && teamById(application.teamId);
      if (!application || team?.ownerAccountId !== accountId) notFound();
      const latest = [...requests.values()]
        .filter((item) => item.applicationId === application!.id)
        .at(-1);
      return ok(publicRequest(latest ?? notFound()));
    })
    // [출처 5] 자기 팀의 유효 지원자 중 새 선발 후보
    .on('POST', '/teams/{teamId}/applicant-recommendations', ({ params }) => {
      const accountId = requireSession();
      const team = teamById(params.teamId!) ?? notFound();
      if (team.ownerAccountId !== accountId) forbidden();
      const now = nowIso();
      const candidates = db()
        .applications.filter(
          (item) =>
            item.teamId === team.id &&
            ['submitted', 'reviewing'].includes(item.status),
        )
        .map((item) => {
          const profile = profileOf(item.applicantAccountId)!;
          return {
            applicationId: item.id,
            reason: `${profile.realName} 님의 희망 역할이 지원 역할과 맞아요.`,
            profileVersion: {
              accountId: profile.accountId,
              usedVersion: profile.version,
              currentVersion: profile.version,
            },
          };
        });
      const request = {
        id: newId(),
        ownerAccountId: accountId,
        purpose: 'applicant_recommendation' as const,
        conversationId: null,
        messageId: null,
        teamId: team.id,
        applicationId: null,
        attempt: 1,
        status: (candidates.length
          ? 'succeeded'
          : 'empty') as AiRequest['status'],
        createdAt: now,
        updatedAt: now,
        result: {
          kind: 'applicant_recommendation' as const,
          summary: candidates.length
            ? '현재 유효한 지원자 중 후보를 정리했어요.'
            : '지금 선발을 검토할 유효한 지원자가 없어요.',
          candidates,
          isStale: false,
          generatedAt: now,
        },
        failure: null,
      };
      requests.set(request.id, request);
      return ok(publicRequest(request), 202, location(request.id));
    });
}
