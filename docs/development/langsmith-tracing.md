# LangSmith 실행 추적

AI 생성의 어느 단계가 오래 걸렸는지, 모델·도구 호출이 실패하거나 취소됐는지와 제공된 토큰 사용량을 확인하는 선택 기능입니다. 기본값은 비활성화이며, 명시적으로 켜도 입력·답변·조회 자료의 원문을 전송하지 않습니다. 기능·권한·저장 계약은 [AI 아키텍처](ai-architecture.md)와 [AI API](../api/ai.md)를 유지합니다.

## 검토한 범위와 선택

[품질·비용·보존 후속 #164](https://github.com/wejo-team/sku-dreamon/issues/164), [실행·데이터 경계 #114](https://github.com/wejo-team/sku-dreamon/issues/114), [입력 가드·ReAct PR #206](https://github.com/wejo-team/sku-dreamon/pull/206)을 함께 검토했습니다. 2026-10-30 사용자 요청에 따라 아래 계측과 문서·검증을 구현하며, 실제 품질 평가나 운영 배포가 끝났다는 의미는 아닙니다.

| 선택 | 이유와 범위 |
| --- | --- |
| 기본 비활성화, 별도 키·프로젝트로 명시적 활성화 | 기존 실행과 외부 전송 경계를 유지 |
| 새 루트 trace와 모델·도구 자식 span | 가드·ReAct·최종 답변·도구의 시간·상태·사용량 구분 |
| 수동 허용 목록 전송 | 자동 tracer의 입출력 숨김만으로는 예외·직렬화·환경 metadata를 모두 차단할 수 없음 |
| 크기가 제한된 앱 큐와 제한된 종료 대기 | 추적 실패를 AI 실패로 바꾸거나 SSE에서 원격 전송 완료를 기다리지 않음 |
| 설정 재배포·백업 키 제외 | 기존 운영 설정 경로로 적용하고 외부 API 키를 백업 archive에 추가하지 않음 |

원문 debugging, 임의 tags/metadata, 전체 LangGraph 내부 노드, 영속 checkpoint, 사용자별 대화 묶음, 품질 평가 dataset·annotation·prompt 관리 기능은 추가하지 않습니다. #164의 실제 자료 평가·대화 삭제/보존·운영 실행 정리는 별도 후속입니다.

## 전송 데이터와 실행의 의미

[계측 구현](../../backend/app/agents/tracing.py)은 LangChain callback에서 필요한 값을 새 payload로 만듭니다. LangSmith에 입력·출력은 빈 객체로 보내며 SDK에서도 숨김을 적용합니다. 자동 LangChain tracing과 SDK의 runtime/environment metadata 수집은 차단합니다.

| 전송하는 값 | 전송하지 않는 값 |
| --- | --- |
| 새 임의 trace/span UUID, 부모 관계와 시작·종료 시각 | 요청·계정·세션·대화·팀·지원·자료의 원래 ID |
| 목적, 시도 번호, 고정 단계·허용한 도구 이름 | 사용자 입력·history·system prompt·도구 인자/결과·프로필·추천 이유·답변 |
| 고정 종료 분류, 모델 이름, 제공된 정수 토큰 수 | 예외 문자열·traceback·제공자 응답 객체·임의 metadata/tags·키 |

루트는 **한 생성 시도**이며 재시도마다 새 추적 UUID를 만듭니다. 입력 가드는 일반 채팅에서만 실행합니다. 모델 자식은 `input_guard`, `react_model`, `final_answer`로, 도구 자식은 서버의 허용 목록 이름으로 구분합니다. 그래프 내부 노드를 제외하므로 모델·도구 span은 모두 같은 루트 아래에 놓입니다. 공급자가 사용량을 반환하지 않으면 추정 토큰을 만들어 넣지 않습니다. 표시되는 비용은 프로젝트의 모델 가격 매핑 등에 의존하며 청구서와 같은 값임을 보장하지 않습니다.

루트의 `completed`는 드라이버가 검증된 최종 생성을 마쳤다는 뜻입니다. 이후 DB 저장·최종 권한 검사·SSE `done` 수신을 보장하지 않으며 제품 성공 여부는 기존 실행 상태와 이벤트로 확인합니다. 고정 정책 안내는 `blocked`, 생성 실패는 `failed`, 작업 취소·생성기 종료는 `canceled`로 구분합니다. 원격 전송 실패·프로세스 강제 종료·큐 포화에는 trace가 누락될 수 있으므로 감사 로그나 업무 상태의 원본으로 쓰지 않습니다.

로컬의 `AI trace request_id=... attempt=... trace_id=...` 로그로 기존 실행 로그와 LangSmith trace를 연결합니다. `request_id`는 외부 payload에 복사하지 않습니다. 외부 trace의 접근 권한과 보존 기간은 앱 DB의 24시간 실행 메타데이터 만료와 별개입니다.

## 설정

원본은 [Settings](../../backend/app/core/config.py)와 [환경변수 예시](../../backend/.env.example)입니다. 로컬에서는 Git에서 제외된 `backend/.env`에 설정하고 서버를 재시작합니다. LangSmith 키는 OpenAI 키와 별도이며 브라우저의 `VITE_*` 설정에 넣지 않습니다.

| 설정 | 기본값·조건 |
| --- | --- |
| `LANGSMITH_TRACING` | `false`. `true`일 때만 앱 소유 계측 Client 생성 |
| `LANGSMITH_API_KEY` | 기본 없음. 활성화하면 빈 값·공백을 허용하지 않음 |
| `LANGSMITH_PROJECT` | `sku-dreamon`. 비어 있지 않은 단일 행, 최대 100자 |
| `LANGSMITH_ENDPOINT` | `https://api.smith.langchain.com`. HTTPS, 사용자정보·query·fragment 금지 |
| `LANGSMITH_WORKSPACE_ID` | 기본 없음. 여러 workspace를 사용하는 조직 키라면 대상 UUID 명시 |

프로젝트는 환경별로 구분하고, endpoint는 조직의 LangSmith 리전에 맞춥니다. 앱은 설정한 단일 목적지에 전송하며 SDK의 다른 자동 목적지·샘플링 환경변수를 운영 설정으로 사용하지 않습니다. 기존 OpenAI 키와 AI 활성화 조건도 별도로 충족해야 생성 trace가 생깁니다. 키·프로젝트·네트워크의 실제 유효성은 설정 검증이나 `/ready`만으로 확인되지 않습니다.

요청은 최대 256개의 작업을 담는 앱 큐에 즉시 추가하고 원격 응답을 기다리지 않습니다. 프로세스의 단일 daemon worker가 SDK 단건 API를 순서대로 호출합니다. SDK 자동 배치는 별도 재시도·429 대기를 추가하므로 사용하지 않습니다. 단건 요청의 timeout은 connect/read 각각 1초, 재시도는 0회입니다. 앱 종료 시 최대 2초와 기존 앱 종료 예산 중 작은 값까지 기다리고, 남은 미전송 작업은 폐기합니다. 진행 중 HTTP는 daemon worker에서 끝나므로 프로세스 종료를 붙잡지 않습니다. 추적 초기화·큐 포화·전송·종료 실패에는 고정된 로그만 남기고 제품 요청을 계속 처리합니다. 잘못된 명시 설정은 기동 시 검증 오류로 처리합니다.

운영에서는 이 코드를 `develop → main`으로 릴리스한 뒤 [SSM 설정 재배포](ssm-configuration.md)의 전체 SecureString bundle에 값을 넣고 정확한 버전을 적용합니다. `LANGSMITH_TRACING=false`로 변경 후 재배포하면 새 전송을 끕니다. 이미 전송한 trace는 삭제되지 않으므로 LangSmith 프로젝트에서 별도로 관리합니다. 키는 [백업 제외·버전별 재주입](production-backups.md) 절차를 따릅니다.

## 검증과 운영 인계

[계측 회귀](../../backend/tests/unit/test_ai_tracing.py)는 가짜 모델·Client로 opt-in/opt-out, 부모 관계, 허용 필드, 오류·취소와 비밀 원문 제외를 검사합니다. [런타임 회귀](../../backend/tests/unit/test_ai_runtime.py)와 [수명 회귀](../../backend/tests/integration/test_deployment_lifespan.py)는 실시간 전달·취소·종료 자원 정리를 함께 확인합니다. 배포 검사는 설정 apply/rollback과 archive에서의 키 제외를 확인합니다. 일반 검사는 실제 OpenAI·LangSmith로 데이터를 보내지 않습니다.

```bash
cd backend
uv sync --locked
uv run pytest tests/unit/test_ai_tracing.py tests/unit/test_ai_runtime.py
```

실제 서비스 확인은 승인된 환경의 가상 요청으로 수행합니다. 프로젝트에서 새 루트와 모델·도구 하위 실행, 비어 있는 Inputs/Outputs, 허용한 metadata만 있는지 확인하고 로컬 `trace_id`로 연결합니다. 실제 키 유효성·클라우드 수신·프로젝트 접근/보존 설정과 실제 자료의 비용·품질 평가는 자동 검사와 별도입니다. 이 변경에서는 운영 키 등록, 실제 LangSmith 전송과 운영 배포를 수행하지 않았습니다.

## 기술 근거

- [LangChain 추적 설정](https://docs.langchain.com/langsmith/trace-with-langchain)
- [입출력 숨김과 민감정보](https://docs.langchain.com/langsmith/mask-inputs-outputs)
- [환경변수 없이 Client·workspace 지정](https://docs.langchain.com/langsmith/trace-without-env-vars)
- [LLM 실행과 토큰 사용량](https://docs.langchain.com/langsmith/log-llm-trace)

현재 lockfile의 Python LangSmith 0.14.12 API를 기준으로 구현합니다. 동기 SDK 호출과 Client 정리는 앱의 전송 worker가 소유합니다. SDK 갱신 시 단건 API의 timeout·재시도와 metadata 제외·종료 검사를 함께 재검증합니다.
