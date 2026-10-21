# AI와 알림 API

**상태: 설계 제안 · 미구현.** 현재 대화·지원자 검토·알림함의 요청과 응답을 정의합니다. 모든 경로는 `/api/v1` 기준이며 로그인이 필요합니다. 제품 정책은 [추천 명세](../specs/matching.md)와 [알림 명세](../specs/notifications.md)를 참조합니다.

| 찾는 내용 | 위치 |
| --- | --- |
| 경로·권한·HTTP 상태 | [현재 대화](#conversation-endpoints), [지원자 검토](#applicant-endpoints), [알림함](#notification-endpoints) |
| 요청·응답 필드 | [대화](#conversation-fields), [AI 실행 상태](#ai-request-fields), [추천 결과](#result-fields), [알림](#notification-fields) |
| 중복 전송·재시도·중단 | [실행 흐름](#request-lifecycle) |
| 공개 범위 변경·과거 근거 처리 | [현재 권한 재검증](#current-permissions) |

LLM 제공자·검색·프롬프트·실행 구조·저장소·보존 기간은 [추천 명세의 미정 사항](../specs/matching.md#open-questions)을 유지합니다. 아래 실행 리소스는 해당 내부 아키텍처를 결정하거나 과거 대화 저장을 약속하지 않습니다.

## 이 문서의 표기

- `Id`는 UUID 문자열, `Timestamp`는 UTC 시각 문자열, `Version`은 양의 십진 문자열, `CatalogCode`는 최대 64자의 코드입니다. [공통 계약](conventions.md)의 표현·검증·오류 형식을 적용합니다.
- 객체의 **아래에 기재된 필드는 모두 필수**입니다. 생략할 수 있는 요청 필드만 별도로 `선택`이라고 표시합니다. `null` 허용은 생략 허용과 다르며, 목록의 빈 값은 `[]`입니다. 선언하지 않은 필드는 허용하지 않습니다.
- `양의 안전 정수`는 `1~9007199254740991`, `음이 아닌 안전 정수`는 `0~9007199254740991`인 JSON 정수입니다. 시도·순서·집계의 전송 표현 한계이며 서비스 이용 횟수 상한이 아닙니다.
- 모든 API는 공통 실패 `401`, `500`, `503`을 제공합니다. 아래 표의 **추가 실패**는 이 공통 실패에 더하는 HTTP 상태입니다. `422`는 경로·query·본문 검증 실패, `429`는 요청 제한이며 구체 제한 수치는 미정입니다.
- 경로의 `{conversationId}`, `{requestId}`, `{applicationId}`, `{teamId}`, `{notificationId}`는 모두 필수 `Id`입니다. 본문을 받는 API는 표의 JSON 객체가 필수이며, `본문 없음`은 요청 DTO가 없다는 뜻입니다.

<a id="conversation-endpoints"></a>

## 현재 대화 API

| 메서드·경로 | 요청 | 성공 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /ai/conversations` | [ConversationCreate](#conversation-fields) | 201 `Conversation` | 404, 409, 422, 429 |
| `GET /ai/conversations/{conversationId}` | 본문 없음 | 200 `ConversationView` | 404, 422 |
| `POST /ai/conversations/{conversationId}/messages` | [MessageCreate](#conversation-fields) | 202 `AiRequest`, `Location` | 404, 409, 422, 429 |
| `GET /ai/requests/{requestId}` | 본문 없음 | 200 `AiRequest` | 404, 422 |
| `POST /ai/requests/{requestId}/retries` | [AiRetry](#ai-control-fields) | 202 `AiRequest`, `Location` | 404, 409, 422, 429 |
| `PUT /ai/requests/{requestId}/cancellation` | [AiCancel](#ai-control-fields) | 200 `AiRequest` | 404, 409, 422 |

`202`는 답변 완성이 아니라 요청 접수입니다. 이 문서의 모든 202 응답은 `Location: /api/v1/ai/requests/{id}`를 제공하며 `id`는 반환된 `AiRequest.id`입니다. 해당 상대 경로를 조회하는 polling 계약을 제안합니다. polling 간격·스트리밍·백그라운드 실행 방식은 미정입니다. 화면이 비활성·로그아웃 상태이면 반복 조회를 멈추고, 429·503에서 무제한 재시도하지 않습니다.

### 권한과 오류 조건

| 대상 | 검증과 실패 |
| --- | --- |
| 새 대화 | 현재 로그인 주체에게 생성. `previousConversationId`를 지정하면 해당 인증 맥락의 현재 대화인지 검증. 다른 소유자·종료된 맥락은 404, 교체 충돌은 409. 구체 오류 코드·중복 생성 처리 방식은 후속 결정 |
| 현재 대화·메시지 | 현재 로그인 주체가 열어 둔 대화만 허용. 교체·로그아웃·만료된 대화는 ID를 알아도 404 |
| AI 요청 조회·재시도·중단 | 요청 소유자와 현재 이용 맥락이 모두 일치해야 함. 일반 대화는 현재 대화 소유권, 지원자 검토·추천은 현재 팀장·지원 관계를 재확인. 불일치·소멸은 404 |
| 같은 메시지 ID·다른 본문 | 409 `MESSAGE_ID_CONFLICT` |
| 다른 요청이 진행 중 | 409 `REQUEST_ALREADY_RUNNING` |
| 재시도할 수 없는 요청 | 409 `REQUEST_NOT_RETRYABLE` |
| 현재 시도와 불일치 | 409 `ATTEMPT_CONFLICT`. 같은 실패 시도의 겹친 재시도는 아래 중복 처리 규칙 적용 |

404의 공통 코드는 `RESOURCE_NOT_FOUND`입니다. 과거 대화 목록·검색·재열기 endpoint는 제공하지 않습니다. 새로고침·재로그인 후 복원은 [MATCH-13](../specs/matching.md#open-questions)에서 결정합니다.

<a id="conversation-fields"></a>

## 대화 요청·응답 필드

### ConversationCreate · Conversation

| 객체 | 필드 | 타입·필수 여부 | 의미 |
| --- | --- | --- | --- |
| `ConversationCreate` | `previousConversationId` | `Id` 또는 `null`, **선택** | 교체할 현재 대화. 생략·`null`은 첫 대화. 첫 대화도 빈 JSON 객체 `{}`를 전송 |
| `Conversation` | `id` | `Id` | 현재 대화 ID |
| `Conversation` | `createdAt` | `Timestamp` | 생성 시각 |

대화 응답 유실 후 생성 요청의 멱등성 및 교체 충돌의 구체 오류 코드는 인증·실행 맥락과 함께 후속 설계합니다. 운영에 제공하기 전에 성공·실패 계약을 완성하며, 임의 코드나 500으로 미정 동작을 대신하지 않습니다. `Conversation.id`가 있다는 사실이 서버 영구 저장이나 과거 기록 복원을 뜻하지 않습니다.

### MessageCreate · AiMessage

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `MessageCreate` | `clientMessageId` | `Id` | 새 메시지마다 생성하는 ID. 같은 전송의 재시도에는 재사용 |
| `MessageCreate` | `content` | 문자열 | 1~1,000자. 공백만 있으면 422. 초과 입력을 잘라 전송하지 않음 |
| `AiMessage` | `id` | `Id` | 서버 메시지 ID |
| `AiMessage` | `clientMessageId` | `Id` 또는 `null` | 사용자 전송 ID, 클라이언트가 전송한 메시지가 아니면 `null` |
| `AiMessage` | `role` | `user` 또는 `assistant` | 발화 주체 |
| `AiMessage` | `content` | 문자열 | 현재 권한을 적용한 표시 본문 |
| `AiMessage` | `sequence` | 양의 안전 정수 | 현재 대화 내 메시지 순서 |
| `AiMessage` | `createdAt` | `Timestamp` | 생성 시각 |

사용자 본문에는 1,000자 정책을 적용합니다. 일반 Unicode 계수 단위는 [공통 미정 계약](conventions.md#deferred)을 따르며, assistant 본문의 제품 길이 상한을 임의로 추가하지 않습니다.

### ConversationView

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `conversation` | `Conversation` | 현재 대화 |
| `messages` | `AiMessage[]` | 현재 대화의 메시지. `sequence`로 순서를 구분 |
| `requests` | `AiRequest[]` | 현재 대화의 실행 요청·상태 |

본문과 결과는 응답할 때 현재 권한으로 재검사합니다. `messages`와 `requests`가 반환되는 범위는 현재 인증 맥락에서 열린 대화에 한정됩니다.

<a id="request-lifecycle"></a>

## 전송·재시도·중단·새 대화

| 식별자 | 구분하는 것 |
| --- | --- |
| `conversationId` | 새 대화 전후의 화면 맥락 |
| `clientMessageId` | 같은 사용자 메시지의 전송 재시도 |
| `requestId` | AI 처리 요청 |
| `attempt` | 같은 요청의 실패 재시도 회차 |

1. **전송:** 새 `clientMessageId`를 생성합니다. 네트워크 실패로 같은 ID·같은 본문을 재전송하면 동일 사용자 메시지와 요청을 반환합니다. 같은 ID의 다른 본문은 409입니다.
2. **진행 중:** 한 대화에서 진행 요청 하나를 허용하는 전송 설계입니다. 새 메시지는 현재 요청이 끝난 뒤 보내거나 먼저 중단합니다. 대화 횟수의 제품 상한을 추가하지 않습니다.
3. **실패 재시도:** 현재 상태가 `failed`이고 `failure.retryable=true`인 요청에 `expectedAttempt`를 보냅니다. 같은 실패 시도의 겹친 재시도는 하나의 다음 `attempt`로 수렴하고 사용자 메시지를 새로 만들지 않습니다. 더 과거 시도는 409입니다. 성공한 검토를 다시 요청할 때는 검토 생성 endpoint로 새 요청을 만듭니다.
4. **중단:** 현재 `attempt`가 일치하고 `pending`이면 `canceled`로 바꿉니다. 같은 시도가 이미 종료되었다면 현재 상태를 200으로 반환합니다. 다른 시도는 409이며, 이전 중단 요청으로 새 시도를 취소하지 않습니다.
5. **새 대화:** 기존 대화와 진행 요청을 비활성화하고 새 대화 ID를 반환합니다. 뒤늦은 이전 대화·시도의 응답은 현재 화면에 반영하지 않습니다.

중단은 결과 채택을 멈추는 계약입니다. 외부 제공자의 계산·로그가 즉시 삭제되었다는 보장은 하지 않습니다.

<a id="ai-control-fields"></a>

### AiRetry · AiCancel

| 객체 | 필드 | 타입 | 의미 |
| --- | --- | --- | --- |
| `AiRetry` | `expectedAttempt` | 양의 안전 정수 | 재시도할 실패 회차 |
| `AiCancel` | `expectedAttempt` | 양의 안전 정수 | 중단할 현재 회차 |

<a id="ai-request-fields"></a>

## AI 실행 상태와 필드

`AiPurpose`는 `chat`, `applicant_review`, `applicant_recommendation` 중 하나입니다. `AiRequestStatus`는 `pending`, `succeeded`, `empty`, `failed`, `canceled` 중 하나입니다.

### AiRequest

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | `Id` | 처리 요청 ID |
| `purpose` | `AiPurpose` | 요청 목적 |
| `conversationId` | `Id` 또는 `null` | 일반 대화 ID. 아래 목적별 조건 적용 |
| `messageId` | `Id` 또는 `null` | 요청을 시작한 사용자 메시지 ID |
| `teamId` | `Id` 또는 `null` | 검토·후보 추천 대상 팀 |
| `applicationId` | `Id` 또는 `null` | 개별 검토 대상 지원 |
| `attempt` | 양의 안전 정수 | 처리 시도 회차 |
| `status` | `AiRequestStatus` | 처리 상태 |
| `createdAt` | `Timestamp` | 요청 생성 시각 |
| `updatedAt` | `Timestamp` | 현재 상태 갱신 시각 |
| `result` | `AiResult` 또는 `null` | 현재 권한을 적용한 결과 |
| `failure` | `AiFailure` 또는 `null` | 사용자에게 제공할 수 있는 실패 정보 |

**목적별 참조 조건과 상태별 결과 조건을 동시에 만족해야 합니다.** 아래 `null`은 필드를 생략하라는 의미가 아닙니다.

| `purpose` | 값이 있어야 하는 참조 | 반드시 `null`인 참조 | `result`가 있으면 `kind` |
| --- | --- | --- | --- |
| `chat` | `conversationId`, `messageId` | `teamId`, `applicationId` | `chat` |
| `applicant_review` | `teamId`, `applicationId` | `conversationId`, `messageId` | `applicant_review` |
| `applicant_recommendation` | `teamId` | `conversationId`, `messageId`, `applicationId` | `applicant_recommendation` |

| `status` | `result` | `failure` | 화면 의미 |
| --- | --- | --- | --- |
| `pending` | `null` | `null` | 응답 준비 중 |
| `succeeded` | 목적에 맞는 `AiResult` 필수 | `null` | 처리 성공 |
| `empty` | 목적에 맞는 `AiResult` 필수 | `null` | 정상 처리했으나 결과 없음. 안내를 제공하고 후보를 만들지 않음 |
| `failed` | `null` | `AiFailure` 필수 | 처리 실패. 재시도 가능 여부 확인 |
| `canceled` | `null` | `null` | 해당 시도 중단 |

### AiFailure

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `code` | `temporary_failure`, `invalid_output`, `context_changed` 중 하나 | 일시 실패, 유효하지 않은 출력, 이용 맥락 변경 |
| `message` | 문자열 | 사용자에게 보여 줄 설명 |
| `retryable` | 불리언 | 현재 요청을 실패 재시도 endpoint로 재시도할 수 있는지 |

`AiFailure`는 200·202 응답 안의 **AI 처리 상태**이며 HTTP 실패의 공통 `error` 객체와 다릅니다. 모델 원문·프롬프트·스택·제공자 비밀값을 포함하지 않습니다.

<a id="applicant-endpoints"></a>

## 팀장 지원자 검토 API

| 메서드·경로 | 권한·요청 | 성공 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /applications/{applicationId}/ai-reviews` | 해당 지원을 받은 현재 팀장. 본문 없음 | 202 `AiRequest`, `Location` | 403, 404, 409, 422, 429 |
| `GET /applications/{applicationId}/ai-review` | 해당 지원을 받은 현재 팀장. 본문 없음 | 200 `AiRequest` | 404, 422 |
| `POST /teams/{teamId}/applicant-recommendations` | 해당 팀의 현재 팀장. 본문 없음 | 202 `AiRequest`, `Location` | 403, 404, 409, 422, 429 |

서버가 현재 자료를 조회합니다. 클라이언트로부터 임의 프로필 전문이나 다른 지원자의 ID 목록을 받지 않습니다. 같은 대상에 진행 요청이 있으면 409 `REQUEST_ALREADY_RUNNING`입니다. 리소스가 없거나 존재를 숨겨야 하는 관계이면 404, 확인 가능한 리소스의 행동 권한이 없으면 403 `FORBIDDEN`입니다. 현재 검토 조회는 결과가 없거나 권한이 없으면 404입니다.

기존 지원서 검토는 종결 상태·지원 후 비공개·팀 모집 종료·팀 또는 공고 기한 경과·정원 충족만으로 차단하지 않습니다. 팀의 후보 요청도 마감·정원 충족만으로 거부하지 않으며, 새 후보에는 자기 팀의 현재 유효한 `submitted`·`reviewing` 중 같은 공모전의 확정 소속이 없는 지원자만 포함합니다. `selected`·`rejected`·`canceled`·`discarded`는 새 후보에서 제외합니다. 상세 정책은 [기존 지원자 검토](../specs/matching.md#applicant-review)를 참조합니다.

AI 검토·후보 요청·결과 조회는 지원 상태를 변경하지 않습니다. `reviewing` 진입은 [팀장의 명시적 검토 시작 API](contests-teams.md#endpoints)에서만 실행합니다. 후보 표시는 실제 선발 허가가 아니며, 선발 실행 시 [공고 접수 기한·여석·소속·권한](../specs/team-recruitment.md#selection-window)을 다시 검사합니다. 공고 접수가 끝난 뒤에도 AI 검토·후보 요청은 가능하지만 실제 선발은 불가합니다.

<a id="result-fields"></a>

## 추천 결과 필드

`AiResult`는 아래 세 객체 중 **정확히 하나**입니다. `kind`로 응답 종류를 구분하며 `AiRequest.purpose`와 같아야 합니다.

| `kind` | 응답 객체 | 내용 |
| --- | --- | --- |
| `chat` | `ChatResult` | 답변과 일반 추천 카드 |
| `applicant_review` | `ApplicantReviewResult` | 기존 지원 한 건의 검토 |
| `applicant_recommendation` | `ApplicantRecommendationResult` | 자기 팀의 새 선발 후보 |

### ResourceCard · ChatResult

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `ResourceCard` | `kind` | `contest`, `team`, `person` 중 하나 | 연결할 실제 리소스 종류 |
| `ResourceCard` | `resourceId` | `Id` | 실제 리소스 ID. 사람은 계정 ID |
| `ResourceCard` | `title` | 문자열 | 현재 권한으로 제공 가능한 제목·표시명 |
| `ResourceCard` | `reason` | 문자열 | 확인 가능한 정보에 근거한 추천 이유 |
| `ResourceCard` | `fieldCodes` | `CatalogCode[]` | 분야 코드 |
| `ResourceCard` | `roleCodes` | `CatalogCode[]` | 역할 코드 |
| `ResourceCard` | `isDemo` | 불리언 | **서버 판정** 시연 데이터 여부. `kind`에 대응하는 고정 UUID 시드 목록에 `resourceId`가 포함되는지 확인. 사람은 계정 ID 기준 |
| `ChatResult` | `kind` | 고정값 `chat` | 응답 종류 |
| `ChatResult` | `answer` | 문자열 | 표시 답변 |
| `ChatResult` | `cards` | `ResourceCard[]` | 종류 합계 최대 3개. 결과가 없으면 `[]` |
| `ChatResult` | `generatedAt` | `Timestamp` | 결과 생성 시각 |
| `ChatResult` | `referencesChanged` | 불리언 | 현재 권한·상태 변경으로 이전 답변을 정보 변경 안내로 대체했는지 |

모델이 만든 URL을 그대로 이동 경로로 쓰지 않습니다. 클라이언트가 `kind`·`resourceId`를 제품의 내부 상세 경로에 연결하며, 응답에 `/design-preview` 경로를 넣지 않습니다. `isDemo`도 이름·모델 출력·화면의 추측으로 결정하지 않습니다. 표시 기준은 [시연 데이터 안내](../specs/sprint-1.md#demo-data-scope)를 따릅니다.

### ProfileVersion · ApplicantReviewResult

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `ProfileVersion` | `accountId` | `Id` | 검토한 계정 |
| `ProfileVersion` | `usedVersion` | `Version` | 결과에 사용한 프로필 버전 |
| `ProfileVersion` | `currentVersion` | `Version` | 조회 시점의 프로필 버전 |
| `ApplicantReviewResult` | `kind` | 고정값 `applicant_review` | 응답 종류 |
| `ApplicantReviewResult` | `applicationId` | `Id` | 검토 대상 지원 |
| `ApplicantReviewResult` | `summary` | 문자열 | 검토 요약 |
| `ApplicantReviewResult` | `evidence` | 문자열 배열 | 확인 가능한 정보에 따른 근거 |
| `ApplicantReviewResult` | `profileVersions` | `ProfileVersion[]` | **정확히 1개**. 해당 지원자의 사용·현재 버전 |
| `ApplicantReviewResult` | `isStale` | 불리언 | 사용한 버전과 현재 버전이 다른지 |
| `ApplicantReviewResult` | `isSelectionCandidate` | 불리언 | 현재 지원 상태·소속 기준에서 새 선발 후보인지. 선발 실행 허가를 대신하지 않음 |
| `ApplicantReviewResult` | `generatedAt` | `Timestamp` | 결과 생성 시각 |

### ApplicantRecommendation · ApplicantRecommendationResult

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `ApplicantRecommendation` | `applicationId` | `Id` | 자기 팀의 실제 유효 지원 ID |
| `ApplicantRecommendation` | `reason` | 문자열 | 추천 근거 |
| `ApplicantRecommendation` | `profileVersion` | `ProfileVersion` | 사용·현재 프로필 버전 |
| `ApplicantRecommendationResult` | `kind` | 고정값 `applicant_recommendation` | 응답 종류 |
| `ApplicantRecommendationResult` | `summary` | 문자열 | 추천 요약 |
| `ApplicantRecommendationResult` | `candidates` | `ApplicantRecommendation[]` | 현재 유효한 자기 팀 지원자. 없으면 `[]` |
| `ApplicantRecommendationResult` | `isStale` | 불리언 | 사용한 프로필과 현재 버전이 달라 과거 근거인지 |
| `ApplicantRecommendationResult` | `generatedAt` | `Timestamp` | 결과 생성 시각 |

일반 대화의 카드 3개 제한을 지원자 검토 인원의 별도 상한으로 확대하지 않습니다. 지원자 표시 정보는 [지원자 조회 응답](contests-teams.md)에서 가져오며 이 결과에 프로필 전문을 중복하지 않습니다.

<a id="current-permissions"></a>

## 현재 권한과 과거 결과 재검증

카드·답변·추천 이유를 반환할 때 실제 대상 존재·현재 공개 범위·모집 조건을 다시 확인합니다. 일반 사람 추천의 공개 철회와 지원받은 팀장의 검토 예외는 [공개 범위 정책](../specs/matching.md#result-display)을 따릅니다.

| 상황 | 응답 처리 |
| --- | --- |
| 이전 일반 답변에 현재 열람할 수 없는 정보가 포함됨 | 카드만 제거하고 본문·이유에 개인정보를 남기지 않음. 안전하게 제공할 수 있는지 검증할 수 없으면 **답변 전체를 정보 변경 안내로 대체**, `cards=[]`, `referencesChanged=true` |
| 일반 팀 추천의 신규 지원 대상 재검증 | 현재 모집 조건과 같은 공모전의 무소속 여부, 해당 팀의 미선발 이력 전체를 확인. 이미 소속되었거나 같은 팀 미선발 이력이 있으면 신규 지원 대상에서 제외 |
| 지원자 프로필이 결과 생성 이후 변경됨 | `usedVersion`·`currentVersion`을 구분하고 `isStale=true`로 표시. 현재 정보에 근거한 것처럼 합치지 않고 재요청 안내 |
| 후보 지원이 선발·미선발·취소·폐기로 바뀜 | 새 후보에서 제외하고 후보와 본문 근거를 함께 재검증. 기존 지원서 검토 열람 관계와 구분 |
| 팀 모집 종료·팀 또는 공고 기한 경과·정원 충족 | 기존 지원자 검토·팀의 후보 요청 자체를 거부하지 않음. 유효 지원·현재 소속으로 후보를 재검증하며 실제 선발 가능 여부는 선발 API에서 검사 |
| 팀장·지원 관계 또는 현재 대화 맥락 소멸 | 해당 요청·결과를 404 처리. ID 보유·과거 열람으로 접근 권한을 복구하지 않음 |
| 오래 열린 화면에서 결과 복사 | 현재 권한이 적용된 결과를 다시 조회한 뒤 복사. 조회 실패를 오래된 데이터의 복사 성공으로 처리하지 않음 |

버전 기록은 지원 당시 프로필 사본에 고정하거나 프로필 전문을 영구 저장하라는 요구가 아닙니다. 조회·검증 계약이 모든 프로필 항목의 모델 전송을 허용하는 것도 아닙니다.

<a id="notification-endpoints"></a>

## 서비스 알림함 API

| 메서드·경로 | 요청 | 성공 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /me/notifications` | `page`, `pageSize`, `unreadOnly` query | 200 `NotificationPage` | 422 |
| `GET /me/notifications/unread-count` | 없음 | 200 `UnreadCount` | 없음 |
| `PUT /me/notifications/{notificationId}/read` | 본문 없음 | 200 `Notification` | 404, 422 |
| `PUT /me/notifications/read` | `ReadNotifications` | 200 `ReadNotificationsResult` | 404, 422 |

모든 알림 경로는 인증 주체 **본인**만 대상으로 합니다. query·본문에 다른 수신자 ID를 받지 않습니다. 다른 사람의 알림이나 없는 ID는 404 `RESOURCE_NOT_FOUND`입니다.

| 목록 query | 타입·기본값 | 계약 |
| --- | --- | --- |
| `page` | 양의 정수, 기본 1 | [공통 페이지 규칙](conventions.md) 적용 |
| `pageSize` | 1~100 정수, 기본 20 | `NotificationPage`의 `items`·`pagination`에 적용 |
| `unreadOnly` | 불리언, 기본 `false` | `true`면 미읽음만 반환 |

정렬은 `occurredAt DESC, id DESC`입니다. `total`은 현재 필터와 권한을 적용한 목록 집계이며, `UnreadCount.unreadCount`는 본인의 **전체 미읽음 수**입니다. 목록 열기만으로 읽음 처리하지 않습니다.

<a id="notification-fields"></a>

## 알림 요청·응답 필드

### NotificationPage — 목록과 전체 미읽음 수

`NotificationPage`는 [공통 `Page<Notification>`](conventions.md#pagination)의 전체 필드와 아래 `unreadCount`를 **같은 객체에** 포함합니다. 세 필드 모두 필수이며 `null`을 허용하지 않습니다.

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `items` | `Notification[]` | 현재 목록 필터에 맞는 본인 알림 |
| `pagination` | `PageMeta` | 같은 권한·필터·읽기 시점의 목록 집계 |
| `unreadCount` | 음이 아닌 안전 정수 | 목록 필터와 무관한 본인의 **전체 미읽음 수** |

`unreadOnly`·페이지 크기·현재 페이지가 달라져도 `unreadCount`는 전체 미읽음을 기준으로 합니다. 별도의 `UnreadCount` 조회 없이 목록 응답으로 알림 배지를 함께 갱신할 수 있습니다.

### Notification

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | `Id` | 알림 ID |
| `kind` | `application_status_changed` 또는 `new_application` | 지원 상태 변경 또는 팀장이 받는 신규 지원 |
| `applicationId` | `Id` | 실제 지원 건 |
| `teamId` | `Id` | 해당 팀 |
| `eventStatus` | [ApplicationStatus](contests-teams.md) | **사건 발생 당시** 지원 상태. 현재 상태와 구분 |
| `occurredAt` | `Timestamp` | 실제 사건 발생 시각 |
| `readAt` | `Timestamp` 또는 `null` | 최초 읽음 시각. 미읽음은 `null` |
| `title` | 문자열 | 현재 권한으로 구성한 제목 |
| `body` | 문자열 | 현재 권한으로 구성한 본문 |

### UnreadCount · ReadNotifications · ReadNotificationsResult

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `UnreadCount` | `unreadCount` | 음이 아닌 안전 정수 | 본인의 전체 미읽음 수 |
| `ReadNotifications` | `notificationIds` | `Id[]` | **최소 1개, 중복 없음**. 현재 사용자에게 제공되어 읽음 대상으로 선택한 ID |
| `ReadNotificationsResult` | `updatedIds` | `Id[]` | 성공한 본인 ID. 이미 읽은 ID도 포함 |
| `ReadNotificationsResult` | `unreadCount` | 음이 아닌 안전 정수 | 처리 후 본인의 전체 미읽음 수 |

모두 읽음은 현재 사용자에게 **이미 제공된 ID의 합집합**을 전송합니다. 그 사이 도착했지만 아직 제공하지 않은 알림은 변경하지 않습니다. 이미 읽은 항목은 최초 `readAt`을 유지하고, 하나라도 타인·없는 ID가 있으면 404로 **전체 변경 없이 실패**합니다.

상태 변경과 알림 생성은 [알림 생성 정책](../specs/notifications.md#generation-policy), 저장·중복 방지는 [알림 테이블](../database/notifications.md)을 참조합니다. 명시적 검토 시작·미선발과 본인 팀 생성에 따른 폐기는 기존 `application_status_changed` 계열로 전달하며 새 `kind`를 추가하지 않습니다. 실제 변경이 없는 조회·재요청이나 모집 종료·기한 경과만으로 상태 변경 알림을 만들지 않습니다. 읽음 성공 후 목적지로 이동하며, 목적지에서 현재 권한·존재 여부를 다시 확인합니다. 알림의 제목·본문도 비공개 프로필을 우회 노출하지 않습니다.

## 정합성 확인 기준

구현 시 다음 조건을 요청·응답 검증과 계약 테스트에서 확인합니다. 제품 정책의 세부 완료 조건은 각 기능 명세가 원본입니다.

- 이 문서의 13개 API에 선언한 요청·응답·성공/실패 상태를 제공하고, 별도 수동 YAML을 병행 관리하지 않습니다.
- `AiRequest`의 필수 필드, 목적별 참조, 상태별 `result`·`failure` 조합을 함께 검증합니다. `failed`인데 실패 정보가 없거나 `chat`에 지원자 검토 결과가 들어가는 응답을 허용하지 않습니다.
- 같은 메시지 재전송·겹친 실패 재시도는 메시지를 중복 생성하지 않으며, 오래된 시도의 중단이 새 시도를 취소하지 않습니다.
- 일반 추천 카드 합계 3개와 서버의 `isDemo`를 지키며, 현재 권한이 없는 정보를 본문·카드·복사 결과로 반환하지 않습니다.
- 알림 ID 집합의 읽음은 전부 성공하거나 전부 실패하며, 이미 읽은 시각과 아직 제공하지 않은 알림을 변경하지 않습니다.

## 미정·범위 밖 항목

AI 과거 대화 검색·자동 지원·자동 선발·포트폴리오 수집, 사용자 간 채팅, 마감 알림·푸시·이메일은 추가하지 않습니다. AI 서버 영속화·로그 보존·새로고침 복원과 알림 보존·실시간 전달은 담당 기능 명세의 미정 범위를 유지합니다. 인증에는 [서버 세션·쿠키 계약](conventions.md#session-auth)을 적용하며, CSRF 등 남은 전송 세부는 해당 계약의 미정 항목을 따릅니다.
