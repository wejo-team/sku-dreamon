# 구조와 초기 실행 기반

현재 기능의 구현 범위와 남은 작업은 [API 인덱스](../api/README.md)와 [DB 인덱스](../database/README.md)에서 확인합니다. 아래는 책임별 폴더 배치 기준입니다. 각 계층의 기능 파일과 프론트의 `e2e/`는 해당 코드가 필요할 때 추가하며, 빈 기능 폴더를 미리 늘리지 않습니다.

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
    core/                # 여러 기능이 함께 사용하는 기반
      config.py          # 환경설정
      exceptions.py      # 애플리케이션 오류 정의
      db/                # ORM metadata·선택 컬럼, 비동기 엔진·세션, repository factory
      http/              # 공통 DTO·응답, 조회 라우터, 예외 핸들러, 요청 의존성
    routers/             # HTTP 경로·요청 파싱·응답과 쿠키
      health.py          # health API
    dependencies/        # HTTP 인증·CSRF 등 요청 의존성
    services/            # 업무 규칙·권한·DTO 구성·요청 트랜잭션
    agents/              # Luna 모델·조회 도구·구조화 계획·텍스트 스트림
    repositories/        # SQL 읽기·쓰기·행 잠금·flush
    models/              # SQLAlchemy ORM 저장 모델
    schemas/             # Pydantic 요청·응답 DTO
    rules/               # 선택지 enum·순수 업무 검증
    security/            # 해시·토큰 서명 등 순수 보안 계산
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
- 백엔드는 전역 계층으로 나누고 각 계층 안에 기능 이름의 모듈을 둡니다. `routers`는 HTTP 경로·파싱·응답, `dependencies`는 인증·CSRF 등 요청 의존성을 담당합니다. `services`는 업무 권한·상태 전이·DTO 구성과 요청 단위 트랜잭션을 담당합니다. `repositories`는 SQL 읽기·쓰기·행 잠금·flush를 수행하고 ORM 객체나 내부 typed row를 반환합니다.
- `models`는 SQLAlchemy 저장 모델, `schemas`는 요청·응답 DTO입니다. `schemas`에서 ORM을 import하거나 ORM 행을 DTO로 변환하지 않습니다. `rules`에는 선택지 enum과 DB·HTTP에 의존하지 않는 검증을, `security`에는 비밀번호 해시·토큰 서명 같은 순수 보안 계산을 둡니다.
- `core`는 여러 기능이 사용하는 기반입니다. ORM의 공통 metadata·선택 컬럼과 엔진·세션·repository factory는 `core/db`, 공통 DTO·응답·조회 라우터·예외 핸들러·요청 의존성은 `core/http`에 둡니다. [공통 기반의 책임](backend.md#orm-foundation)에 따라 모델의 PK·컬럼을 선택하며 모든 모델에 같은 `id`·시각 컬럼을 강제하지 않습니다.
- [BaseCrudRouter](backend.md#read-router)는 도메인이 명시한 목록·상세 GET의 응답 계약과 오류 선언을 연결합니다. HTTP handler가 서비스에 파싱된 값을 전달하며, 공통 라우터는 DB 쿼리·권한 정책·트랜잭션을 결정하지 않습니다. 쓰기·업무 명령과 특수 응답은 일반 `APIRouter` 경로로 등록합니다. 등록된 제품 경로와 구현 상태는 [API 인덱스](../api/README.md)를 따르며, 문서 예시를 별도 기능의 구현으로 해석하지 않습니다.
- DB를 사용하는 업무는 `routers → services → repositories → models` 방향을 따릅니다. 요청 의존성은 인증 서비스를 호출하고, 서비스는 필요한 ORM 객체·스키마·순수 규칙을 사용할 수 있습니다. 레포지토리는 서비스·API DTO·HTTP 계층을 import하지 않으며, 서비스·모델·스키마·규칙·보안 계산도 기능별 `routers`·`dependencies`에 의존하지 않습니다. `core`는 기능별 상위 계층을 import하지 않으며, `core/db`는 FastAPI·Starlette나 `core/http`에도 의존하지 않습니다. 기존 `core/http`의 공통 DTO와 HTTP 어댑터는 유지합니다. 엔진·세션의 생성과 정리는 `core/db/session.py`, 요청 DB 연결은 `core/http/dependencies.py`, 앱 수명과 라우터 조립은 `main.py`가 맡습니다.
- 읽기·쓰기 DB 접근은 [함수형 레포지토리 모듈](backend.md#repository-boundary)에 둡니다. 서비스에서 ORM 필드의 업무 상태를 바꿀 수 있지만 SQL 실행·행 잠금·flush는 레포지토리를 호출합니다. API DTO는 레포지토리 결과를 받아 서비스에서 구성합니다. 별도 generic base class·interface·Unit of Work를 추가하지 않습니다. 기존 [RepositoryFactory](backend.md#repository-factory)는 생성자 주입과 독립 작업 세션에 필요할 때 사용하는 도구이며 모든 기능에 강제하지 않습니다.
- 서비스끼리 호출할 수 있습니다. 한 업무에 속한 팀·지원·알림 변경은 같은 세션을 전달하고, 가장 바깥 쓰기 서비스가 commit·rollback을 소유합니다. 하위 서비스와 레포지토리는 commit·rollback하지 않으며, 필요한 DB 반영은 레포지토리의 flush로 처리합니다. [트랜잭션 책임](backend.md#transaction-ownership)을 유지하면서 DB 접근과 업무 판단을 분리합니다.
- AI의 `agents`는 모델·프롬프트·읽기 도구 어댑터를 담당합니다. `services/ai → agents → services/ai_sources → 기존 도메인 services`로 연결하며 에이전트가 실행 조합/실행 제어 서비스로 역참조하거나 SQL·HTTP 프레임워크에 의존하지 않습니다. 기존 repositories·models·core의 의존 경계는 유지합니다. 구현과 검증 원본은 [AI SDD](../development-plans/ai-agent.md)를 따릅니다.
- 프론트와 백엔드는 HTTP API를 통해 연결합니다. 백엔드 DB 구조를 그대로 프론트의 내부 상태 구조로 강제하지 않습니다.

## 개발 환경

- PostgreSQL은 루트 Compose로 실행하고, 프론트·백엔드 개발 서버는 각 폴더에서 실행합니다.
- 프론트 API 기본 경로는 `/api/v1`입니다. 개발 환경에서는 Vite의 `/api` 프록시가 FastAPI로 전달합니다. 운영 환경 연결 방식은 배포 플랫폼 확정 시 정합니다.
- 환경변수 예시는 프론트·백엔드 각각 제공합니다. Compose의 개발 DB 설정과 백엔드 DATABASE_URL의 일치 여부를 실행 검증에 포함합니다.
- Node와 Python은 버전 파일로, npm 패키지와 Python 의존성은 각 lockfile로 고정합니다.

## 실행 기반의 구성

1. 실행 기반: 런타임 버전·의존성·환경변수 예시·PostgreSQL Compose.
2. 백엔드: 앱 생성, 설정 로딩, async DB 세션과 repository factory, 공통 목록·상세 라우터, Alembic 환경, health API.
3. 프론트: router·provider·모바일 레이아웃·공통 HTTP 클라이언트·백엔드 연결 확인.
4. 검사: formatter·linter·타입 검사와 실제 코드에 대한 테스트, GitHub Actions 연결.
5. 문서: [로컬 실행](local-development.md)에 설치·실행·검사·마이그레이션 명령 기록.

초기 health 응답은 `/api/v1/health`에서 `{"status":"ok"}`로 고정합니다. DB 연결 가능 여부는 별도 연결 검사로 확인하며, health 응답만으로 DB 정상 여부를 주장하지 않습니다.

현재 ORM과 Alembic 적용 범위는 [DB 인덱스](../database/README.md)를 따릅니다. 스키마 적용, 기능 구현, 운영 데이터 적재와 배포 완료를 구분하며, 미구현 기능을 임시 성공 응답으로 대신하지 않습니다.

## 완료 기준

- 새 환경에서 문서대로 의존성 설치와 PostgreSQL 실행을 재현할 수 있습니다.
- 모바일 기본 화면에서 FastAPI 요청의 성공·실패를 확인할 수 있습니다.
- 비동기 DB 연결과 Alembic 실행 경로를 검증합니다.
- 구현된 범위의 검사와 빌드가 통과하고, 아직 설정하지 않은 검사를 구분해 보고합니다.
- 폴더·명령·환경변수 설명이 실제 코드와 일치합니다.

참고: [Vite 개발 프록시](https://vite.dev/config/server-options#server-proxy).
