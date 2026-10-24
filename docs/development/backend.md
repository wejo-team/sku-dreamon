# 백엔드·비동기 DB 규칙

## 기본 구성

FastAPI, uv, Pydantic, pydantic-settings, SQLAlchemy 2 비동기 API, asyncpg, PostgreSQL, Alembic을 사용합니다. 데이터베이스 URL 형식은 `postgresql+asyncpg://...`입니다.

백엔드는 `routers`·`dependencies`·`services`·`repositories`·`models`·`schemas`·`rules`·`security`의 전역 계층으로 나눕니다. 각 계층에는 필요한 기능 모듈만 추가합니다. `core`는 공통 설정·예외·DB·HTTP 기반을 제공하며 기능별 상위 계층을 import하지 않습니다. 기존 `core/http`는 공통 HTTP 어댑터로 유지하고, `core/db`는 HTTP 프레임워크와 `core/http`에 의존하지 않습니다. 전체 배치와 의존 방향은 [구조와 책임 경계](architecture.md#responsibility-boundaries)를 따릅니다.

현재 등록된 제품 API와 남은 기능은 [API 인덱스](../api/README.md), 저장 모델·Alembic 적용 범위는 [DB 인덱스](../database/README.md)에서 확인합니다. [앱 구성](../../backend/app/main.py)은 기능 라우터를 `/api/v1`에 연결하고 실제 라우터·DTO에서 OpenAPI를 생성합니다.

- API는 `/api/v1` 아래에 리소스 중심 경로로 제공합니다. HTTP 상태 코드를 사용하고 실패를 200 응답으로 감추지 않습니다.
- 요청·응답은 Pydantic schema로 명시합니다. FastAPI의 기본 validation error 형식과 호환되는 처리를 우선하고, 도메인 오류 계약이 필요하면 프론트와 함께 문서화합니다.
- 제품 API의 성공 응답 모델은 [공통 성공 응답](../api/conventions.md#success-responses)을 따릅니다. 실제 JSON과 OpenAPI 모두 최상위 `data`를 명시하며, 204의 빈 본문과 쿠키·`Location` 헤더를 보존합니다.
- 구현 전 API 계약은 [Markdown 설계](../api/README.md)에서 검토합니다. 구현 시 라우터·Pydantic 모델·인증과 오류 선언을 기준으로 FastAPI의 OpenAPI·Swagger UI를 자동 생성하며 수동 YAML을 별도로 유지하지 않습니다.
- 구현 PR에서 생성 문서와 실제 응답을 [정합성 확인 기준](../api/README.md#consistency)에 따라 설계와 대조합니다. 구현된 API의 상세 필드 표는 코드·생성 문서 링크로 대체하고 설계 이유·정책·트랜잭션 설명은 유지합니다. 자세한 순서는 [API 인계 절차](../api/README.md#implementation-handoff)를 따릅니다.
- Python 내부 필드와 전송 JSON의 이름은 [컨벤션](conventions.md)의 「API JSON 필드명」 규칙에 따라 API DTO 경계에서 연결합니다. 현재 적용 상태와 요청 이름 검증 기준도 해당 절을 따릅니다.
- 환경설정은 `core/config.py`에서 검증합니다. 모듈 import만으로 DB 쿼리·외부 API 호출·테이블 생성이 실행되지 않게 합니다.
- async DB나 비동기 외부 I/O를 호출하는 경로는 `async def`와 `await`로 연결합니다. 비동기 경로에서 동기 DB·HTTP 호출로 이벤트 루프를 막지 않습니다.

<a id="api-core"></a>

## 공통 API 기반의 책임

[구현 이슈 #99](https://github.com/wejo-team/sku-dreamon/issues/99)의 `core/http`는 전송 계약과 FastAPI 연결을 담당합니다. ORM 공통 기반은 아래 별도 절처럼 `core/db`에 둡니다. 업무 권한·상태 전이·정원·DTO 구성과 요청 트랜잭션은 `services`, SQL 읽기·쓰기·행 잠금·flush는 `repositories`가 맡습니다. `schemas`는 ORM을 import하지 않으며 API DTO의 값과 전송 계약을 정의합니다.

- 요청 DTO는 camelCase만 받고, 응답 DTO는 Python의 snake_case로 구성하여 camelCase로 보냅니다. 두 책임을 분리하여 응답 생성 편의를 위해 외부 snake_case 입력까지 허용하지 않습니다. 임의 map 키는 변환하지 않습니다.
- 성공 응답과 페이지 응답은 라우터에서 명시적인 모델로 반환합니다. `Success[T]`의 `T`에는 NULL을 허용하지 않는 영역별 DTO나 배열 타입을 지정하여 실제 검증과 OpenAPI를 일치시킵니다. [공통 조회 라우터](#read-router)는 등록한 상세 조회의 DTO를 `Success[T]`로 한 번 감쌉니다. 응답 본문을 자동으로 감싸는 middleware는 사용하지 않으므로 health·204·쿠키·`Location`의 기존 동작을 유지합니다.
- BIGINT는 DTO 경계에서 엄격한 십진 문자열, 시각은 시간대가 있는 값으로 검증해 UTC `Z`로 보냅니다. DB 정수를 응답에 담을 때의 `str()` 변환은 해당 DTO를 만드는 곳에서 명시합니다.
- 업무 오류는 상태·코드·안전한 안내 문구를 가진 예외 하나로 표현합니다. 예상하지 못한 오류와 요청 검증 실패에는 입력 원문을 포함하지 않는 응답을 제공합니다. 오류 응답 모델은 라우터의 `responses`에도 명시하여 OpenAPI와 실제 응답을 맞춥니다.
- 페이지 모델은 범위와 전송 모양만 검증합니다. 마지막 페이지 보정·권한·필터·동일 읽기 시점의 집계는 실제 목록을 조회하는 도메인이 책임집니다.

구현 원본은 [공통 DTO·응답 모델·전송 타입](../../backend/app/core/http/schemas.py), [애플리케이션 예외](../../backend/app/core/exceptions.py)와 [HTTP 예외 핸들러·오류 응답 선언](../../backend/app/core/http/handlers.py)입니다. 제품 요청 모델은 `RequestDTO`, 응답 모델은 `ResponseDTO`를 상속합니다. 모델 전체에 `strict=True`를 지정하기보다 숫자 등 해당 필드의 엄격한 타입을 선택하여 정상 UUID·시각 문자열의 파싱을 막지 않습니다.

각 도메인은 사용하는 공통 요소를 해당 모듈에서 가져옵니다. 공통 DTO·응답 모델과 전송 타입은 `app.core.http.schemas`에서 가져옵니다.

```python
from app.core.exceptions import AppError
from app.core.http.handlers import error_responses
from app.core.http.schemas import RequestDTO, ResponseDTO, Success, Timestamp, Version
```

제품 라우터는 `responses=error_responses(401, 409, 422, 500, 503)`처럼 자신이 제공할 오류 상태를 명시합니다. 업무 실패는 `AppError(status_code, code, message)`로 전달하며 `message`에 입력 원문을 넣지 않습니다. 422는 요청 검증에만 사용하며 `AppError`로 지정할 수 없습니다. 프레임워크 HTTP 오류의 원래 `detail`과 검증기의 원래 `msg`는 그대로 노출하지 않습니다. 422는 `loc`·`type`과 고정된 안전한 안내를 반환하므로 필드별 화면 안내는 선언한 검증 계약을 함께 사용합니다. 위치 정보가 없는 명시적 `HTTPException(422)`도 같은 `detail` 구조로 반환합니다.

`AppError`는 HTTP 상태·헤더를 포함하는 애플리케이션 예외이며, 전송 방식과 무관한 순수 도메인 예외로 정의하지 않습니다. 예외 정의는 FastAPI 없이 사용할 수 있고, 이를 응답으로 바꾸고 앱에 등록하는 책임은 `core/http/handlers.py`에 둡니다.

오류 처리 시 만든 추적 ID는 `X-Request-ID` 응답 헤더와 최소 오류 로그에 기록하며, 업무 오류 본문의 `requestId`와 같습니다. 422 본문에는 기존 `detail`만 유지합니다. 이 ID는 생성 재시도에 쓰는 도메인 `requestId`와 관계없고 성공 요청 전체를 추적하는 기능은 아닙니다. 공통 핸들러가 남기는 로그에는 요청 본문·검증 입력·예외 문자열을 추가하지 않습니다. 서버 자체의 traceback 로그를 정제하는 기능은 포함하지 않습니다.

<a id="read-router"></a>

## 공통 조회 라우터

[BaseCrudRouter](../../backend/app/core/http/routers.py)는 목록·상세 GET의 등록, 응답 모델, 오류 응답 선언을 공통화합니다. 도메인이 `prefix`, 선택적인 `tags`·`dependencies`를 전달해 생성하고 필요한 작업만 등록합니다. 생성만으로 경로가 추가되지 않으며, `.router`는 앱에 연결할 `APIRouter`입니다.

| 등록 메서드 | handler의 반환값 | 등록할 response_model과 동작 |
| --- | --- | --- |
| `add_list(path="", handler=..., response_model=...)` | `Page[Summary]` 또는 이를 확장한 페이지 DTO | 실제 페이지 DTO 타입을 지정. handler가 만든 `data`·`pagination`·추가 메타데이터를 반환 |
| `add_detail(path, handler=..., response_model=...)` | `Detail` DTO | `Success[Detail]`을 지정. 반환 DTO를 `data`에 한 번 감싸 반환 |

`Summary`·`Detail`은 `ResponseDTO`를 상속하며 목록과 상세에서 서로 다른 DTO를 사용할 수 있습니다. 목록의 전체 개수·페이지 보정·집계 등 메타데이터 계산은 서비스가 책임집니다. 확장 페이지를 사용하면 `response_model`에도 그 타입을 지정합니다. 상세 handler는 이미 감싼 `Success`를 반환하지 않습니다. 대상이 없으면 서비스가 `AppError(404, ...)`를 발생시키며, 라우터가 `None`을 자동으로 404로 바꾸지 않습니다.

handler는 `Depends(handler)`로 실행됩니다. handler에 선언한 path·query 타입과 검증 조건은 요청 처리와 OpenAPI에 반영되며, 중첩 `Depends`도 실행됩니다. 주입된 `Response`에 설정한 헤더·쿠키는 응답에 보존됩니다. handler는 `routers`에 두는 얇은 HTTP 함수이며, 파싱된 값과 세션을 서비스에 전달합니다. DB를 사용하는 기능은 서비스가 레포지토리를 호출하며 라우터에서 직접 SQL을 실행하지 않습니다. 비동기 DB·서비스 호출은 `async def` handler에서 `await`하고, 동기 handler는 DTO·페이지 객체를 직접 반환합니다. 서비스에 `Request`·`Depends` 같은 FastAPI 의존성을 추가하지 않습니다.

생성자의 `dependencies`와 각 등록 메서드의 `dependencies`는 함께 적용됩니다. 인증·권한 검사는 도메인이 필요한 의존성을 명시하며, 공통 라우터가 인증 정책을 자동으로 선택하지 않습니다. 기본 오류 응답 선언은 목록에 422·500·503, 상세에 404·422·500·503입니다. `error_statuses`로 401·403 등 해당 작업의 추가 오류를 선언하고, `name`·`summary`로 경로 이름과 OpenAPI 설명을 지정할 수 있습니다. 오류 상태를 선언하는 것만으로 인증 검사나 예외 처리 동작이 추가되지는 않습니다.

아래는 [공모전 경로](../api/contests.md#endpoints)로 등록 형태를 설명하는 예시입니다. `ContestSummary`·`Contest`·`service`는 예시용 이름이며 실제 도메인 구현의 DTO·함수와 구분합니다. 검색·정렬 등 나머지 query를 생략하고 페이지와 UUID 경로 선언만 보여 줍니다. 실제 적용은 [지원 라우터](../../backend/app/routers/applications.py)의 `BaseCrudRouter` 등록을 참고합니다.

```python
from typing import Annotated
from uuid import UUID

from fastapi import Path, Query

from app.core.http.dependencies import DatabaseSession
from app.core.http.routers import BaseCrudRouter
from app.core.http.schemas import Page, Success


async def list_contests(
    session: DatabaseSession,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20,
) -> Page[ContestSummary]:
    return await service.list_contests(session, page=page, page_size=page_size)


async def get_contest(
    contest_id: Annotated[UUID, Path(alias="contestId")],
    session: DatabaseSession,
) -> Contest:
    return await service.get_contest(session, contest_id)


contests = BaseCrudRouter(prefix="/contests", tags=["contests"])
contests.add_list(
    handler=list_contests,
    response_model=Page[ContestSummary],
    name="list_contests",
    summary="공모전 목록",
)
contests.add_detail(
    "/{contestId}",
    handler=get_contest,
    response_model=Success[Contest],
    name="get_contest",
    summary="공모전 상세",
)
router = contests.router
```

이 `router`를 기존 앱의 `/api/v1` prefix 아래에 연결합니다. 생성·수정·삭제, 업무 명령, 204, redirect, streaming 응답은 `.router`에 일반 `APIRouter` 경로로 개별 등록합니다. 공통 라우터는 SQL 필터·PK·레포지토리 구현을 추정하거나 트랜잭션을 시작·commit하지 않습니다. DB 접근은 [레포지토리 경계](#repository-boundary), 쓰기의 성공·실패는 [최상위 서비스](#transaction-ownership)의 책임입니다.

<a id="orm-foundation"></a>

## ORM 공통 기반

[Base](../../backend/app/core/db/base.py)는 SQLAlchemy metadata와 [제약조건 네이밍](../database/conventions.md#constraint-names)을 공유합니다. 단일 PK는 `account_id`, `team_id`처럼 `<단수형 테이블명>_id`로 직접 선언합니다. 모든 테이블에 같은 PK·시각 컬럼을 강제하거나 테이블·컬럼 이름을 자동으로 정하지 않습니다. 프로필의 공유 PK, 학사의 정수 ID, 선택지 연결의 복합 PK처럼 테이블마다 식별 방법이 다릅니다.

[UUID PK 타입](../../backend/app/core/db/types.py)과 [시각 mixin](../../backend/app/core/db/mixins.py)은 필요한 컬럼만 조합하여 사용합니다.

| 공통 요소 | 책임과 적용 조건 |
| --- | --- |
| `UUIDPrimaryKey` | 명시한 필드명에 UUID PK와 애플리케이션의 `uuid4` 기본값을 적용. INSERT/flush 때 발급하므로 그 전에 ID가 필요하면 서비스가 명시적으로 전달 |
| `CreatedAtMixin` | NOT NULL `TIMESTAMPTZ created_at`, DB 생성 기본값 `now()` |
| `UpdatedAtMixin` | NOT NULL `TIMESTAMPTZ updated_at`, DB 생성 기본값 `now()`. 이후 갱신은 아래 서비스 책임 |

예를 들어 계정은 UUID PK 타입·생성 시각만, 공고·팀은 여기에 수정 시각을 조합합니다. 다음은 이름과 PK 발급 책임을 보여 주는 최소 예시이며 실제 도메인 모델 전체가 아닙니다.

```python
from uuid import UUID

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db.base import Base
from app.core.db.mixins import CreatedAtMixin, UpdatedAtMixin
from app.core.db.types import UUIDPrimaryKey


class Account(CreatedAtMixin, Base):
    __tablename__ = "accounts"

    account_id: Mapped[UUIDPrimaryKey]


class Profile(CreatedAtMixin, UpdatedAtMixin, Base):
    __tablename__ = "profiles"

    profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.account_id"), primary_key=True
    )
```

공유 PK인 `profiles.profile_id`에는 부모 `accounts.account_id`와 같은 값을 전달하며 독립 UUID를 발급하는 `UUIDPrimaryKey`를 쓰지 않습니다. `portfolio_links.portfolio_link_id`도 같은 방식으로 `profiles.profile_id`를 참조합니다. 복합 PK는 기존 컬럼 조합을 모델에서 직접 선언합니다. 세션 발급·만료처럼 동일한 업무 시각으로 여러 값을 계산해야 하는 경우에는 해당 모델에서 직접 컬럼을 정의합니다. 실제 적용은 각 도메인 모델·migration에서 설계와 대조합니다. DB PK 이름과 공개 API 이름이 다르면 DTO를 구성하는 곳에서 명시적으로 연결하며, 이번 네이밍 변경으로 공개 API 필드를 바꾸지 않습니다.

수정 시각은 쓰기 서비스가 `version`과 함께 명시적으로 갱신합니다. 프로필 선택 항목·포트폴리오만 바뀌어도 부모 프로필의 시각·버전을 같은 트랜잭션에서 바꿔야 합니다. 조회와 실제 변경이 없는 재시도에는 갱신하지 않습니다. mixin은 `onupdate`나 DB trigger를 추가하지 않으므로 직접 SQL도 같은 책임을 따릅니다.

ORM 모델은 `models`, SQL 읽기·쓰기와 DB 반영은 `repositories`에 둡니다. `services`는 레포지토리가 반환한 ORM 객체나 내부 typed row를 사용해 업무 권한·상태 전이를 판단하고 API DTO와 트랜잭션을 구성합니다. `core/db`에는 함께 사용하는 DB 기반과 선택적인 [레포지토리 생성 도구](#repository-factory)를 둡니다.

<a id="repository-boundary"></a>

## 레포지토리 경계

기능별 `repositories/<기능>.py`에 `AsyncSession`을 받는 함수를 정의합니다. SELECT·INSERT·UPDATE·DELETE, ORM 추가·삭제·flush, 행 잠금은 이 계층에서 실행합니다. 조회 이름을 바꾸는 데 그치지 않고 읽기와 쓰기의 DB 접근을 함께 옮깁니다.

레포지토리는 ORM 객체·값·내부 typed row를 반환하며 `schemas`의 API DTO를 만들거나 반환하지 않습니다. 서비스가 현재 권한과 업무 규칙을 적용해 DTO를 구성합니다. 서비스에서 이미 읽은 ORM 객체의 필드를 변경하는 것은 허용하지만, 변경을 DB에 반영할 때는 레포지토리를 호출합니다.

레포지토리는 호출자가 전달한 세션을 사용하고 commit·rollback·세션 종료를 하지 않습니다. 여러 레포지토리에 같은 세션을 전달해 한 업무의 원자성을 유지합니다. 권한 판단, 잠금 순서의 조합, 상태 전이와 저장 확정은 최상위 서비스가 책임집니다.

함수형 모듈을 기본으로 하며 별도 generic base class·interface·Unit of Work는 도입하지 않습니다. `AsyncSession`의 모든 메서드를 그대로 복제하는 범용 CRUD도 만들지 않습니다.

## 엔진과 세션

[인증 세션 서비스](../../backend/app/services/sessions.py)는 불투명 토큰을 발급하고 잠금 후 현재 시각으로 만료·회수를 검사합니다. 요청의 [인증 의존성](../../backend/app/dependencies/auth.py)은 세션 서비스를 호출하며, 세션 서비스가 별도의 짧은 DB 세션에서 유효 활동을 커밋합니다. 업무 서비스에는 인증 주체 UUID와 별도의 `DatabaseSession`을 전달합니다. 세션 발급·회수 함수는 호출자의 세션을 사용하고 커밋은 최상위 유스케이스가 맡습니다. [인증 서비스](../../backend/app/services/auth.py)가 가입·로그인의 세션 발급과 로그아웃의 회수를 커밋하며 HTTP 라우터와 연결되어 있습니다.

[CSRF 요청 검사](../../backend/app/dependencies/csrf.py)와 [서명 계산](../../backend/app/security/csrf.py)은 `CSRF_SIGNING_KEY`와 정확한 HTTPS origin 목록 `AUTH_ALLOWED_ORIGINS`를 사용합니다. 키 원문은 저장소와 오류 로그에 포함하지 않습니다. [인증 라우터](../../backend/app/routers/auth.py)는 현재 인증 상태의 CSRF 조회·본인 계정 조회·로그아웃을 제공하고, [쿠키 처리](../../backend/app/routers/auth_cookies.py)는 유효 토큰 재사용·무효 세션 쿠키 삭제·커밋 후 로그아웃 쿠키 삭제에 연결됩니다. 응답 필드는 [인증 DTO](../../backend/app/schemas/auth.py), 전송 설계는 별도 [PR #124](https://github.com/wejo-team/sku-dreamon/pull/124)를 참조합니다. 가입·로그인·아이디 중복 확인, PostgreSQL 공유 시도 제한과 로컬 차단 목록 검증도 구현했습니다. 실제 운영 파일·키·origin 배포와 세션·시도 키 보존은 후속 범위입니다.

- `create_async_engine`과 `async_sessionmaker`를 사용합니다. engine·session factory는 앱 수명에 맞춰 구성하고 종료 시 engine을 dispose합니다.
- `AsyncSession`은 요청 또는 독립 작업 단위로 생성·종료합니다. 전역 Session, 요청 사이의 Session 공유, 하나의 Session을 여러 동시 task에서 공유하는 코드를 만들지 않습니다.
- [DB 세션 기반](../../backend/app/core/db/session.py)의 `Database`·`create_database`는 HTTP 요청을 알지 않습니다. `Database.session()`은 세션을 생성하고 context 종료 시 정리하므로 HTTP·배치·CLI에서 함께 사용할 수 있습니다. [HTTP 의존성](../../backend/app/core/http/dependencies.py)의 `get_session`·`DatabaseSession`은 이 context를 요청에 연결합니다. context 종료 시 자동으로 commit하지 않습니다.
- 기본 세션 설정은 `expire_on_commit=False`로 합니다. 이것이 모든 지연 로딩을 비동기로 안전하게 만드는 것은 아닙니다.
- 응답 직렬화 중 암묵적 쿼리가 발생하지 않도록 필요한 관계를 명시적으로 조회합니다. 관계 조회는 `selectinload` 등의 eager loading을 우선 검토합니다.
- 종료된 세션에 붙어 있던 객체에서 새 DB 조회가 필요한 속성을 읽지 않습니다. background task에는 기존 요청 Session을 넘기지 않습니다.

<a id="repository-factory"></a>

## 레포지토리 생성

업무 레포지토리는 위의 함수형 모듈을 사용합니다. 기존 `RepositoryFactory`는 생성자 주입이나 독립 작업의 세션 관리가 필요한 경우에만 쓰는 공통 helper이며 모든 레포지토리에 적용하지 않습니다.

[RepositoryFactory](../../backend/app/core/db/factories.py)는 `AsyncSession`을 받는 생성자를 주입하고 반환 타입을 유지합니다. HTTP 요청·도메인 모델·CRUD 메서드를 알지 않으며, 레포지토리에 특정 부모 클래스나 공통 PK를 요구하지 않습니다. `repository_class`의 타입은 `Callable[[AsyncSession], RepositoryType]`이므로 클래스 또는 추가 설정을 묶은 생성 함수를 전달할 수 있습니다.

| 호출 | 세션 소유권과 동작 |
| --- | --- |
| `factory.create_repository(session)` | 호출자가 제공한 세션으로 객체를 생성. 팩토리는 세션을 종료하거나 commit하지 않음 |
| `async with factory.open_repository() as repository` | 생성자에 전달한 `database`의 `session()`으로 새 세션을 열고 context 종료 시 정리. `database`가 없으면 `ValueError` |

`open_repository()`는 객체 생성 중이나 context 본문에서 예외가 발생해도 세션을 정리하고 예외를 전파합니다. 자동 commit은 없으며, 커밋하지 않은 변경은 세션 정리 시 롤백됩니다. 저장 확정과 실패 처리는 아래 [트랜잭션 책임](#transaction-ownership)을 따릅니다. 여러 레포지토리의 쓰기를 하나로 묶을 때는 같은 세션을 각각의 `create_repository()`에 전달합니다. 각 레포지토리에서 `open_repository()`를 따로 호출하면 서로 다른 세션이 만들어집니다.

다음은 호출 방식의 예시입니다. `AccountRepository`는 예시용 이름이며 생성자에서 `AsyncSession`을 받는다고 가정합니다. 요청에서는 HTTP 의존성이 제공한 세션을 전달합니다. 이 예시는 클래스형 레포지토리나 factory 사용을 강제하지 않으며, 함수형 레포지토리의 DB 접근 분리 원칙은 유지합니다.

```python
from app.core.db.factories import RepositoryFactory
from app.core.http.dependencies import DatabaseSession

account_factory = RepositoryFactory(repository_class=AccountRepository)


def get_account_repository(session: DatabaseSession) -> AccountRepository:
    return account_factory.create_repository(session)
```

독립 작업에서는 앱 또는 작업의 수명에 맞춰 준비한 `database`를 사용합니다. 아래 코드는 비동기 작업 본문이며, 작업을 끝낸 뒤 DB 엔진을 해제하는 책임은 `database`를 만든 진입점에 있습니다.

```python
account_factory = RepositoryFactory(
    repository_class=AccountRepository,
    database=database,
)

async with account_factory.open_repository() as repository:
    account = await repository.get_by_id(account_id)
```

이 구조는 [aioia-core의 팩토리](https://github.com/algorima/aioia-core/blob/76f0cdd03afbace4132bbf2a6b27cd900e3e0cff/python/aioia_core/factories/base_repository_factory.py)의 생성자 주입과 제네릭 패턴을 참고해 우리 비동기 기반에 맞게 구현했습니다. 참고 기준은 커밋 `76f0cdd03afbace4132bbf2a6b27cd900e3e0cff`입니다. 외부 패키지를 의존성으로 추가하지 않습니다. 해당 버전의 [Python 지원 범위](https://github.com/algorima/aioia-core/blob/76f0cdd03afbace4132bbf2a6b27cd900e3e0cff/python/pyproject.toml)는 3.13 미만이며, [원본 레포지토리](https://github.com/algorima/aioia-core/blob/76f0cdd03afbace4132bbf2a6b27cd900e3e0cff/python/aioia_core/repositories.py)는 동기 세션·내부 commit·문자열 `id`를 전제합니다. 우리 코어는 비동기 세션, 명시적인 세션 소유권, 서비스의 commit, 도메인별 PK·DTO를 유지합니다.

<a id="transaction-ownership"></a>

## 트랜잭션 책임

- 하나의 쓰기 유스케이스를 맡는 최상위 서비스가 트랜잭션의 성공·실패를 책임집니다.
- 최상위 서비스는 필요한 변경을 수행한 뒤 `await session.commit()`을 한 번 호출합니다. 실패하면 `await session.rollback()` 후 오류를 전파합니다. commit은 성공 응답을 반환하기 전에 완료합니다.
- 레포지토리와 하위 보조 서비스는 commit·rollback하지 않습니다. 생성된 ID나 제약조건 확인이 필요하면 레포지토리에서 `flush()`를 수행합니다.
- 서비스 간 호출을 허용하며, 한 유스케이스의 팀·지원·알림 변경에는 같은 `AsyncSession`을 전달합니다. 가장 바깥 쓰기 서비스가 commit·rollback을 소유하고 하위 변경 함수는 레포지토리를 통해 필요한 DB 반영만 수행합니다. 이미 commit하는 최상위 서비스를 그대로 중첩 호출하지 않습니다.
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
