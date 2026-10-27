# AI 에이전트 SDD

- 기준: 2026-10-25 사용자 결정, [설계 PR #156](https://github.com/wejo-team/sku-dreamon/pull/156)
- 상태: **백엔드 PR #157 병합 · 프론트 실제 AI 미연결 · 미배포**
- 기준 명세: [LLM 기반 추천](../specs/matching.md#acceptance-criteria), AC-16~35
- 구현 PR: [#157](https://github.com/wejo-team/sku-dreamon/pull/157)
- 구현 구조: [AI 에이전트 아키텍처](../development/ai-architecture.md)
- 계약 원본: [AI API](../api/ai.md), [AI 실행 저장](../database/ai.md)
- 구현 PR의 범위: 사용자 요청에 따라 **백엔드만 구현**했으며 운영 DB 적용은 포함하지 않았습니다. 아래 결정·검증은 PR #157 당시 범위이고 현재 남은 작업은 후속 절에서 구분합니다.

공모전·팀·공개 사람 탐색과 팀장의 지원자 검토를 기존 FastAPI 서비스에 연결합니다. 사용자 동작은 기능 명세, 전송 계약은 DTO·API 문서, 저장 구조는 ORM·DB 문서가 원본입니다. PR #157은 프론트 변경을 포함하지 않았습니다. 현재 자체 로그인·지원자 조회의 실제 API 연결 상태는 [구현 현황](../development/implementation-status.md), AI 대화·지원자 AI 검토의 실제 화면 연결은 [후속 작업 #163](https://github.com/wejo-team/sku-dreamon/issues/163)을 참조합니다.

## 결정과 적용 범위

2026-10-25 추가 사용자 요청으로 이번 PR에 일반 AI 대화의 DB 저장과 구현 아키텍처 문서를 포함합니다. `ai_conversations`는 계정 소유 대화, `ai_messages`는 접수한 사용자 메시지와 성공/빈 결과의 완성된 답변을 저장합니다. 요청 접수와 사용자 메시지 저장, 실행 완료와 답변 저장은 각각 같은 트랜잭션에서 확정합니다. 실패·취소·권한 무효화 전의 부분 답변과 지원자 검토 원문은 저장하지 않습니다. 실행 메타데이터 만료와 대화 보존은 분리하며 조회·목록·복원 API, 모델 맥락의 DB 자동 복원, 프론트 변경은 추가하지 않습니다. 재시도·만료 뒤 재전송·다른 계정의 대화 ID 사용·저장 실패를 검증합니다.

| 항목 | 선택 | 적용 상태 |
| --- | --- | --- |
| 에이전트 | `langchain.agents.create_agent`, LangGraph 런타임 | 구현 |
| 모델 | OpenAI Luna, `gpt-6-luna` | 실제 도구 호출·구조화 출력·스트림 수동 검증 |
| 모델 API | Responses API, `store=False`, 자동 모델 대체 없음 | 구현 |
| 응답 전달 | FastAPI 비동기 실행과 POST SSE | 백엔드 구현, 화면 연결은 후속 |
| 대화 유지 | 현재 브라우저 탭 메모리, 새로고침·새 대화·로그아웃 시 초기화 | 제품 요구사항. 서버 원문은 별도 보존하며 복원 API 없음 |
| 실행 상태 | PostgreSQL 공유 메타데이터·입력/결과 해시·근거 참조 | 모델·migration·재시도·중단·정리 구현 |
| 대화 저장 | 계정 소유 대화·접수 입력·완성 답변 | 일반 채팅만 보존, 조회 API·자동 만료 없음 |
| 프론트 | AI 화면의 인증·탭 메모리·스트림 파서·복사 재검증 | PR #157에서 제외. 실제 AI 화면 연결은 #163 후속 |

별도 LLM worker·큐·LangGraph 서버·Deep Agents·벡터 DB·임베딩·장기 기억은 도입하지 않습니다. 자동 지원·선발·외부 웹/포트폴리오 수집·과거 대화 목록은 기존 제외 범위를 유지합니다.

## 구조와 설계 이유

실제 실행 흐름·모듈 책임·도구 권한·대화 맥락·트랜잭션·장애 처리는 [아키텍처 문서](../development/ai-architecture.md)를 원본으로 관리합니다. 이 SDD에는 선택 이유와 후속 범위를 둡니다.

- Planner의 자료 조회·구조화 계획 뒤 서버가 후보·권한을 검증하고 별도 Writer가 답변을 생성합니다. 검증 전 계획을 제품 스트림에 섞지 않기 위한 선택이며 첫 답변 지연·모델 호출 비용은 실제 자료로 평가해야 합니다.
- 실행 제어를 PostgreSQL에 공유해 여러 프로세스의 중복·취소·재시도를 일관되게 검사합니다. 영속 LangGraph checkpoint·worker·큐와 실행 재개는 도입하지 않습니다.
- 일반 대화 원문은 사용자 후속 요청에 따라 실행 메타데이터와 별도 테이블에 저장합니다. 입력 접수와 실행 생성, 답변 저장과 성공 처리를 각각 하나의 트랜잭션으로 묶고 실패·취소된 부분 답변은 저장하지 않습니다.
- 메시지 보존은 기록 조회·복원 API나 모델의 장기 기억을 뜻하지 않습니다. 프론트 탭 메모리 요구사항과 기존 요청 맥락 계약은 유지합니다.

<a id="open-decisions"></a>

## 구현에 적용한 결정과 후속 작업

| ID | 이번 백엔드 구현 | 남은 작업 |
| --- | --- | --- |
| D-01 | 목적별 입력 필드 허용 목록, `store=False`, tracing 비활성화, 안전한 오류 로그 | 운영 조직의 제공자·로그/백업 보존 설정 확인 |
| D-02 | 짧은 전송 잠금·현재 권한 검사, 서버 근거 참조, 결과 해시 재검증 | 프론트의 전체 답변 무효화·화면 재진입·복사 연결, 운영 프록시 확인 |
| D-03 | 공유 실행 메타데이터의 24시간 접근 만료·정리 CLI, 별도 일반 대화·메시지 보존, 조회/복원 API 없음 | 대화 보존/삭제·백업 정책, 운영 메타데이터 정리 스케줄과 장애 관측 |
| D-04 | 기본 90초·계정 동시 2개·시간당 30시도·최대 3회 시도, 도구 8회·자료 30개·계획 모델 6회·입력 18,000토큰·출력 4,096토큰·reasoning low | 실제 데이터의 지연·비용·품질 평가 후 설정 조정 |
| D-05 | 프로필 완성 여부와 무관하게 공개 탐색 허용, 사용자 입력 조건만 적용, 비공개 본인 프로필 자동 개인화 없음 | 추가 개인화가 필요할 때 기능 명세 검토 |

한도는 무제한 실행을 막는 운영 기본값이며 카드 수·지원 자격 같은 제품 정책과 구분합니다. 입력 토큰 한도는 모델 호출별, 출력 토큰 한도는 제공자 호출별이며 전체 실행은 모델/도구 호출 수와 시간 제한으로도 제한합니다. 정확한 설정 범위는 [Settings](../../backend/app/core/config.py)가 원본입니다.

## 검증과 인계

- [입력·이벤트 검사](../../backend/tests/unit/test_ai_contract.py): 1,000자·Unicode·권한 역할 입력 거부·맥락 상한·이벤트 페이로드·SSE OpenAPI.
- [HTTP·PostgreSQL 검사](../../backend/tests/integration/test_ai.py): 로그인/CSRF·타인 요청·비공개 지원자·실제 ID·중복·재시도·중단·세션 회수·전송 중 공개 철회·결과 위변조·프로필 버전·만료/정리.
- 대화 저장 검사: 현재 입력·완성 답변, 재시도 중복 방지, 실행 정리 후 보존, 다른 계정의 대화 추가 거부, 실패/단절/무효화된 부분 답변 제외, DB 저장 실패의 전체 롤백.
- [실제 모델 수동 검사](../../backend/tests/manual/check_ai_model.py): 가상 자료만으로 Luna 도구 호출·구조화 출력·답변 스트리밍 확인. 일반 pytest는 유료 모델을 호출하지 않음.
- 로컬 DB 검증은 격리된 PostgreSQL 18에서 수행합니다. Docker를 사용할 수 없어 Compose 기준 PostgreSQL 17.11은 이번 로컬 실행에 사용하지 않았습니다. 운영 DB에는 migration을 적용하지 않았습니다.

실행·정리 명령은 [AI 로컬 실행](../development/local-development.md#ai-backend)을 참조합니다. 프론트 AC-16·23·26·28·33·34의 실제 화면 동작과 브라우저 E2E, 실제 지원자 자료를 사용한 추천 품질 평가는 완료로 표시하지 않습니다. 백엔드는 PR #157로 main에 병합했습니다. 실제 AI 화면 연결은 [#163](https://github.com/wejo-team/sku-dreamon/issues/163), 실제 자료 품질·보존 정책은 [#164](https://github.com/wejo-team/sku-dreamon/issues/164), 운영 배포는 [#165](https://github.com/wejo-team/sku-dreamon/issues/165)에 남깁니다.

## 기술 근거

- [LangChain Agents](https://docs.langchain.com/oss/python/langchain/agents), [LangGraph 이전 안내](https://docs.langchain.com/oss/python/migrate/langgraph-v1): `create_agent` 진입점과 런타임.
- [Luna 모델](https://developers.openai.com/api/docs/models/gpt-6-luna), [ChatOpenAI](https://docs.langchain.com/oss/python/integrations/chat/openai): 모델 ID와 Responses API 연동.
- [구조화 출력](https://docs.langchain.com/oss/python/langchain/structured-output), [스트리밍](https://docs.langchain.com/oss/python/langchain/streaming): 모델 실행을 제품 계약으로 연결하는 근거.
