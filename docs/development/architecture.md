# 구조와 초기 실행 기반

현재 React 개발 연결 화면, FastAPI health API, 비동기 PostgreSQL 연결·Alembic과 CI가 있습니다. 아래는 폴더의 책임 지도이며, 도메인의 `models.py`·`service.py`와 프론트의 `e2e/` 등은 해당 코드가 필요할 때 추가합니다. 빈 기능 폴더를 미리 늘리지 않습니다.

```text
frontend/
  src/
    app/                 # router와 provider 조립
    pages/               # URL에 대응하는 화면 조립
    features/            # 기능별 UI·API·query·검증
    components/ui/       # shadcn/ui 기본 컴포넌트
    components/layout/   # 공통 화면 틀
    lib/                 # 공통 HTTP·환경설정·QueryClient
    styles/              # 전역 스타일·디자인 토큰
    main.tsx
  e2e/                   # 핵심 사용자 흐름이 생길 때
  .env.example
  .nvmrc
  package.json
  package-lock.json
backend/
  app/
    core/                # 도메인이 함께 사용하는 기반
      config.py          # 환경설정
      exceptions.py      # 애플리케이션 오류 정의
      db/                # ORM metadata·선택 컬럼, 비동기 엔진·세션, 연결 검사
      http/              # 공통 DTO·응답, 예외 핸들러, 요청 의존성
    domains/
      health/            # 현재 구현된 health API
        router.py
        schemas.py
      <기능>/            # 구현 시 router.py·schemas.py와 필요한 models.py·service.py 추가
    main.py              # 앱 생성·lifespan·라우터 연결
  alembic/versions/      # DB 변경 이력
  tests/                 # unit / integration (HTTP·PostgreSQL)
  .env.example
  .python-version
  pyproject.toml
  uv.lock
docs/                    # 작업별 인덱스·명세·개발 및 에이전트 가이드
  .vitepress/            # 문서 사이트 설정·테마
scripts/                 # CI 영향 범위·필수 결과 판별, 문서·사이트 검증
.github/workflows/        # 앱 CI와 문서·Pages workflow
package.json             # VitePress 문서 도구 전용
package-lock.json
compose.yaml             # 개발용 PostgreSQL
```

<a id="responsibility-boundaries"></a>

## 책임 경계

- 프론트 `app`은 router와 provider를 연결하고, `pages`는 기능을 조합합니다. 기능 내부 API·query·form schema는 `features/<기능>/`에 모읍니다.
- 공통 UI는 특정 기능의 API나 query에 의존하지 않습니다. 여러 기능이 사용하는 코드만 공통 위치로 옮깁니다.
- `lib`에는 앱 전반의 작은 기반 코드만 둡니다. 기능 규칙을 넣는 만능 폴더로 사용하지 않습니다.
- 백엔드 `domains/<기능>/`에 해당 기능의 라우터·요청과 응답 스키마·ORM 모델·서비스를 모읍니다. 라우터는 HTTP 처리, 서비스는 업무 규칙과 쓰기 트랜잭션을 담당합니다. ORM 모델과 요청·응답 스키마를 분리하며, 실제로 필요한 파일만 만듭니다.
- `core`는 여러 도메인이 사용하는 기반입니다. ORM의 공통 metadata·선택 컬럼과 엔진·세션은 `core/db`, 공통 DTO·응답·예외 핸들러·요청 의존성은 `core/http`에 둡니다. [공통 기반의 책임](backend.md#orm-foundation)에 따라 모델의 PK·컬럼을 선택하며 모든 모델에 같은 `id`·시각 컬럼을 강제하지 않습니다.
- 의존 방향은 도메인에서 `core`로 향합니다. `core`는 개별 도메인을 import하지 않고, `core/db`는 FastAPI·Starlette나 `core/http`를 import하지 않습니다. 요청에서 DB 세션을 꺼내는 처리는 `core/http/dependencies.py`, 엔진·세션 생성은 `core/db/session.py`, 앱 수명과 라우터 연결은 `main.py`가 맡습니다.
- 반복되거나 복잡한 DB 쿼리가 생기면 해당 도메인에 `repository.py`를 추가합니다. 여러 도메인에서 실제로 반복되는 기능만 검토해 공통화하며, 모든 기능에 Repository·Factory·interface를 의무화하지 않습니다.
- 프론트와 백엔드는 HTTP API를 통해 연결합니다. 백엔드 DB 구조를 그대로 프론트의 내부 상태 구조로 강제하지 않습니다.

## 개발 환경

- PostgreSQL은 루트 Compose로 실행하고, 프론트·백엔드 개발 서버는 각 폴더에서 실행합니다.
- 프론트 API 기본 경로는 `/api/v1`입니다. 개발 환경에서는 Vite의 `/api` 프록시가 FastAPI로 전달합니다. 운영 환경 연결 방식은 배포 플랫폼 확정 시 정합니다.
- 환경변수 예시는 프론트·백엔드 각각 제공합니다. Compose의 개발 DB 설정과 백엔드 DATABASE_URL의 일치 여부를 실행 검증에 포함합니다.
- Node와 Python은 버전 파일로, npm 패키지와 Python 의존성은 각 lockfile로 고정합니다.

## 실행 기반의 구성

1. 실행 기반: 런타임 버전·의존성·환경변수 예시·PostgreSQL Compose.
2. 백엔드: 앱 생성, 설정 로딩, async DB 세션, Alembic 환경, health API.
3. 프론트: router·provider·모바일 레이아웃·공통 HTTP 클라이언트·백엔드 연결 확인.
4. 검사: formatter·linter·타입 검사와 실제 코드에 대한 테스트, GitHub Actions 연결.
5. 문서: [로컬 실행](local-development.md)에 설치·실행·검사·마이그레이션 명령 기록.

초기 health 응답은 `/api/v1/health`에서 `{"status":"ok"}`로 고정합니다. DB 연결 가능 여부는 별도 연결 검사로 확인하며, health 응답만으로 DB 정상 여부를 주장하지 않습니다.

도메인 테이블과 첫 revision은 데이터 모델을 정할 때 추가합니다. 로그인·모집·지원 화면을 완성한 것처럼 보이는 임시 기능은 만들지 않습니다. 개발 연결 확인 UI는 첫 실제 화면 도입 시 제거합니다.

## 완료 기준

- 새 환경에서 문서대로 의존성 설치와 PostgreSQL 실행을 재현할 수 있습니다.
- 모바일 기본 화면에서 FastAPI 요청의 성공·실패를 확인할 수 있습니다.
- 비동기 DB 연결과 Alembic 실행 경로를 검증합니다.
- 구현된 범위의 검사와 빌드가 통과하고, 아직 설정하지 않은 검사를 구분해 보고합니다.
- 폴더·명령·환경변수 설명이 실제 코드와 일치합니다.

참고: [Vite 개발 프록시](https://vite.dev/config/server-options#server-proxy).
