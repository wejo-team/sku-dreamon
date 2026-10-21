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

기본 개발 DB는 `127.0.0.1:5432`, DB·사용자·암호는 모두 `wejo`입니다. localhost에만 포트를 공개하며 이 값은 개발용입니다. 데이터는 Compose 볼륨에 유지됩니다.

5432 포트를 사용할 수 없다면 다른 포트로 실행합니다.

```bash
POSTGRES_PORT=55432 docker compose up -d --wait
```

이때 아래 백엔드 `.env`의 `DATABASE_URL` 포트도 55432로 바꿉니다. DB 포트 변경은 프론트의 API 프록시 주소와 무관합니다.

## 백엔드 — 별도 터미널

```bash
cd backend
cp .env.example .env
uv sync --locked
uv run alembic upgrade head
uv run python -m app.db.check
uv run uvicorn app.main:app --reload
```

API는 `http://127.0.0.1:8000`, 대화형 API 문서는 `/docs`입니다. `GET /api/v1/health`는 `{"status":"ok"}`를 반환합니다. health는 프로세스 연결 확인이며 DB 준비 상태 검사가 아닙니다.

도메인 모델과 최초 migration은 아직 없습니다. `upgrade head`는 현재 비동기 Alembic 연결 경로를 실행하며 서비스 테이블을 생성하지 않습니다. 모델 추가 방법은 [백엔드 가이드](backend.md)를 따릅니다.

## 프론트엔드 — 별도 터미널

```bash
cd frontend
cp .env.example .env
npm ci
npm run dev
```

`http://localhost:5173`에서 연결 확인 화면을 엽니다. Vite 개발 서버가 `/api` 요청을 백엔드 8000 포트로 전달합니다. API 실패 시 오류를 표시하고 다시 확인할 수 있습니다.

`VITE_API_BASE_URL`은 브라우저에 노출되는 API 경로입니다. `API_PROXY_TARGET`은 Vite 개발 서버만 사용합니다. 인증은 [서버 세션 쿠키](../specs/authentication.md#session-policy)로 결정했으며 아직 구현하지 않았습니다. 운영 배포의 API 연결 방식·도메인·CORS와 보안 쿠키를 검증할 로컬 HTTPS 구성은 후속 개발 계획에서 정합니다.

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

`pytest`는 `TEST_DATABASE_URL`이 없으면 DB 통합 테스트를 건너뜁니다. 전체 DB 검증에는 전용 테스트 DB를 만듭니다. 아래 생성 명령은 저장소 루트에서 한 번만 실행합니다.

```bash
docker compose exec postgres createdb -U wejo wejo_test
```

그다음 백엔드 폴더에서 테스트 DB의 실제 포트에 맞춰 실행합니다. `TEST_DATABASE_URL`은 명시적으로 셸에 설정하며 `.env`에서 자동으로 읽지 않습니다.

```bash
export TEST_DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:5432/wejo_test
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic upgrade head
DATABASE_URL="$TEST_DATABASE_URL" uv run alembic check
DATABASE_URL="$TEST_DATABASE_URL" uv run python -m app.db.check
uv run pytest
```

통합 테스트는 전용 DB에 고유 테스트 스키마를 만들고 정리합니다. 실제 서비스 DB나 운영 DB를 지정하지 않습니다. 문서 검사는 [문서 관리](documentation.md)의 명령을 사용합니다.

## 종료

프론트·백엔드는 각 터미널에서 Ctrl+C로 종료합니다. DB는 저장소 루트에서 `docker compose stop`으로 멈추며 데이터 볼륨은 유지됩니다.
