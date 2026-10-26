# 로컬 실행

앱을 처음 실행하거나 검사 명령이 필요할 때 읽습니다. 명령은 저장소 루트에서 시작하는 Bash·WSL/macOS 셸 기준입니다. Windows PowerShell에서는 환경변수 설정 문법을 해당 셸에 맞춥니다.

## 준비

- Node 버전은 `frontend/.nvmrc`의 22.22.1, npm은 9.2.0입니다. Node 버전 관리자로 해당 버전을 선택한 뒤 `npm install --global npm@9.2.0`을 실행합니다.
- Python은 `backend/.python-version`의 3.13.14, uv는 0.11.30입니다. uv가 필요한 Python을 설치하도록 할 수 있습니다.
- Docker Engine 또는 Docker Desktop과 Compose가 필요합니다. WSL에서 Docker Desktop을 쓰면 WSL 연동과 엔진 실행 상태를 확인합니다.
- 앱 의존성은 `frontend/package-lock.json`, `backend/uv.lock`으로 고정합니다. 루트 `package-lock.json`은 문서 사이트 전용이며 [문서 관리](documentation.md)의 명령으로 따로 설치합니다. 설치 중 lockfile을 임의로 갱신하지 않습니다.

## PostgreSQL

```bash
docker compose up -d --wait
```

기본 개발 DB는 `127.0.0.1:5432/wejo_dev`이며 사용자·암호는 `wejo`입니다. localhost에만 포트를 공개하며 이 값은 개발용입니다. 데이터는 Compose 볼륨에 유지됩니다.

| DB | 용도 | 연결 설정 |
| --- | --- | --- |
| `wejo_dev` | 앱을 직접 사용하며 확인하는 로컬 개발 데이터 | `backend/.env`의 `DATABASE_URL` |
| `wejo_test` | 자동 테스트의 데이터 생성·정리 | 셸의 `TEST_DATABASE_URL`, 테스트 migration에만 `DATABASE_URL` 임시 지정 |
| 운영 DB | 별도 배포 환경의 실제 데이터 | 배포 환경에서 주입하며 로컬 설정과 분리 |

5432 포트를 사용할 수 없다면 다른 포트로 실행합니다.

```bash
POSTGRES_PORT=55432 docker compose up -d --wait
```

이때 아래 백엔드 `.env`의 `DATABASE_URL` 포트도 55432로 바꿉니다. DB 포트 변경은 프론트의 API 프록시 주소와 무관합니다.

다음 실행에도 이 포트를 유지하려면 저장소 루트의 `.env`에 `POSTGRES_PORT=55432`를 저장합니다. 루트 `.env`는 Compose용이고 `backend/.env`는 백엔드용입니다. 두 파일 모두 Git에서 제외합니다. 이 경우 백엔드 주소는 `postgresql+asyncpg://wejo:wejo@127.0.0.1:55432/wejo_dev`입니다.

### 기존 `wejo` DB를 사용하던 경우

`POSTGRES_DB`는 비어 있는 볼륨을 처음 초기화할 때만 DB를 만듭니다. 기존 볼륨은 설정만 바꿔도 DB 이름이 바뀌지 않습니다. 기존 백엔드·DB 도구의 `wejo` 연결을 종료하고, `wejo_dev`가 아직 없는 경우에만 다음 명령으로 이름을 바꿉니다. 테이블과 데이터는 유지됩니다.

```bash
docker compose exec postgres psql -U wejo -d postgres -v ON_ERROR_STOP=1 \
  -c "ALTER DATABASE wejo RENAME TO wejo_dev;"
```

변경 후 기존 `backend/.env`의 `DATABASE_URL` 마지막 DB 이름을 `/wejo_dev`로 수정합니다. `.env` 전체를 복사해 덮어쓰지 않으며 API 키·인증 설정은 유지합니다. `wejo_dev`가 이미 있다면 위 이름 변경을 반복하지 않습니다. [PostgreSQL 이미지 초기화](https://hub.docker.com/_/postgres), [DB 이름 변경](https://www.postgresql.org/docs/17/sql-alterdatabase.html)을 참고합니다.

## 백엔드 — 별도 터미널

```bash
cd backend
cp -n .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run python -m app.core.db.check
uv run uvicorn app.main:app --reload
```

`cp -n`은 기존 `.env`를 덮어쓰지 않습니다. 기존 파일이 있다면 아래 DB 주소가 맞는지 직접 확인합니다. 포트를 변경했다면 주소의 포트도 맞춥니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:5432/wejo_dev
```

API는 `http://127.0.0.1:8000`, 대화형 API 문서는 `/docs`입니다. `GET /api/v1/health`는 `{"status":"ok"}`를 반환합니다. health는 프로세스 연결 확인이며 DB 준비 상태 검사가 아닙니다.

`upgrade head`는 계정·서버 세션, 학사, 공고, 프로필, 팀·지원·소속·발생 건·알림과 AI 실행 메타데이터·대화·메시지까지 migration 8개를 적용합니다. 현재 적용 대상은 [DB 인덱스](../database/README.md)와 [Alembic 모델 등록](../../backend/alembic/env.py)에서 확인합니다. 스키마 적용은 운영 학사 원장·공고·시연 데이터를 적재하지 않습니다. 모델 추가 방법은 [백엔드 가이드](backend.md)를 따릅니다.

개발용 데이터는 `wejo_dev`에 넣고 실제 API로 변경하면서 검증합니다. 공고 등록은 [공고 CLI](../api/contests.md#contest-import-cli), 가입·프로필·팀 생성은 각 [API](../api/README.md)를 사용합니다. 전체 예시 데이터를 한 번에 넣는 개발용 seed 명령은 아직 없습니다. 자동 테스트 fixture는 `wejo_test`에서 생성·정리하며 개발 DB의 예시 데이터를 대신하지 않습니다.

인증 HTTP는 가입·로그인·CSRF 조회·본인 계정 조회·로그아웃을 제공하며, 화면 연결은 별도 작업입니다. 전체 API 구현 범위는 [API 인덱스](../api/README.md)를 따릅니다. 인증 관련 요청을 검증할 환경에서는 `.env`의 `CSRF_SIGNING_KEY`에 32바이트 이상의 난수 키를 주입하고 `AUTH_ALLOWED_ORIGINS`에 정확한 HTTPS origin 목록을 설정합니다. 설정 형식은 [환경변수 예시](../../backend/.env.example), 검증은 [Settings](../../backend/app/core/config.py), 쿠키 속성은 [인증 쿠키 코드](../../backend/app/routers/auth_cookies.py)를 확인합니다.

## 프론트엔드 — 별도 터미널

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

`http://localhost:5173`에서 화면 시연 앱을 엽니다. 현재 로그인·프로필·팀·지원 등은 `DemoProvider`의 메모리 예시 데이터를 사용합니다. 실제 백엔드 연결 확인 화면은 `http://localhost:5173/health`이며, Vite 개발 서버가 `/api` 요청을 백엔드 8000 포트로 전달합니다. 연결 실패 시 오류를 표시하고 다시 확인할 수 있습니다. 화면별 API 연결은 후속 작업이며 [구현 현황](implementation-status.md)에서 구분합니다.

`VITE_API_BASE_URL`은 브라우저에 노출되는 API 경로입니다. `API_PROXY_TARGET`은 Vite 개발 서버만 사용합니다. 위 HTTP 주소는 화면 시연·연결 확인용이며 현재 프론트에 가입·로그인 흐름이 연결된 것은 아닙니다. 서버의 인증 쿠키는 `Secure`를 유지하므로 브라우저 인증 검증에는 HTTPS 구성이 필요합니다. 운영 API 연결 방식·도메인·CORS와 로컬 HTTPS 구성은 후속 범위이며, 인증 전송 설계는 별도 [PR #124](https://github.com/wejo-team/sku-dreamon/pull/124)에서 확인합니다.

## 검사

프론트 폴더에서:

```bash
npm run lint
npm run format:check
npm run typecheck
npm test
npm run build
```

백엔드 폴더에서:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest
uv run alembic check
```

유닛 테스트만 실행하려면 `uv run pytest tests/unit`, DB 없이 HTTP 통합만 확인하려면 `uv run pytest tests/integration -m "not database"`를 사용합니다. 전체 테스트는 위의 `uv run pytest`로 실행합니다. `integration` marker는 HTTP·DB 경계 검사를, `database` marker는 전용 PostgreSQL이 필요한 검사를 뜻합니다.

`pytest`는 `TEST_DATABASE_URL`이 없으면 DB 통합 테스트를 건너뜁니다. 전체 DB 검증에는 전용 테스트 DB를 만듭니다. 아래 생성 명령은 저장소 루트에서 한 번만 실행합니다.

```bash
docker compose exec postgres createdb -U wejo wejo_test
```

그다음 백엔드 폴더에서 테스트 DB의 실제 포트에 맞춰 실행합니다. `TEST_DATABASE_URL`은 명시적으로 셸에 설정하며 `.env`에서 자동으로 읽지 않습니다.

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:5432/wejo_test
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic check
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m app.core.db.check
uv run pytest
```

통합 테스트는 전용 DB에 고유 테스트 스키마를 만들고 정리합니다. 실제 서비스 DB나 운영 DB를 지정하지 않습니다. 문서 검사는 [문서 관리](documentation.md)의 명령을 사용합니다.

## 종료

프론트·백엔드는 각 터미널에서 Ctrl+C로 종료합니다. DB는 저장소 루트에서 `docker compose stop`으로 멈추며 데이터 볼륨은 유지됩니다.

<a id="ai-backend"></a>

## AI 백엔드 실행과 검사

AI 백엔드는 `backend/.env`의 `OPENAI_API_KEY`를 읽습니다. 키는 Python 파일·프론트 환경변수에 넣지 않으며 `.env`는 Git에서 제외합니다. `uv sync --locked` 후 `uv run alembic upgrade head`로 AI 실행 메타데이터 migration까지 적용하고 서버를 실행합니다. 실제 서버에는 이전과 같은 HTTPS Origin·CSRF·세션 쿠키가 필요합니다.

모델은 `gpt-6-luna`, Responses API, `store=False`로 연결합니다. 키가 없으면 일반 서버는 시작하지만 AI 생성 요청은 503을 반환합니다. 프론트 로그인·AI 화면은 이번 백엔드 작업에 연결하지 않았습니다. 정확한 경로·본문·SSE 이벤트는 [AI API](../api/ai.md)와 실행 앱의 `/docs`·`/openapi.json`에서 확인합니다.

| 설정 | 기본값 | 의미 |
| --- | --- | --- |
| `AI_REASONING_EFFORT` | `low` | 모델 추론 강도 |
| `AI_TIMEOUT_SECONDS` | 90 | 한 실행 시도의 전체 기한 |
| `AI_RETENTION_SECONDS` | 86400 | 실행 메타데이터 접근 만료까지의 초 |
| `AI_MAX_INPUT_TOKENS` | 18000 | 모델 호출별 입력 예산 |
| `AI_MAX_OUTPUT_TOKENS` | 4096 | 모델 호출별 출력 한도 |
| `AI_MAX_TOOL_CALLS` / `AI_MAX_SOURCES` | 8 / 30 | 한 실행의 도구 호출·자료 수 |
| `AI_CONCURRENT_REQUESTS` / `AI_REQUESTS_PER_HOUR` | 2 / 30 | 계정별 동시 실행·최근 시도 제한 |

계획 단계는 최대 6회 모델 호출, 한 요청은 최초 실행을 포함해 최대 3회 시도합니다. 시간 제한·일시 장애는 실패 재시도, 입력/도구 예산 초과는 조건 수정 후 새 요청으로 처리합니다. 설정의 허용 범위는 [Settings](../../backend/app/core/config.py)가 원본입니다.

일반 테스트는 가짜 모델과 격리 PostgreSQL로 검사합니다. 실제 모델 수동 검사는 아래 명령을 **명시적으로 실행할 때만** OpenAI API를 호출하며 과금될 수 있습니다. 가상 자료만 보내고 키·생성 원문은 출력하지 않습니다.

```bash
cd backend
uv run pytest tests/unit/test_ai_contract.py
# TEST_DATABASE_URL을 격리된 테스트 DB로 지정한 상태에서 실행합니다.
uv run pytest tests/integration/test_ai.py
# 실제 Luna 도구 호출·구조화 출력·스트리밍 검사
PYTHONPATH=. uv run python tests/manual/check_ai_model.py
```

만료된 실행 메타데이터는 새 요청 접수 또는 다음 운영 명령에서 정리합니다. 유휴 시간에도 물리 삭제가 필요하면 운영 스케줄러에서 정기 실행합니다. 이 명령은 LLM을 호출하지 않으며 대화·메시지도 삭제하지 않습니다. 일반 채팅 원문은 별도 보존 기간 결정 전까지 자동 만료하지 않습니다.

```bash
cd backend
uv run python -m app.cli.ai_runs
```

운영 프록시는 SSE를 버퍼링하지 않아야 하며 연결 기한·10초 heartbeat·클라이언트 연결 종료를 실제 환경에서 확인합니다. `done` 전 연결 단절은 성공이 아니며 이미 완료된 본문은 서버에서 복원하지 않습니다. 상태 확인·새 실행·복사 재검증은 [클라이언트 계약](../api/ai.md)을 따릅니다.
