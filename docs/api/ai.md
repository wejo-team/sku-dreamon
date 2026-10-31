# AI API

**상태: 기존 AI 대화 연결에 지원자 평가 v3·완성 JSON 연결 추가 · 운영 배포 미검증.** 일반 대화, 팀장의 지원자 검토·후보 추천을 OpenAI Luna와 `create_agent`로 실행합니다. 모든 경로는 `/api/v1` 아래에 있으며 현재 서버 세션으로 인증합니다. 제품 정책은 [추천 명세](../specs/matching.md), 실행 구조는 [아키텍처](../development/ai-architecture.md), 범위·결정은 [SDD](../development-plans/ai-agent.md)를 따릅니다.

정확한 요청·결과·이벤트 필드는 [AI DTO](../../backend/app/schemas/ai.py), 경로·HTTP 상태·의존성은 [라우터](../../backend/app/routers/ai.py)와 실행 앱의 `/docs`·`/openapi.json`이 원본입니다. 이전 `202 + Location + polling` 초안은 대체했으며 별도 대화 생성·목록·메시지 조회·복원 API는 제공하지 않습니다. 일반 채팅 접수 시 대화와 현재 입력을 저장하고 생성 완료 시 답변을 저장합니다.

<a id="streaming-proposal"></a>
<a id="conversation-endpoints"></a>
<a id="applicant-endpoints"></a>

## 경로와 권한

| 메서드·경로 | 입력 | 성공 응답·권한 |
| --- | --- | --- |
| `POST /ai/chat/stream` | `ChatStart` | 200 SSE. 현재 로그인 사용자 |
| `POST /applications/{applicationId}/ai-reviews` | `TargetStart` | 200 `Success<AiCompletion>`. 해당 지원을 받은 현재 팀장 |
| `POST /teams/{teamId}/applicant-recommendations` | `TargetStart` | 200 `Success<AiCompletion>`. 해당 팀의 현재 팀장 |
| `POST /ai/requests/{requestId}/retries` | `RetryStart` | 200 `Success<AiCompletion>`. 지원자 평가 실패 시도만 재실행 |
| `POST /applications/{applicationId}/ai-reviews/stream` | `TargetStart` | 호환용 SSE. 현재 팀장에게 v3 최종 결과만 전달 |
| `POST /teams/{teamId}/applicant-recommendations/stream` | `TargetStart` | 호환용 SSE. 현재 팀장에게 v3 최종 결과만 전달 |
| `POST /ai/requests/{requestId}/retries/stream` | `RetryStart` | 200 SSE. 현재 요청 소유자·대상 관계·실패 시도 확인 |
| `GET /ai/requests/{requestId}` | 본문 없음 | 200 `Success<AiRequestView>`. 본문 없는 실행 상태 조회 |
| `PUT /ai/requests/{requestId}/cancellation` | `CancelRequest` | 200 `Success<AiRequestView>`. 현재 시도 중단 |
| `POST /ai/requests/{requestId}/validation` | `ValidateResult` | 200 `Success<ResultValidation>`. 표시·복사 전 결과 무결성과 현재 권한 검증 |

쿠키·CSRF·Origin 검사는 [기존 인증 전송 계약](conventions.md#csrf-transport)을 적용합니다. 비로그인은 401, 존재를 숨겨야 하는 대상·다른 소유자·만료된 실행은 404, 공개 가능한 리소스의 행동 권한 부족은 403입니다. 팀장의 기존 지원자 검토는 모집 종료·마감·정원 충족·지원 뒤 비공개 전환만으로 차단하지 않습니다. 새 후보는 유효한 지원 완료·검토 중이며 같은 공모전의 확정 소속이 없어야 합니다. AI 조회는 지원 상태를 바꾸지 않습니다.

<a id="conversation-fields"></a>
<a id="ai-control-fields"></a>

## 요청과 대화 맥락

일반 대화는 브라우저가 만든 `requestId`·`conversationId`·`clientMessageId`, 현재 `content`, 이전 사용자 발화 `history`, 이전 결과의 `requestId`·`attempt` 참조 `previousResults`를 보냅니다. 현재 입력은 NFC 정규화·앞뒤 공백 제거 후 Unicode 코드 포인트 1~1,000자이며 초과 입력을 잘라 사용하지 않습니다. 빈 값·NUL·잘못된 Unicode·선언하지 않은 필드·snake_case 요청 이름은 422입니다.

일반 대화의 새 화면은 선택 필드 `resultFormat: "rich"`를 보내 근거·등록 정보를 포함한 카드를 요청합니다. 생략하거나 `null`이면 기존 기본 카드 형식이며, 서버의 정규화 입력 직렬화에서도 이 필드를 제외해 이전 요청의 입력 해시를 유지합니다. `rich` 요청의 재시도는 원입력의 값까지 그대로 보내야 하며 형식을 중간에 바꾸면 409입니다. 지원자 요청에는 이 옵션을 추가하지 않습니다.

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

입력 가드는 매 일반 채팅 사용자 메시지에 적용하며, 허용 후에만 이전 결과 자료를 다시 조회합니다. 정책 거절은 고정 안내·빈 `cards`·`succeeded`로 정상 완료하고 완성 답변을 저장합니다. 가드 장애는 기존 `temporary_failure`로 종료하며 원래 입력 전체로 재시도합니다. 자유 입력 없는 지원자 목적 요청은 서버의 고정 요청을 사용합니다. 일반 대화 단일 ReAct의 필수 서버 검증 전 중간 텍스트·도구 JSON은 전송하지 않으며, 검증 후 `validating`·`writing`을 첫 최종 텍스트 직전에 보냅니다. 이벤트·상태 schema는 그대로 유지합니다.

정상 순서는 `started → progress* → answer.delta* → result → done`입니다. `done`을 받기 전 부분 답변이나 연결 단절을 완료로 표시하지 않습니다. 이전 대화·요청·시도의 늦은 이벤트는 반영하지 않습니다. 스트림 시작 전 오류는 공통 JSON HTTP 오류이며, 시작 후에는 HTTP 상태를 바꾸지 않고 종료 이벤트로 실패를 전달합니다.

### 지원자 평가의 완성 JSON

지원자 제품 화면은 `/stream` 없는 POST를 사용합니다. 지원자 전용 `create_agent`는 기존 권한별 조회 도구와 명시적 `ProviderStrategy(ApplicantAssessmentPlan, strict=True)`로 조회·평가를 한 그래프에서 수행합니다. 자유 텍스트 생성·부분 문장 전송 없이 구조화 결과를 만든 뒤 서버가 대상·근거·현재 권한을 검사합니다. 제공자의 완료 상태가 `incomplete`이면 JSON이 파싱돼도 성공 처리하지 않습니다.

`Success<AiCompletion>.data`는 `requestId`, `attempt`, `status`, `result`입니다. `succeeded`·`empty`는 결과가 있고 `canceled`·`invalidated`는 반드시 `result=null`입니다. 실패는 표준 HTTP 오류로 반환하며 원문 없는 실행 상태 조회로 재시도 가능 여부를 확인합니다. chat 목적의 JSON 재시도는 409입니다. `Cache-Control: no-store`와 전송 경계의 현재 권한 검증을 유지합니다. 기존 지원자 SSE 경로도 `answer.delta` 없이 같은 v3 `result`·`done`만 보냅니다.

생성 중 화면에는 진행 상태와 요청 취소를 제공하며 가짜 진행률·부분 문장은 표시하지 않습니다. 결과 원문 저장·결과 polling·새로고침 복원은 추가하지 않습니다.

<a id="termination"></a>

## 응답 종료와 지연 정리

[DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211)는 [AiStreamResponse](../../backend/app/routers/ai.py)와 [StreamCleanup](../../backend/app/services/ai.py)에 유한한 실행·정리 예산을 적용했습니다. 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. 지원자 `AiJsonResponse`도 같은 전체 응답·개별 전송·공유 정리 deadline과 한 번의 상태 저장 규칙을 적용합니다. 헤더를 보내기 전부터 응답 실행을 `AI_TIMEOUT_SECONDS + 9초`로 제한하며, 헤더·heartbeat·본문·최종 프레임의 각 전송은 3초 안에 끝나야 합니다. provider `aclose`·실패 상태 저장·generator 종료·`on_close`는 첫 정리 때 시작한 단일 `AI_CLEANUP_TIMEOUT_SECONDS` deadline을 공유하고 새 예산을 시작하지 않습니다. 기본 정리는 5초, 허용 범위는 0.1~30초이며 상태 저장은 한 번만 시도합니다.

협조적 취소와 유한한 DB·driver I/O 아래 응답은 `AI_TIMEOUT_SECONDS + 9초 + AI_CLEANUP_TIMEOUT_SECONDS`와 스케줄링 여유 안에 끝납니다. 취소를 무시하는 임의 외부 코드를 강제로 종료한다는 보장은 아닙니다. 열려 있는 producer를 분리해 계속 실행하는 방식은 사용하지 않습니다. timeout·닫기 실패를 완료 저장·가짜 `result`/`done`으로 바꾸지 않으며 기존 성공/빈 결과의 commit 경계를 유지합니다. 전송이 이미 막혔으면 실패 이벤트도 전달되지 않을 수 있어 상태 조회로 확인합니다.

DB 실패·잠금 등으로 종료 상태 저장을 마치지 못하면 `pending`과 원래 `deadline_at`·`expires_at`을 유지합니다. 실행 기한 이후 상태 조회 또는 기존 `python -m app.cli.ai_runs`가 `failed`·`temporary_failure`로 회수하고, 접근 만료 뒤 물리 삭제합니다. 이전 시도의 늦은 정리가 새 시도나 이미 종료한 상태를 덮어쓰지 않습니다. 이 CLI는 대화·메시지를 삭제하는 보존 정책이 아닙니다. 실제 프록시 드레인·checkpoint·SSE 재생은 구현하지 않았으며 [배포 계획](../development-plans/deployment-foundation.md)에서 별도 검증합니다.

<a id="result-fields"></a>

## 결과와 근거

결과는 `ChatResult`, `ApplicantReviewResult`, `ApplicantRecommendationResult` 중 목적에 맞는 하나입니다. 일반 대화 계약은 기존대로 버전 필드 없이 유지하고 지원자 결과만 필수 `schemaVersion: 3`을 제공합니다. [DTO 원본](../../backend/app/schemas/ai.py)의 필드·개수·NULL·버전 표현을 사용합니다.

- 일반 대화는 종류 합계 최대 3개 카드입니다. 제목·리소스 ID·분야/역할·`isDemo`는 실제 서비스 자료로 구성합니다. 모델이 만든 URL을 이동 경로로 사용하지 않습니다.
- 개별 검토는 지정 지원 한 건의 요약·근거·사용한 프로필 버전·현재 후보 여부와 `assessment`를 제공합니다. 후보 여부가 실제 선발 허가를 뜻하지 않습니다.
- 팀 후보 추천은 조회된 유효 지원 중 이번 실행이 선택한 최대 3명만 평가합니다. 전체 지원자 일괄 평가·점수별 상위 순위가 아니며 정보 부족만을 제외 사유로 삼지 않습니다. 응답 배열의 기존 최대 100개 전송형은 유지하되 모델 출력과 서비스는 3명 상한을 강제합니다. 각 유효 후보에 현재 등록 이름 `title`, 등록 역량 `profile.skillCodes`, `assessment`를 포함합니다. 이 상한은 평가 생성의 출력 예산이며 일반 대화 카드 제한과 별개입니다. 조회·입력 예산도 기존대로 적용합니다.
- 응답의 사실성은 구조화 출력만으로 증명되지 않습니다. 존재하지 않는 ID·잘못된 목적·허용 범위 밖 후보는 서버가 거부하고, 설명 품질은 별도 평가 대상입니다.

<a id="rich-chat-results"></a>

### 일반 대화의 선택적 등록 정보

기본 `ResourceCard`는 기존 `kind`, `resourceId`, `title`, `reason`, `fieldCodes`, `roleCodes`, `isDemo`만 반환합니다. `resultFormat: "rich"`로 생성한 카드만 `evidence`와 `details`를 함께 갖습니다. 두 형식 모두 버전 필드를 추가하지 않으며 새 클라이언트는 엄격한 두 형식을 구분합니다. 절반만 있는 확장 필드·미등록 역량·종류 불일치·추가 사실 필드는 거부합니다.

- `evidence`는 검증된 선택 계획의 최대 6개·각 500자 설명입니다. 모델의 서술이며 별도 사실 보증이나 점수가 아닙니다.
- `details`는 모델이 작성하지 않습니다. 서버가 실제로 조회하고 선택·현재 권한을 검증한 해당 자료의 허용 필드만 결합합니다. 사람은 등록 역량·주당 시간·경험 상태/내용·자기소개, 팀은 공모전명·정원·현재 인원·모집 종료 시각/상태, 공모전은 주최자·접수 상태·시작/종료 시각입니다.
- 미입력은 `null`/빈 배열/`unspecified` 그대로 보존하며 시간 부족·경험 없음·0점으로 바꾸지 않습니다. `capacity`는 기존 양의 정수 문자열 계약, `memberCount`는 엄격한 양의 정수, 시각은 시간대가 있는 timestamp입니다.
- 일반 채팅 UI는 설명과 등록 사실을 펼쳐 보고, 이번 답변에 표시된 공개 사람만 등록 역량으로 필터링하거나 2~3명 비교합니다. 전체 검색 조건·순위·지원자 평가로 확장하지 않습니다. 복사도 새 권한 검증 뒤 같은 근거와 사실을 포함합니다.

기본·확장 카드 모두 최초 결과 전체를 해시에 포함합니다. 기존 저장 결과에 새 필드를 채워 넣지 않으며 재검증은 받은 원본 그대로 전송합니다. 공개 철회·근거 변경·세션 종료 시 답변·카드·비교표를 함께 숨기고 복사를 차단합니다. 이미 시스템 클립보드로 전달한 내용까지 회수하는 기능은 아닙니다.

### 지원자 평가 구조

개별 검토와 각 후보의 `assessment`에는 정확히 네 개의 서로 다른 항목(`role`, `skills`, `experience`, `availability`)과 최대 세 개의 확인 질문이 있습니다. 항목은 필수 nullable `score`, 필수 `informationStatus`, 짧은 설명, 실제 등록 자료의 출처·내용으로 된 근거를 제공합니다.

- `score`는 0~100의 5점 단위 엄격한 정수 또는 `null`입니다. boolean·실수·숫자 문자열·범위 밖·5의 배수가 아닌 값은 거부합니다.
- `informationStatus=sufficient`일 때만 숫자 점수가 있고 `insufficient`일 때는 반드시 `score=null`입니다. 서버·클라이언트 스키마가 양방향 일치를 검사합니다. 0점은 근거가 있는 실제 불일치이며 정보 부족과 다릅니다.
- 숫자 점수에는 해당 항목의 실제 지원자 근거가 필요합니다. 모델이 반환한 참조가 서버 자료 목록에 없거나 다른 지원자의 참조이면 거부합니다. 팀 소개만으로 지원자 역량에 점수를 줄 수 없습니다. 참여시간 숫자에는 등록 주당 시간·팀 소개의 조건·지원 메시지의 팀별 배정시간 참조가 함께 필요합니다.
- [평가 프롬프트](../../backend/app/agents/prompts.py)는 항목마다 0·25·50·75·100 기준점을 정의하고 그 사이를 5점 단위로 평가합니다. 모든 후보에게 동일한 팀 요구와 루브릭을 적용하며 총점·순위·자동 선발은 만들지 않습니다. 학년·전공·이름 등 개인 속성으로 점수를 정하지 않습니다. 미등록을 0점으로 처리하지 않고, 팀의 시간 요구나 지원자의 팀별 배정시간이 불명확하면 참여시간 점수는 `null`입니다.

지원자 요약은 최대 600자, 항목 설명은 300자, 근거는 항목당 최대 6개·각 500자, 질문은 각 200자입니다. 정확한 source enum·필드·검증은 DTO와 [평가 근거 구성](../../backend/app/agents/assessment.py)이 원본입니다. 프롬프트의 루브릭·의미 판단과 서버의 형식·참조 검증은 구분하며 실제 모델의 점수 일관성은 별도 품질 검증 대상입니다. 기본 출력 예산 안에서 일괄 결과가 과도해지지 않도록 이번 추천은 최대 3명이며 항목 설명·총평은 간결한 한 문장으로 요청합니다.

지원자 UI는 네 항목을 세로축, 점수 0~100을 가로축으로 비교합니다. 후보마다 고유색을 사용하고 이름·범례·숫자 점수를 함께 표시합니다. `informationStatus=insufficient`는 0점 막대로 바꾸지 않고 점선·비어 있는 표시로 구분하며 그래프에 같은 안내 문구를 반복하지 않습니다. 평가 설명·근거·출처·확인 질문·등록 정보 패널은 표시하지 않으며 원문·프로필은 지원서 상세로 연결합니다. 화면에 숨긴 검증 필드도 최초 결과와 해시에 포함하며, 재검증 전에 삭제하거나 점수를 다시 계산하지 않습니다.

### 결과 버전과 호환

기존 대화 결과는 버전 필드를 추가하지 않고 기본 요청에는 기본 응답을 유지합니다. 일반 대화의 rich 확장은 요청 opt-in으로만 활성화하며 기존 엄격한 클라이언트·이미 발급된 결과 해시·입력 재시도와 호환됩니다. 지원자 v3의 새 필드는 필수입니다. `schemaVersion`이 없거나 지원하지 않는 버전의 결과를 임의로 보완해 표시·재검증하지 않습니다. 브라우저 메모리에 남은 구형 결과는 새 요청으로 다시 생성합니다. 이 결과 변경은 기존 대화 메시지를 수정하는 DB 마이그레이션을 추가하지 않습니다. 재검증에 보내는 최초 결과를 그대로 보존하며, 표시용 필드를 덧붙이거나 버전 값을 고쳐 기존 실행의 결과 해시를 맞추지 않습니다.

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
