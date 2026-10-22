# 백엔드·비동기 DB 규칙

## 기본 구성

FastAPI, uv, Pydantic, pydantic-settings, SQLAlchemy 2 비동기 API, asyncpg, PostgreSQL, Alembic을 사용합니다. 데이터베이스 URL 형식은 `postgresql+asyncpg://...`입니다.

- API는 `/api/v1` 아래에 리소스 중심 경로로 제공합니다. HTTP 상태 코드를 사용하고 실패를 200 응답으로 감추지 않습니다.
- 요청·응답은 Pydantic schema로 명시합니다. FastAPI의 기본 validation error 형식과 호환되는 처리를 우선하고, 도메인 오류 계약이 필요하면 프론트와 함께 문서화합니다.
- 제품 API의 성공 응답 모델은 [공통 성공 응답](../api/conventions.md#success-responses)을 따릅니다. 실제 JSON과 OpenAPI 모두 최상위 `data`를 명시하며, 204의 빈 본문과 쿠키·`Location` 헤더를 보존합니다.
- 구현 전 API 계약은 [Markdown 설계](../api/README.md)에서 검토합니다. 구현 시 라우터·Pydantic 모델·인증과 오류 선언을 기준으로 FastAPI의 OpenAPI·Swagger UI를 자동 생성하며 수동 YAML을 별도로 유지하지 않습니다.
- 구현 PR에서 생성 문서와 실제 응답을 [정합성 확인 기준](../api/README.md#consistency)에 따라 설계와 대조합니다. 구현된 API의 상세 필드 표는 코드·생성 문서 링크로 대체하고 설계 이유·정책·트랜잭션 설명은 유지합니다. 자세한 순서는 [API 인계 절차](../api/README.md#implementation-handoff)를 따릅니다.
- Python 내부 필드와 전송 JSON의 이름은 [컨벤션](conventions.md)의 「API JSON 필드명」 규칙에 따라 API DTO 경계에서 연결합니다. 현재 적용 상태와 요청 이름 검증 기준도 해당 절을 따릅니다.
- 환경설정은 `core/config.py`에서 검증합니다. 모듈 import만으로 DB 쿼리·외부 API 호출·테이블 생성이 실행되지 않게 합니다.
- async DB나 비동기 외부 I/O를 호출하는 경로는 `async def`와 `await`로 연결합니다. 비동기 경로에서 동기 DB·HTTP 호출로 이벤트 루프를 막지 않습니다.

## 엔진과 세션

- `create_async_engine`과 `async_sessionmaker`를 사용합니다. engine·session factory는 앱 수명에 맞춰 구성하고 종료 시 engine을 dispose합니다.
- `AsyncSession`은 요청 또는 독립 작업 단위로 생성·종료합니다. 전역 Session, 요청 사이의 Session 공유, 하나의 Session을 여러 동시 task에서 공유하는 코드를 만들지 않습니다.
- 요청 dependency는 세션의 생성과 정리를 담당합니다. dependency 종료 시 무조건 commit하는 정책은 사용하지 않습니다.
- 기본 세션 설정은 `expire_on_commit=False`로 합니다. 이것이 모든 지연 로딩을 비동기로 안전하게 만드는 것은 아닙니다.
- 응답 직렬화 중 암묵적 쿼리가 발생하지 않도록 필요한 관계를 명시적으로 조회합니다. 관계 조회는 `selectinload` 등의 eager loading을 우선 검토합니다.
- 종료된 세션에 붙어 있던 객체에서 새 DB 조회가 필요한 속성을 읽지 않습니다. background task에는 기존 요청 Session을 넘기지 않습니다.

## 트랜잭션 책임

- 하나의 쓰기 유스케이스를 맡는 최상위 서비스가 트랜잭션의 성공·실패를 책임집니다.
- 최상위 서비스는 필요한 변경을 수행한 뒤 `await session.commit()`을 한 번 호출합니다. 실패하면 `await session.rollback()` 후 오류를 전파합니다. commit은 성공 응답을 반환하기 전에 완료합니다.
- 하위 query 함수·repository·보조 서비스는 독자적으로 commit하지 않습니다. 생성된 ID나 제약조건 확인이 필요하면 `flush()`를 사용합니다.
- 여러 쓰기를 하나로 묶는 기능은 가장 바깥 유스케이스가 commit을 소유합니다. 이미 commit하는 최상위 서비스를 그대로 중첩 호출하지 않습니다.
- 인증·권한 조회 등 앞선 SELECT가 autobegin을 만들 수 있습니다. 세션 상태를 고려하지 않고 모든 서비스에 `session.begin()`을 추가하지 않습니다. begin context를 사용하려면 그 코드가 트랜잭션 전체 경계를 소유함을 보장합니다.
- 읽기 전용 작업에 불필요한 commit을 추가하지 않습니다. 실패한 세션을 재사용하려면 rollback을 먼저 수행합니다.
- 느린 AI·외부 API 응답을 기다리는 동안 DB 트랜잭션과 잠금을 오래 유지하지 않습니다. 외부 호출과 DB 변경의 순서·실패 처리는 기능 단위로 설계합니다.

## 모델과 마이그레이션

- SQLAlchemy 2의 typed mapping을 사용하고, ORM 모델과 API schema를 분리합니다.
- 테이블·컬럼 변경은 Alembic revision으로 관리합니다. 앱 시작 시 `create_all()`로 서비스 스키마를 관리하지 않습니다.
- Alembic은 async 환경 템플릿을 바탕으로 연결합니다. 비동기 connection에서 `run_sync`를 통해 Alembic migration context를 실행합니다. revision의 `upgrade()`·`downgrade()`는 일반 동기 함수로 유지합니다.
- 자동 생성 revision은 반드시 검토합니다. 이름 변경, enum, 데이터 변환, 데이터 손실 가능성은 자동 생성만으로 판단하지 않습니다.
- 공유 환경에 적용한 revision은 다시 쓰지 않고 새 revision을 추가합니다. 실제 모델이 정해지기 전 의미 없는 첫 migration을 만들지 않습니다.
- 개발과 CI에서 PostgreSQL로 migration을 검증합니다. `alembic check`는 변경 누락 탐지 보조 검사이며 정확성 전체를 보장하지 않습니다.

## 근거

- [SQLAlchemy AsyncSession·동시 작업·암묵적 I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [SQLAlchemy asyncpg dialect](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#asyncpg)
- [Alembic asyncio 환경](https://alembic.sqlalchemy.org/en/latest/cookbook.html#using-asyncio-with-alembic)
- [Alembic autogenerate와 check](https://alembic.sqlalchemy.org/en/latest/autogenerate.html)
