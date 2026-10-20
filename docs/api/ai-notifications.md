# AI와 알림 API

**상태: 설계 제안.** 외부 요청·응답과 권한 검사의 접점을 정의합니다. LLM 제공자·검색·프롬프트·실행 구조·저장소·보존 기간은 [추천 명세의 미정 사항](../specs/matching.md#open-questions)을 유지합니다. 아래 모든 경로는 `/api/v1` 기준이며 로그인 필요입니다.

## 현재 대화의 생명주기

| 메서드·경로 | 요청 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `POST /ai/conversations` | 선택 `previousConversationId` | 201 `Conversation` | 404 다른/종료된 맥락, 409 충돌 |
| `GET /ai/conversations/{conversationId}` | 현재 대화 ID | 200 `ConversationView` | 404 현재 열람 대상 아님 |
| `POST /ai/conversations/{conversationId}/messages` | `clientMessageId`, `content` | 202 `AiRequest`, `Location` | 409 메시지 ID 충돌·다른 요청 진행 중, 422 입력 |
| `GET /ai/requests/{requestId}` | 요청 ID | 200 `AiRequest` | 404 소유·맥락·관계 불일치 |
| `POST /ai/requests/{requestId}/retries` | `expectedAttempt` | 202 `AiRequest`, `Location` | 409 재시도 불가·시도 충돌 |
| `PUT /ai/requests/{requestId}/cancellation` | `expectedAttempt` | 200 현재 `AiRequest` | 409 다른 시도 |

현재 열린 대화를 서버 실행 리소스로 구분하는 안입니다. 조회는 **현재 로그인 맥락에서 열어 둔 대화**만 허용합니다. 대화 ID를 알고 있더라도 교체·로그아웃·만료된 대화를 다시 열지 못합니다. 서버에 기록을 영구 저장하거나 새로고침·재로그인 후 복원한다는 계약이 아닙니다. 과거 대화 목록·검색 endpoint는 없습니다.

권한과 새 대화의 UI 동작은 [자연어 추천 명세](../specs/matching.md)에 연결합니다. 클라이언트는 다음 식별자를 구분합니다.

| 식별자 | 구분하는 것 |
| --- | --- |
| `conversationId` | 새 대화 전후의 화면 맥락 |
| `clientMessageId` | 같은 사용자 메시지의 전송 재시도 |
| `requestId` | AI 처리 요청 |
| `attempt` | 같은 요청의 실패 재시도 회차 |

`202`는 답변 완성이 아니라 요청 접수입니다. `Location`의 조회 경로로 `pending`, `succeeded`, `empty`, `failed`, `canceled`를 확인하는 polling 계약을 제안합니다. polling 간격·스트리밍·백그라운드 실행 방식은 아직 선택하지 않습니다. 클라이언트는 화면이 비활성·로그아웃 상태이면 반복 조회를 멈추고, 429·503에서 무제한 재시도하지 않습니다.

### 전송·재시도·새 대화

1. 메시지 전송 시 새 `clientMessageId`를 생성합니다. 네트워크 실패로 재전송할 때 같은 ID·본문을 사용하면 동일 사용자 메시지와 요청을 반환합니다. 같은 ID의 다른 본문은 409입니다.
2. 한 대화에서 진행 중인 요청을 하나로 제한하는 전송 설계를 제안합니다. 새 메시지는 현재 요청이 끝난 뒤 보내거나 먼저 중단합니다. 대화 횟수의 제품 상한을 추가하는 결정은 아닙니다.
3. 실패한 요청의 재시도는 `expectedAttempt`를 보내고 사용자 메시지를 새로 만들지 않습니다. 서로 겹친 같은 시도의 재시도는 하나의 다음 시도로 수렴합니다.
4. 새 대화는 기존 `conversationId`를 교체하고 진행 중 요청을 비활성화합니다. 뒤늦은 이전 응답은 ID·시도가 현재 화면과 일치하지 않으므로 반영하지 않습니다.
5. 중단은 결과 채택을 멈추는 계약입니다. 외부 제공자의 계산·로그가 즉시 삭제됐다는 보장은 하지 않습니다.

## 결과와 현재 권한

`AiRequest.result`는 종류별 schema로 구분합니다.

| 결과 schema | 제공 정보 | 재검증 |
| --- | --- | --- |
| `ChatResult` | 답변, 합계 최대 3개의 공고·팀·공개 사람 카드 | 실제 대상 존재·현재 공개·모집 조건. 변경된 참조는 답변·근거까지 재검사 |
| `ApplicantReviewResult` | 실제 지원의 검토 내용, 사용한 프로필 버전과 현재 버전, `isStale`, 현재 후보 여부 | 현재 받은 팀장 권한·지원 관계 |
| `ApplicantRecommendationResult` | 새 선발 후보의 실제 지원 ID·이유·사용 프로필 버전 | 현재 유효한 지원과 소속을 다시 확인 |

카드는 `kind`와 실제 `resourceId`를 제공합니다. 모델이 만든 URL을 그대로 이동 경로로 쓰지 않고 클라이언트가 제품의 내부 상세 경로에 연결합니다. API 응답에 공식 디자인의 `/design-preview` 경로를 넣지 않습니다.

정보가 바뀐 결과를 보여 줄 때는 카드만 숨기고 답변 본문에 이전 개인정보를 남기지 않습니다. 현재 열람할 수 없는 데이터가 답변·이유에 섞였는지 검증할 수 없으면 해당 답변 전체를 정보 변경 안내로 대체하고 카드를 비웁니다. `referencesChanged=true`로 이 대체를 구분합니다. 이는 일반 사람 추천의 [공개 철회 정책](../specs/matching.md#result-display)을 충족하기 위한 외부 계약이며, 구체적인 내부 응답 검증 기술을 선택한 것은 아닙니다.

결과 클릭·복사도 현재 권한이 적용된 응답을 사용합니다. 오래 열린 화면은 현재 결과를 다시 조회한 뒤 복사하고, 실패하면 오래된 데이터를 복사 성공으로 처리하지 않는 방향을 제안합니다. 결과 ID가 있다는 사실이 접근 권한을 복구하지 않습니다.

## 팀장 지원자 검토

| 메서드·경로 | 범위 | 성공 |
| --- | --- | --- |
| `POST /applications/{applicationId}/ai-reviews` | 기존 지원서의 현재 정보로 검토·재요청 | 202 `AiRequest`, `Location` |
| `GET /applications/{applicationId}/ai-review` | 현재 이용 맥락에서 제공 가능한 해당 검토 결과 | 200 `AiRequest`; 결과 없으면 404 |
| `POST /teams/{teamId}/applicant-recommendations` | 해당 팀의 새 선발 후보 요청 | 202 `AiRequest`, `Location` |

세 경로는 현재 팀장·지원 관계를 검증합니다. 본문 없이 서버가 현재 자료를 조회하므로, 클라이언트가 임의 프로필 전문·다른 지원자의 ID 목록을 모델 입력으로 주입하지 않습니다. 같은 대상에 진행 요청이 있으면 409 `REQUEST_ALREADY_RUNNING`으로 구분합니다.

기존 지원서의 검토와 새 선발 후보는 서로 다른 결과입니다. 기존 지원서의 종결 상태·모집 종료가 AI 검토 권한을 없애지는 않지만 후보 여부는 현재 상태로 다시 계산합니다. 정확한 허용 범위는 [기존 지원자 검토 정책](../specs/matching.md#applicant-review)에 연결합니다. 일반 대화의 카드 3개 제한을 지원자 검토 인원의 별도 상한으로 확대하지 않습니다.

`profileVersions[].usedVersion`은 결과가 사용한 값, `currentVersion`은 조회 시점의 프로필 버전입니다. 다르면 `isStale=true`이며 과거 근거임을 표시하고 새 검토를 요청합니다. 지원 당시 프로필 사본으로 고정하거나 이전 결과를 최신 정보인 것처럼 합치지 않습니다. 이 버전 기록은 모델에 모든 프로필 항목을 전송하거나 프로필 전문을 영구 저장하라는 요구가 아닙니다.

## 서비스 알림함

| 메서드·경로 | 요청 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `GET /me/notifications` | `unreadOnly`, 페이지 | 200 `NotificationPage` | 401 인증, 422 조건 |
| `GET /me/notifications/unread-count` | 없음 | 200 `unreadCount` | 401 인증 |
| `PUT /me/notifications/{notificationId}/read` | 본문 없음 | 200 `Notification` | 404 다른 사용자·없음 |
| `PUT /me/notifications/read` | 제공받은 `notificationIds` | 200 `updatedIds`, `unreadCount` | 타인·없는 ID 포함 시 404·전체 변경 없음 |

정렬은 `occurredAt DESC, id DESC`입니다. `Notification.eventStatus`는 알림 발생 당시 상태이며 현재 지원 상태는 목적지 API에서 확인합니다. 목록 열기만으로 읽음 처리하지 않습니다. 개인 데이터·미읽음 수는 인증 주체에서 결정하며 query에 다른 수신자 ID를 받지 않습니다.

모두 읽음은 현재 사용자에게 **이미 제공된 알림 ID 집합**을 전송합니다. 그 사이 도착했지만 아직 제공하지 않은 알림은 읽음으로 바꾸지 않습니다. 이미 읽은 항목은 최초 `readAt`을 유지하고, 하나라도 타인·없는 ID가 있으면 일부만 처리하지 않습니다.

상태 변경과 알림 생성은 [알림 생성 정책](../specs/notifications.md#generation-policy), 저장·중복 방지는 [알림 테이블](../database/notifications.md)을 참조합니다. 알림의 읽음 성공 후 관련 화면으로 이동하며 목적지의 현재 권한·존재 여부를 다시 확인합니다. 과거 알림으로 이전 권한을 복구하지 않습니다.

## 이 문서가 추가하지 않는 것

AI 과거 대화 검색·자동 지원·자동 선발·포트폴리오 수집, 사용자 간 채팅, 마감 알림·푸시·이메일은 추가하지 않습니다. AI 서버 영속화·로그 보존·새로고침 복원과 알림 보존·실시간 전달은 담당 기능 명세의 미정 범위를 유지합니다.
