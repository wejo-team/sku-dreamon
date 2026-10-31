# AI API

**상태: 백엔드 #157과 [제품 AI 화면 #192](https://github.com/wejo-team/sku-dreamon/pull/192)의 실제 API 연결 구현 · 운영 배포 미검증.** 일반 대화, 팀장의 지원자 검토·후보 추천을 OpenAI Luna와 `create_agent`로 실행합니다. 모든 경로는 `/api/v1` 아래에 있으며 현재 서버 세션으로 인증합니다. 제품 정책은 [추천 명세](../specs/matching.md), 실행 구조는 [아키텍처](../development/ai-architecture.md), 범위·결정은 [SDD](../development-plans/ai-agent.md)를 따릅니다.

정확한 요청·결과·이벤트 필드는 [AI DTO](../../backend/app/schemas/ai.py), 경로·HTTP 상태·의존성은 [라우터](../../backend/app/routers/ai.py)와 실행 앱의 `/docs`·`/openapi.json`이 원본입니다. 이전 `202 + Location + polling` 초안은 대체했으며 별도 대화 생성·목록·메시지 조회·복원 API는 제공하지 않습니다. 일반 채팅 접수 시 대화와 현재 입력을 저장하고 생성 완료 시 답변을 저장합니다.

<a id="streaming-proposal"></a>
<a id="conversation-endpoints"></a>
<a id="applicant-endpoints"></a>

## 경로와 권한

| 메서드·경로 | 입력 | 성공 응답·권한 |
| --- | --- | --- |
| `POST /ai/chat/stream` | `ChatStart` | 200 SSE. 현재 로그인 사용자 |
| `POST /applications/{applicationId}/ai-reviews/stream` | `TargetStart` | 200 SSE. 해당 지원을 받은 현재 팀장 |
| `POST /teams/{teamId}/applicant-recommendations/stream` | `TargetStart` | 200 SSE. 해당 팀의 현재 팀장 |
| `POST /ai/requests/{requestId}/retries/stream` | `RetryStart` | 200 SSE. 현재 요청 소유자·대상 관계·실패 시도 확인 |
| `GET /ai/requests/{requestId}` | 본문 없음 | 200 `Success<AiRequestView>`. 본문 없는 실행 상태 조회 |
| `PUT /ai/requests/{requestId}/cancellation` | `CancelRequest` | 200 `Success<AiRequestView>`. 현재 시도 중단 |
| `POST /ai/requests/{requestId}/validation` | `ValidateResult` | 200 `Success<ResultValidation>`. 표시·복사 전 결과 무결성과 현재 권한 검증 |

쿠키·CSRF·Origin 검사는 [기존 인증 전송 계약](conventions.md#csrf-transport)을 적용합니다. 비로그인은 401, 존재를 숨겨야 하는 대상·다른 소유자·만료된 실행은 404, 공개 가능한 리소스의 행동 권한 부족은 403입니다. 팀장의 기존 지원자 검토는 모집 종료·마감·정원 충족·지원 뒤 비공개 전환만으로 차단하지 않습니다. 새 후보는 유효한 지원 완료·검토 중이며 같은 공모전의 확정 소속이 없어야 합니다. AI 조회는 지원 상태를 바꾸지 않습니다.

<a id="conversation-fields"></a>
<a id="ai-control-fields"></a>

## 요청과 대화 맥락

일반 대화는 브라우저가 만든 `requestId`·`conversationId`·`clientMessageId`, 현재 `content`, 이전 사용자 발화 `history`, 이전 결과의 `requestId`·`attempt` 참조 `previousResults`를 보냅니다. 현재 입력은 NFC 정규화·앞뒤 공백 제거 후 Unicode 코드 포인트 1~1,000자이며 초과 입력을 잘라 사용하지 않습니다. 빈 값·NUL·잘못된 Unicode·선언하지 않은 필드·snake_case 요청 이름은 422입니다.

`history`는 사용자 문자열만 최대 20개이며 현재 입력과 합쳐 12,000자까지입니다. `previousResults`는 최대 20개입니다. 서버는 참조된 이전 실행의 소유권·같은 대화·시도를 검사하고 최신 자료를 다시 조회합니다. assistant 본문·`system`·`developer`·`tool` 메시지·임의 프로필을 요청 맥락으로 받지 않습니다. 이 한도는 요청 컨텍스트의 처리 예산이며 대화 전체 횟수를 제한하지 않습니다. 프론트는 현재 입력을 보존하고 컨텍스트 한도 도달 시 새 대화를 안내해야 합니다.

지원자 요청은 중복 방지용 `requestId`만 받으며 대상 ID는 경로에서 정합니다. 팀·지원·프로필 자료는 서버에서 조회합니다. 실패 재시도는 `expectedAttempt`와 **원래 입력 전체**를 `input`으로 다시 전달합니다. 대화 저장에는 원래 요청의 맥락 전체가 포함되지 않으며, 실행 입력 해시를 대조하므로 시도 번호만으로 재실행하지 않습니다.

<a id="request-lifecycle"></a>
<a id="ai-request-fields"></a>

## 실행 상태·중복·중단

실행 상태는 `pending`, `succeeded`, `empty`, `failed`, `canceled`입니다. 같은 인증 세션에서만 실행을 조회·중단·재시도할 수 있으며 ID가 접근 권한을 부여하지 않습니다. 상태 조회는 결과 원문을 복원하지 않습니다.

| 상황 | 처리 |
| --- | --- |
| 같은 ID·같은 입력 재전송 | 실행을 추가하지 않고 409 `REQUEST_ALREADY_RUNNING` 또는 `REQUEST_ALREADY_FINISHED`. 이미 알고 있는 `requestId`로 상태 조회 |
| 같은 ID의 다른 입력, 같은 메시지에 다른 실행 ID | 409 `MESSAGE_ID_CONFLICT` |
| 다른 계정이 소유한 `conversationId` 사용 | 404. 계정 소유 대화에 추가할 수 없음 |
| 메타데이터 만료 후 이미 저장한 채팅 메시지 재전송 | 409 `MESSAGE_ID_CONFLICT`. 새 실행·메시지 ID 필요 |
| 같은 대화·검토 대상에서 실행 중 | 409 `REQUEST_ALREADY_RUNNING` |
| 실패 재시도 | 입력 해시·현재 시도·재시도 가능 여부 확인 후 시도를 증가. 최대 3회 시도, 즉 최초 실행 후 재시도 최대 2회 |
| 이전 시도의 재시도·중단 | 409 `ATTEMPT_CONFLICT`. 새 시도에 적용하지 않음 |
| 재시도 불가 상태 | 409 `REQUEST_NOT_RETRYABLE`. 수정한 조건으로 새 요청 필요 |
| 현재 실행 중단 | `pending → canceled`. 모델 작업 취소를 요청하고 이후 결과 채택을 막음 |
| 같은 시도가 이미 종료됨 | 중단 요청은 현재 상태를 반환. 완료 결과를 중단으로 다시 쓰지 않음 |
| 연결 종료·프로세스 장애 | 연결 종료 시 실행 정리. 프로세스 장애로 남은 `pending`은 기한이 지난 다음 상태 조회·정리에서 실패 처리 |

SSE 자동 재연결·이벤트 재생은 제공하지 않습니다. 연결이 끊기면 실행 상태를 확인합니다. 이미 완료됐지만 전체 결과를 받지 못한 경우 저장된 본문의 재전송 API는 없으므로 새 실행 ID·메시지 ID로 다시 요청해야 합니다. 새로고침 뒤 대화 복원은 제공하지 않습니다. 중단은 제공자의 계산·과금·로그가 즉시 없어졌다는 보장이 아닙니다.

## 스트림 이벤트

성공 응답은 `text/event-stream`, `Cache-Control: no-store`, `X-Accel-Buffering: no`입니다. 스트림 전체를 JSON `Success<T>`로 감싸지 않습니다. `fetch`로 POST 본문·쿠키·CSRF를 전달하고 UTF-8·줄·이벤트 경계를 누적 파싱해야 합니다. 네트워크 청크와 SSE 이벤트는 일대일이 아닙니다.

모든 데이터 이벤트에 `requestId`·`attempt`·시도 내 증가하는 `sequence`가 있습니다. 정확한 페이로드는 `AiEvent`가 검증합니다. 10초 간격의 SSE 주석은 연결 유지용이며 답변이 아닙니다.

| 이벤트 | 내용 |
| --- | --- |
| `started` | 수락한 실행과 `purpose` |
| `progress` | `searching`, `validating`, `writing` 단계 |
| `answer.delta` | 사용자에게 표시할 텍스트 조각. 내부 추론·도구 출력·원시 계획은 제외 |
| `result` | 서버가 검증한 전체 `AiResult` |
| `done` | `succeeded` 또는 `empty`로 종료 |
| `error` | 안전한 실패 코드·안내·재시도 가능 여부 |
| `canceled` | 현재 시도 중단 |
| `invalidated` | 권한·근거 변경. 해당 답변 전체와 카드를 제거하고 안내로 대체해야 함 |

입력 가드는 매 일반 채팅 사용자 메시지에 적용하며, 허용 후에만 이전 결과 자료를 다시 조회합니다. 정책 거절은 고정 안내·빈 `cards`·`succeeded`로 정상 완료하고 완성 답변을 저장합니다. 가드 장애는 기존 `temporary_failure`로 종료하며 원래 입력 전체로 재시도합니다. 자유 입력 없는 지원자 목적 요청은 서버의 고정 요청을 사용합니다. 단일 ReAct의 필수 서버 검증 전 중간 텍스트·도구 JSON은 전송하지 않으며, 검증 후 `validating`·`writing`을 첫 최종 텍스트 직전에 보냅니다. 이벤트·상태 schema는 그대로 유지합니다.

정상 순서는 `started → progress* → answer.delta* → result → done`입니다. `done`을 받기 전 부분 답변이나 연결 단절을 완료로 표시하지 않습니다. 이전 대화·요청·시도의 늦은 이벤트는 반영하지 않습니다. 스트림 시작 전 오류는 공통 JSON HTTP 오류이며, 시작 후에는 HTTP 상태를 바꾸지 않고 종료 이벤트로 실패를 전달합니다.

<a id="termination"></a>

## 응답 종료와 지연 정리

[DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211)는 [AiStreamResponse](../../backend/app/routers/ai.py)와 [StreamCleanup](../../backend/app/services/ai.py)에 유한한 실행·정리 예산을 적용했습니다. 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. 헤더를 보내기 전부터 응답 실행을 `AI_TIMEOUT_SECONDS + 9초`로 제한하며, 헤더·heartbeat·본문·최종 프레임의 각 전송은 3초 안에 끝나야 합니다. provider `aclose`·실패 상태 저장·generator 종료·`on_close`는 첫 정리 때 시작한 단일 `AI_CLEANUP_TIMEOUT_SECONDS` deadline을 공유하고 새 예산을 시작하지 않습니다. 기본 정리는 5초, 허용 범위는 0.1~30초이며 상태 저장은 한 번만 시도합니다.

협조적 취소와 유한한 DB·driver I/O 아래 응답은 `AI_TIMEOUT_SECONDS + 9초 + AI_CLEANUP_TIMEOUT_SECONDS`와 스케줄링 여유 안에 끝납니다. 취소를 무시하는 임의 외부 코드를 강제로 종료한다는 보장은 아닙니다. 열려 있는 producer를 분리해 계속 실행하는 방식은 사용하지 않습니다. timeout·닫기 실패를 완료 저장·가짜 `result`/`done`으로 바꾸지 않으며 기존 성공/빈 결과의 commit 경계를 유지합니다. 전송이 이미 막혔으면 실패 이벤트도 전달되지 않을 수 있어 상태 조회로 확인합니다.

DB 실패·잠금 등으로 종료 상태 저장을 마치지 못하면 `pending`과 원래 `deadline_at`·`expires_at`을 유지합니다. 실행 기한 이후 상태 조회 또는 기존 `python -m app.cli.ai_runs`가 `failed`·`temporary_failure`로 회수하고, 접근 만료 뒤 물리 삭제합니다. 이전 시도의 늦은 정리가 새 시도나 이미 종료한 상태를 덮어쓰지 않습니다. 이 CLI는 대화·메시지를 삭제하는 보존 정책이 아닙니다. 실제 프록시 드레인·checkpoint·SSE 재생은 구현하지 않았으며 [배포 계획](../development-plans/deployment-foundation.md)에서 별도 검증합니다.

<a id="result-fields"></a>

## 결과와 근거

결과는 `ChatResult`, `ApplicantReviewResult`, `ApplicantRecommendationResult` 중 목적에 맞는 하나입니다. [DTO 원본](../../backend/app/schemas/ai.py)의 필드·개수·NULL·버전 표현을 사용합니다.

- 일반 대화는 종류 합계 최대 3개 카드입니다. 제목·리소스 ID·분야/역할·`isDemo`는 실제 서비스 자료로 구성합니다. 모델이 만든 URL을 이동 경로로 사용하지 않습니다.
- 개별 검토는 지정 지원 한 건의 요약·근거·사용한 프로필 버전·현재 후보 여부를 제공합니다. 후보 여부가 실제 선발 허가를 뜻하지 않습니다.
- 팀 후보 추천은 실제 유효 지원만 제공합니다. 일반 카드 3개 제한을 지원자 수에 확대하지 않으며 조회·입력 예산은 별도로 적용합니다.
- 응답의 사실성은 구조화 출력만으로 증명되지 않습니다. 존재하지 않는 ID·잘못된 목적·허용 범위 밖 후보는 서버가 거부하고, 설명 품질은 별도 평가 대상입니다.

<a id="current-permissions"></a>

## 현재 권한과 이전 결과 재검증

도구 실행은 현재 권한으로 자료를 조회하고 모델 전송 필드는 [자료 서비스](../../backend/app/services/ai_sources.py)의 허용 목록으로 제한합니다. 일반 사람 탐색은 공개 자료만 읽으며, 지원받은 팀장의 최신 비공개 프로필 검토 권한은 일반 대화로 확장하지 않습니다.

텍스트·최종 결과를 전송할 때 관련 계정·공고·팀·지원·프로필과 세션을 짧게 잠그고 실제 근거 해시를 다시 검사합니다. 잠금은 ASGI 전송 경계까지 유지하고 한 번의 전송은 최대 3초로 제한합니다. 모델을 기다리는 동안 DB 잠금을 유지하지 않습니다. 전송 직후 공개 철회가 발생할 수 있고 이미 전달된 바이트를 회수할 수 없으므로, 이는 클라이언트가 읽는 순간까지 권한을 고정하거나 이미 전달한 내용을 회수한다는 보장이 아닙니다.

표시·복사 시에는 브라우저가 가진 원래 `result`와 `attempt`를 validation API로 보냅니다. 서버에 저장된 결과 SHA-256과 다르면 409 `AI_RESULT_MISMATCH`입니다. 현재 허용되지 않거나 일반 추천 근거가 바뀌면 `valid=false, result=null`이며 본문·카드를 모두 제거해야 합니다. 결과 조회 실패를 오래된 답변의 복사 성공으로 처리하지 않습니다.

지원자 프로필이 변경됐지만 현재 팀장 열람 권한이 유지되면 이전 결과를 다시 작성하지 않고 `usedVersion`·`currentVersion`·`isStale`를 구분합니다. 새 후보가 선발·미선발·취소·폐기로 바뀌면 후보 추천 결과는 무효입니다. 검증 응답의 갱신된 버전 표시는 화면용이며, 다음 검증에는 해시가 일치하는 **최초 result**를 다시 보내야 합니다.

과목 카탈로그의 대표명 재적재처럼 프로필 버전을 바꾸지 않는 조회 근거 변경도 저장 당시와 현재 근거의 fingerprint를 비교해 `isStale=true`로 표시합니다. 이 경우 `usedVersion`과 `currentVersion`은 같을 수 있습니다. 과거 답변을 최신 과목명으로 자동 재작성하거나 현재 근거로 간주하지 않습니다.

## 저장·운영 경계

일반 채팅은 현재 사용자 입력과 성공/빈 결과의 완성 답변을 [대화·메시지 테이블](../database/ai.md)에 저장합니다. 접수와 입력 저장, 완료와 답변 저장은 각각 같은 트랜잭션이며 저장 실패를 성공으로 표시하지 않습니다. 이전 사용자 발화 `history`의 중복 적재, 실패·취소·완료 전 무효화된 부분 답변, 지원자 검토·후보 추천 원문, 프로필 전문은 저장하지 않습니다. 별도 삭제 정책이 정해지기 전까지 대화에는 자동 만료를 적용하지 않으며, 실행 정리 CLI도 대화를 지우지 않습니다. 대화 저장은 조회·복원이나 모델 맥락 자동 로드를 추가하지 않습니다.

기존 실행 메타데이터에는 본문 대신 소유권·상태·시도·해시·근거 참조를 저장합니다. 실행 메타데이터는 기본 24시간 뒤 접근이 만료됩니다. 신규 실행과 운영 정리 명령이 만료 행을 삭제하며, 유휴 시간의 물리 삭제는 운영 스케줄에서 해당 명령을 호출해야 합니다.

기본 실행 한도와 실제 OpenAI 수동 검사·정리 명령은 [AI 로컬 실행](../development/local-development.md#ai-backend)에 둡니다. 기본 `AI_REQUIRED=false`에서는 API 키가 없으면 AI 생성 경로가 503 `AI_NOT_CONFIGURED`입니다. AI 제공 배포는 `AI_REQUIRED=true`로 키 누락을 기동 실패로 처리하며 다른 모델로 자동 전환하지 않습니다. 운영 HTTPS·프록시 스트리밍·정리 스케줄·비용/품질 평가는 배포 환경에서 별도로 검증해야 합니다.
