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

`upgrade head`는 계정·서버 세션, 학사, 공고, 프로필, 팀·지원·소속·발생 건·알림과 AI 실행 메타데이터·대화·메시지까지 migration 9개를 적용합니다. 현재 적용 대상은 [DB 인덱스](../database/README.md)와 [Alembic 모델 등록](../../backend/alembic/env.py)에서 확인합니다. 스키마 적용은 운영 학사 원장·공고·시연 데이터를 적재하지 않습니다. 모델 추가 방법은 [백엔드 가이드](backend.md)를 따릅니다.

개발용 데이터는 `wejo_dev`에 넣고 실제 API로 변경하면서 검증합니다. 공고 등록은 [공고 CLI](../api/contests.md#contest-import-cli), 가입·프로필·팀 생성은 각 [API](../api/README.md)를 사용합니다. 자동 테스트 fixture는 `wejo_test`에서 생성·정리하며 개발 DB의 예시 데이터를 대신하지 않습니다.

개발용 사용자·팀 예시 데이터는 백엔드 폴더에서 다음 명령으로 준비합니다. [시드 스크립트](../../backend/scripts/seed_dev_data.py)는 로컬 `wejo_dev`만 허용하고, 기본 실행은 전체 데이터를 생성·검증한 뒤 롤백합니다.

```bash
uv run python -m scripts.seed_dev_data
uv run python -m scripts.seed_dev_data --apply
# 공고 적재가 진행 중이면 사용자부터 준비할 수 있습니다.
uv run python -m scripts.seed_dev_data --users-only --apply
```

계정은 `devuser001`~`devuser300`, 개발용 공통 비밀번호는 `WejoDev2026!Demo`입니다. 공개 프로필 240개와 비공개 60개, 관심 분야·역할·역량·경험·선택 포트폴리오를 생성합니다. 자연스러운 가상 이름과 프로젝트 문장을 사용하되, 이름에는 `[테스트 P001]`, 팀명에는 `[테스트 T001]` 형태의 고정 식별자를 붙입니다. 이름과 경력은 가상이며, 포트폴리오는 `example.com` 예시 URL입니다. 계정별 비밀번호는 서로 다른 salt의 Argon2id 해시로 저장합니다. 이 계정은 실제 백엔드 인증용이며 프론트 시연 화면의 고정 데모 로그인 계정과 다릅니다. 프론트에서 사용하려면 실제 서버 모드 전환과 HTTPS·CSRF 설정이 필요합니다.

공통 카탈로그 7종은 서버 enum을 사용하므로 별도 코드 테이블을 적재하지 않습니다. 학사 데이터는 [학사 명세의 31행 이관 목록](../specs/academic-structure.md#catalog)을 읽어 단과대학 6개·학부/학과 31개·전공 57개, 총 94개를 `academic_units`에 넣습니다. 이름과 부모 관계를 보존하고, 동명 학과를 합치거나 `전공 미배정` 항목을 만들지 않습니다. 이번 적재는 **문서 목록을 사용하는 로컬 개발·시연용**이며, 문서의 현행 학년도·공식 원장 검증이 완료되었다는 뜻은 아닙니다. 기존 경로가 한 개라면 ID를 재사용하고, 중복 경로나 비활성 항목을 만나면 임의 변경 없이 실패합니다.

공고·분야·참가 대상 데이터는 생성·수정하지 않습니다. 기존 공고 중 현재 접수 중이며 마감이 1시간 넘게 남고 2명 이상 팀의 참가 인원 조건이 확인된 공고에 최대 100개 팀과 지원·소속·상태 변경 사건·읽음/미읽음 알림을 연결합니다. 적합한 공고가 없으면 사용자만 넣고 안내를 출력합니다. 이후 공고 적재가 완료되면 같은 명령을 다시 실행하면 됩니다. 선발·취소·검토·미선발은 제품 서비스를 호출해 실제 상태 전이와 알림 규칙을 적용합니다. AI 호출·가상 AI 실행 결과는 생성하지 않습니다.

고정 UUID는 [시연 데이터 목록](../../backend/app/core/demo_data.py)에서 관리하며 API의 `isDemo`에 반영합니다. 재실행은 기존 시드 계정·팀을 건너뛰고 사용자가 편집한 프로필이나 상태를 보존합니다. 일반 계정을 덮어쓰거나 기존 데이터를 지우지 않으며, 한 실행에서 발생한 오류는 해당 실행 전체를 롤백합니다. 동시 시드 실행은 PostgreSQL advisory lock으로 직렬화합니다.

이전 시드의 이름·소개를 새 가상 콘텐츠로 바꾸려면 별도 갱신 모드를 사용합니다. 기본 실행은 변경 예정 건수를 확인한 뒤 롤백하며 `--apply`가 있어야 저장합니다.

```bash
uv run python -m scripts.seed_dev_data --refresh-content
uv run python -m scripts.seed_dev_data --refresh-content --apply
```

이 모드는 새 행을 만들지 않습니다. 고정 시드 ID·계정과 구버전 콘텐츠가 일치하는 행만 갱신하고, 사용자가 편집한 프로필·팀은 건너뜁니다. 로그인 ID·암호·UUID·팀 상태·지원·알림은 유지하며 변경한 프로필·팀의 version과 수정 시각을 함께 올립니다. 다시 실행해 이미 갱신한 콘텐츠를 덮어쓰지 않습니다. 비교 기준과 새 문구는 [시드 콘텐츠](../../backend/scripts/seed_content.py)에 있습니다.

기존 개발 공고의 포스터 주소가 비어 있다면 [포스터 복구 도구](../../backend/scripts/backfill_contest_posters.py)를 사용합니다. 아래 명령은 백엔드 `.env`의 명시적 로컬 `wejo_dev`에 연결하며, 첫 실행은 DB를 변경하지 않고 원본과 이미지 응답을 확인한 계획 파일을 출력합니다.

```bash
uv run --env-file .env python -m scripts.backfill_contest_posters --limit 20
# 첫 명령이 출력한 실제 계획 경로로 바꿉니다.
uv run --env-file .env python -m scripts.backfill_contest_posters --apply '../.bugbash/explore-feedback/posters/plan-<출력된시각>.json'
# 일시 실패를 다시 확인할 때만 명시적으로 사용합니다.
uv run --env-file .env python -m scripts.backfill_contest_posters --limit 20 --retry-failed
```

이 도구는 기존 Linkareer 출처의 대표 포스터를 복구하는 로컬 보조 도구이며, [운영 수집 방식](../specs/contests.md#operation-flow)을 확정하지 않습니다. 원문의 canonical URL·제목·대표 이미지, 허용 이미지 주소·응답 종류·크기를 확인합니다. 외부 요청은 초당 최대 1회, 자동 재시도 없이 처리하며 429 응답이면 수집을 중단합니다. 기본 재실행은 캐시를 사용하고 `--retry-failed`일 때만 실패 건을 다시 확인합니다. 계획·원문 근거·복구 기록은 Git에서 제외된 `.bugbash/explore-feedback/posters/`에 저장합니다.

적용은 포스터가 비어 있고 계획 작성 당시의 행과 여전히 같은 공고만 한 트랜잭션에서 처리합니다. 변경된 행을 만나면 전체 적용을 중단합니다. `poster_url`·version·수정 시각만 바꾸며 공식 URL·원문·등록 전 확인 상태는 유지합니다. 원문이나 이미지 확인이 실패한 공고와 화면에서 이미지 로드가 실패한 경우에는 기존 기본 커버를 유지합니다.

인증 HTTP는 가입·로그인·CSRF 조회·본인 계정 조회·로그아웃을 제공하며, 비AI 화면은 API 호출에 연결되어 있습니다. 전체 API 구현 범위는 [API 인덱스](../api/README.md)를 따릅니다. 인증 검증에는 `.env`의 `CSRF_SIGNING_KEY`에 32바이트 이상의 난수 키를 주입하고 `AUTH_ALLOWED_ORIGINS`에 정확한 HTTPS origin 목록을 설정합니다. 신규 가입에는 `PASSWORD_BLOCKLIST_PATH`·`PASSWORD_BLOCKLIST_VERSION`도 필요합니다. 설정 형식은 [환경변수 예시](../../backend/.env.example), 검증은 [Settings](../../backend/app/core/config.py), 쿠키 속성은 [인증 쿠키 코드](../../backend/app/routers/auth_cookies.py)를 확인합니다. 별도 DB·HTTPS·가상 자료를 함께 준비하는 명령은 [통합테스트와 bug bash](bug-bash.md)에 있습니다.

## 프론트엔드 — 별도 터미널

```bash
cd frontend
cp -n .env.example .env
npm ci
npm run dev
```

`http://localhost:5173`에서 화면을 엽니다. `.env.example`의 기본값 `VITE_API_MOCK=true`는 메모리 목업 API를 사용합니다. 인증·프로필·탐색·팀·지원·알림의 화면 API 계층은 연결됐으며, 실제 서버 검증에는 `VITE_API_MOCK=false`와 HTTPS 설정 후 개발 서버를 재시작합니다. AI 대화·지원자 검토·지원자 추천도 이 설정에서 실제 서버에 연결됩니다. `VITE_API_MOCK=true`에서만 모의 대화를 사용합니다. [구현 현황](implementation-status.md)에서 구분합니다.

`VITE_API_BASE_URL`은 브라우저에 노출되는 API 경로입니다. `API_PROXY_TARGET`은 Vite 개발 서버만 사용하며 기본값은 백엔드 8000 포트입니다. `DEV_HTTPS_CERT`·`DEV_HTTPS_KEY`를 모두 지정하면 HTTPS로 실행합니다. 서버의 Secure 쿠키·CSRF 검사는 유지하므로 HTTP 화면 시연을 실제 인증 검증으로 취급하지 않습니다. `/health`는 연결 확인 화면이며 DB 준비·인증 성공을 보장하지 않습니다. 실제 HTTPS 프록시 실행은 [bug bash 안내](bug-bash.md), 전송 계약은 [PR #124](https://github.com/wejo-team/sku-dreamon/pull/124)를 따릅니다.

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

모델은 `gpt-6-luna`, Responses API, `store=False`로 연결합니다. 키가 없으면 일반 서버는 시작하지만 AI 생성 요청은 503을 반환합니다. `VITE_API_MOCK=false`에서 로그인 후 AI 탭의 자연어 대화, 팀장의 지원자 상세 AI 검토, 팀 공간의 AI 지원자 추천을 이용합니다. 생성 버튼을 누르면 실제 모델 요청이 발생하며, 자동 생성·실패 자동 재전송은 하지 않습니다. 키가 없는 경우 화면에 준비되지 않았다는 안내를 표시하고 모의 답변으로 대체하지 않습니다. 대화·초안은 현재 탭 메모리에서만 유지하며 새로고침·새 대화·로그아웃 시 초기화합니다. 무료 자동 회귀 검사는 [AI 브라우저 통합](bug-bash.md#ai-e2e)을 따릅니다. 정확한 경로·본문·SSE 이벤트는 [AI API](../api/ai.md)와 실행 앱의 `/docs`·`/openapi.json`에서 확인합니다.

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
