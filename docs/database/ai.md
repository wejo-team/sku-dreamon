# AI 대화와 실행 저장

**상태: 백엔드 작업 브랜치 구현 · 운영 DB 미적용.** 일반 채팅의 원문 보존과 실행 제어의 수명을 분리합니다. [AI API](../api/ai.md), [아키텍처](../development/ai-architecture.md), [설계 결정](../development-plans/ai-agent.md)을 함께 봅니다.

## 관계와 저장 범위

```text
accounts ──< ai_conversations ──< ai_messages
accounts ──< ai_runs >── auth_sessions
                │
                └─ 팀·지원 대상 FK (지원자 목적)

ai_messages.request_id와 ai_runs.ai_run_id는 논리적으로 같은 실행을 가리킨다.
메타데이터를 먼저 삭제할 수 있도록 두 테이블 사이에 FK는 두지 않는다.
```

대화의 소유자는 계정입니다. 로그인 세션이 끝나거나 실행 메타데이터를 정리해도 대화가 연쇄 삭제되지 않습니다. 현재 대화 목록·메시지 조회·수정·삭제·복원 API는 없습니다. 저장된 본문을 모델 맥락으로 자동 복원하지 않습니다.

## 대화·메시지 모델

원본은 [AiConversation·AiMessage](../../backend/app/models/ai_chat.py), 도입 revision은 [20261025_08](../../backend/alembic/versions/20261025_08_ai_chat_history.py)입니다.

| `ai_conversations` 컬럼 | 타입·제약·의미 |
| --- | --- |
| `ai_conversation_id` | UUID PK. 클라이언트의 `conversationId` |
| `account_id` | UUID NOT NULL, `accounts` FK. 계정 소유권 |
| `created_at`, `updated_at` | TIMESTAMPTZ NOT NULL. 첫 입력 접수·마지막 저장 시각 |

`updated_at >= created_at` CHECK와 `(account_id, created_at)` 조회 인덱스를 둡니다. 다른 계정이 이미 소유한 대화 ID는 404로 거부합니다. 아직 목록을 제공하지 않으므로 자동 제목·요약·대화 목록 상태는 추가하지 않습니다.

| `ai_messages` 컬럼 | 타입·제약·의미 |
| --- | --- |
| `ai_message_id` | 서버 발급 UUID PK |
| `ai_conversation_id` | UUID NOT NULL, 대화 FK |
| `client_message_id` | UUID NOT NULL. 사용자 입력과 그 답변을 연결하는 기존 `clientMessageId` |
| `request_id` | UUID NOT NULL. 원래 실행 ID, 만료 후에도 유지하는 논리 참조 |
| `role` | VARCHAR(16), `user` 또는 `assistant` CHECK |
| `content` | TEXT NOT NULL. 정규화된 현재 사용자 입력 또는 완성된 답변 본문 |
| `attempt` | INTEGER, 1 이상 CHECK. user는 1, assistant는 답변을 완료한 실행 시도 |
| `model` | VARCHAR(64). user는 NULL, assistant는 사용 모델 ID 필수 |
| `source_references` | JSONB 배열. user는 빈 배열, assistant는 근거 자료 ID·버전·해시. 프로필 전문·도구 원문 제외 |
| `created_at` | TIMESTAMPTZ NOT NULL. 입력 접수 또는 답변 완료 시각 |

입력은 1~1,000자, 답변은 1~12,000자로 제한합니다. `(request_id, role)`과 `(ai_conversation_id, client_message_id, role)`에 UNIQUE를 두어 재시도·다른 실행 ID를 사용한 같은 메시지 재전송을 중복 저장하지 않습니다. 메시지의 생성 시각과 ID로 안정적으로 정렬할 수 있고 같은 `client_message_id`로 입력·답변을 묶습니다. `(ai_conversation_id, created_at)` 인덱스를 둡니다.

일반 채팅에서 현재 입력만 저장하며 요청의 `history`를 과거 메시지로 중복 적재하지 않습니다. 실패·취소·완료 전 권한 변경으로 끝난 부분 답변, 지원자 검토·후보 추천 원문, system/tool 메시지, 결과 카드 JSON은 저장하지 않습니다. 답변에 포함된 설명은 본문으로 보존하고 근거 참조는 별도로 남깁니다. 저장된 ID·해시가 향후 열람 권한을 부여하지 않습니다.

## 저장 트랜잭션과 예외

- 접수한 사용자 메시지와 `ai_runs`의 시작/재시도는 같은 트랜잭션입니다. 대화 생성·입력 저장 실패 시 실행도 시작하지 않습니다. 거부된 요청은 기록하지 않습니다.
- 소유권 확인과 사용자 메시지의 충돌 없는 INSERT를 계정 잠금 아래 수행합니다. 서로 다른 계정이 같은 대화 ID를 동시에 만들더라도 하나의 소유자만 확정됩니다.
- 실패 재시도는 기존 사용자 메시지를 유지하며 완성된 assistant만 한 번 추가합니다. 입력 내용·메시지 ID를 바꾸는 것은 재시도가 아닙니다.
- 완료 시 현재 자료·세션·시도를 잠금 아래 재검증하고 답변 INSERT와 실행 성공/빈 결과·결과 해시를 함께 커밋합니다. 답변 저장 실패 시 성공 상태와 결과 해시도 롤백됩니다.
- 저장 완료는 클라이언트 수신 확인과 다릅니다. 완료 커밋 뒤 네트워크 단절·권한 변경이 발생해도 저장된 답변은 유지하며 기존 스트림 재생 API는 제공하지 않습니다.
- 실행 정리 뒤 같은 요청·메시지 ID는 409 `MESSAGE_ID_CONFLICT`입니다. 새 요청에는 새 실행·메시지 ID를 사용합니다.

## 실행 메타데이터

원본은 [AiRun](../../backend/app/models/ai_runs.py), 도입 revision은 [20261025_07](../../backend/alembic/versions/20261025_07_ai_runs.py)입니다. 기존 실행 테이블은 계속 본문을 저장하지 않습니다.

| 영역 | 저장값과 의미 |
| --- | --- |
| 식별·소유 | `ai_run_id` PK, `account_id`·`auth_session_id` FK. 실행 조회·취소·재시도는 소유 인증 세션에 한정 |
| 목적·대상 | 목적, 대화/메시지 ID 또는 팀·지원 FK. 목적별 필수/NULL 조합 CHECK |
| 실행 제어 | 현재 시도·상태·실패 코드·생성/갱신 시각·실행 기한·보존 기한 |
| 입력 중복 방지 | 원래 요청 전체·목적·대상의 SHA-256 |
| 결과 검증 | 전체 결과 SHA-256, 조회 자료 ID·관련 ID·버전·해시, 선택된 자료 key |

`(auth_session_id, conversation_id, client_message_id)` UNIQUE와 진행 중 `(account_id, scope_key)` 부분 UNIQUE를 유지합니다. 성공/빈 결과에는 결과 해시, 실패에는 실패 코드가 있어야 하며 목적·시도·기한을 CHECK로 제한합니다. 계정 → 공고 → 팀 → 지원 → 프로필 → 실행·세션 순으로 잠그고 현재 자료를 확인합니다. LLM 대기에는 잠금을 유지하지 않습니다.

## 보존과 마이그레이션

실행 기한은 기본 90초, 메타데이터 접근 만료는 시도 시작 기준 기본 24시간입니다. 기한이 지난 진행 실행은 상태 조회·정리에서 재시도 가능한 실패로 바뀝니다. 메타데이터 만료 뒤에는 실행 조회가 404이며 새 요청 또는 `uv run python -m app.cli.ai_runs`가 행을 삭제합니다. 이 명령은 대화·메시지를 삭제하지 않습니다.

대화 원문은 별도 보존 기간이 확정되지 않아 현재 자동 만료·삭제하지 않습니다. 계정 탈퇴·보존 기간·백업·삭제/익명화 정책은 후속 결정입니다. FK는 RESTRICT이며 삭제 시 메시지 → 대화 → 계정 순서를 고려해야 합니다. 대화 저장이 향후 원문 조회 API의 권한 검증을 대체하지 않으며, 조회 기능 도입 시 현재 소유권·자료 공개 범위·결과 노출 정책을 별도로 설계해야 합니다.

`20261025_08`은 새 테이블만 추가하며 기존 실행 원문을 역으로 채우지 않습니다. 이전에 저장하지 않은 본문은 복구할 수 없습니다. 이전 실패 실행의 정상 재시도는 재전송한 현재 입력부터 저장할 수 있습니다. downgrade는 두 테이블과 저장된 대화를 삭제하므로 적용 환경에서 데이터 보존 여부를 먼저 판단해야 합니다. 운영 DB 적용은 이번 작업에서 수행하지 않습니다.
