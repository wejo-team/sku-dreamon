# DB 설계 공통 기준

이 문서는 물리 테이블 정의를 읽는 데 필요한 기준입니다. 실행 환경과 코드 책임은 [백엔드 규칙](../development/backend.md)을 따릅니다.

## 표기와 타입

| 항목 | 설계 기준 |
| --- | --- |
| 대상 DB | 저장소 `compose.yaml`과 같은 PostgreSQL 17.11 |
| 이름 | 테이블은 복수형, 컬럼은 `snake_case`. API의 `camelCase`와 DTO 경계에서 변환 |
| `PK` / `FK` / `UQ` | 기본 키 / 외래 키 / 유일성. 복합 키는 괄호 안 컬럼 전체의 조합 |
| NULL | 표에서 허용한 컬럼만 NULL. 미입력을 빈 문자열·가짜 코드·0으로 대체하지 않음 |
| UUID | 계정·공고·팀·지원 등 업무 객체의 식별자. 서버가 생성하며 로그인 아이디와 분리 |
| 학사 ID | `academic_units.id`는 `bigint GENERATED ALWAYS AS IDENTITY`. 부모·프로필 참조도 `bigint`, API에는 십진 문자열로 전달 |
| `VARCHAR(64)` 코드 | 분야·역할 등 선택지의 안정된 키. 화면 이름은 변경할 수 있지만 키를 이름으로 재생성하지 않음 |
| `TEXT` | 가변 길이 입력. 길이·형식 제약은 해당 테이블의 CHECK와 API 검증을 함께 사용 |
| `BIGINT` | 정원·수정 버전. API에는 정밀도 손실 없는 십진 문자열로 전달 |
| `TIMESTAMPTZ` | 실제 시점. API는 UTC 오프셋이 있는 RFC 3339 문자열. 원문 시간대는 별도 보존 |
| `DATE` / `TIME` | 공고에 적힌 날짜·시각 원문 요소. 실제 마감 판정에는 정규화된 시점을 사용 |
| 기본값 `—` | DB 기본값 없음. 쓰기 유스케이스가 명시적으로 전달 |
| 서버 시각 | 해당 업무가 실제 발생한 서버 시점. 요청자가 보낸 시각을 감사 기록으로 신뢰하지 않음 |

`BIGINT`의 양수 표현 범위는 1~9,223,372,036,854,775,807입니다. 이는 저장 타입의 기술적 범위이며, “인원 제한 없음” 공고에 별도의 서비스 정원 상한을 정한 것이 아닙니다. API에서 정원과 버전은 이 범위를 검증하고, 표현 범위가 달라져야 하면 DB와 API 계약을 함께 변경합니다.

## 제약을 두는 위치

| 무결성 종류 | 적용 위치 | 예 |
| --- | --- | --- |
| 한 행 안의 필수·범위·조합 | NOT NULL, CHECK | 정원 양수, 경험 상태와 본문 조합 |
| 식별자·참조 대상 일치 | PK, UQ, FK | 지원의 팀·공모전 조합, 소속의 원천 지원 |
| 일부 행에만 유일성 적용 | 조건부 UNIQUE 인덱스 | 종료되지 않은 공모전별 소속 |
| 여러 행의 개수·업무 상태 | 잠금을 포함한 서비스 트랜잭션 | 현재 소속 수와 목표 정원, 관심 분야 개수 |
| 현재 시각·열람자에 의존 | 조회·쓰기 시점의 서비스 검사 | 접수 상태, 프로필 공개 범위 |

CHECK는 다른 테이블을 조회하거나 시간이 지나면 저절로 재평가되는 장치가 아닙니다. 관계를 FK로 표현할 수 있으면 FK를 사용하고, 행 개수·기한·권한은 [트랜잭션 설계](transactions.md)에서 다룹니다. [PostgreSQL 제약 문서](https://www.postgresql.org/docs/17/ddl-constraints.html), [조건부 인덱스 문서](https://www.postgresql.org/docs/17/indexes-partial.html)

모든 PK·UQ는 필요한 인덱스를 포함합니다. 같은 컬럼의 일반 인덱스를 중복 추가하지 않습니다. FK의 자식 쪽 조회 인덱스는 도메인 문서에 별도로 적습니다.

<a id="constraint-names"></a>

## 제약조건·인덱스 이름

[ORM Base의 metadata](../../backend/app/db/base.py)는 이름을 생략한 PK·UQ·FK·일반 인덱스에 아래 기본 규칙을 적용합니다. 도메인 문서에 이름이 명시된 제약·인덱스는 그 이름을 코드에 그대로 전달합니다. 예를 들어 `fk_auth_sessions_account`를 자동 이름으로 바꾸지 않습니다.

| 종류 | 이름을 생략했을 때 |
| --- | --- |
| PK | `pk_<table>` |
| UQ | `uq_<table>_<column1>_<column2>...` |
| FK | `fk_<table>_<column1>_<column2>..._<referred_table>` |
| 인덱스 | `ix_<table>_<column1>_<column2>...` |

복합 제약에는 선언 순서의 모든 로컬 컬럼 이름을 포함합니다. CHECK는 `ck_<table>_<meaning>` 형태의 **완전한 이름을 직접 선언**하며, 이름이 없으면 metadata 구성 시 오류로 거부합니다. 이미 정한 CHECK 이름에 접두사를 다시 붙이지 않습니다. 같은 컬럼에 다른 조건·정렬·참조 대상을 쓰는 인덱스나 제약은 의미를 구별하는 이름을 명시합니다.

Alembic은 앱과 같은 `Base.metadata`를 사용합니다. 네이밍을 도입했다는 이유로 빈 migration을 만들거나 기존 이름을 일괄 변경하지 않습니다. 실제 테이블 도입 시 생성된 migration과 DB 제약을 함께 검토합니다. 구현 방식은 [SQLAlchemy naming convention](https://docs.sqlalchemy.org/en/20/core/constraints.html#configuring-constraint-naming-conventions)을 따릅니다.

## 변경·버전·삭제

- `created_at`은 생성 시점, `updated_at`은 저장 내용의 변경 시점입니다. 단순 조회로 갱신하지 않습니다.
- `version`은 1에서 시작하고 해당 리소스의 변경 트랜잭션마다 증가합니다. 프로필 연결 테이블·포트폴리오 변경도 같은 프로필 버전을 증가시킵니다.
- 클라이언트의 `expectedVersion`은 오래된 편집 방지용입니다. 정원·권한·소속 검사를 대신하지 않습니다.
- 상태 코드는 영문 소문자로 저장하며 확정된 유한 상태는 `VARCHAR`와 CHECK로 표현합니다. [공통 선택지 7종](catalogs.md#code-enums)은 애플리케이션 enum으로 관리하고 선택값만 `VARCHAR(64)`에 저장합니다. 해당 코드의 허용 목록은 서버에서 검증하며, 코드 테이블 FK·PostgreSQL ENUM·허용값을 복제한 CHECK는 두지 않습니다. 소유자·공고·팀·학사 경로를 참조하는 업무 FK는 유지합니다.
- 별도 명시가 없으면 FK의 삭제·키 갱신은 `RESTRICT`입니다. 키는 변경하지 않습니다. 삭제가 제한된다는 사실은 영구 보존 정책을 뜻하지 않습니다.
- 소속의 `ended_at`, 지원의 `status`처럼 업무상 종료를 표현하는 컬럼과 데이터 삭제는 구분합니다. 모든 테이블에 일반적인 `deleted_at`을 추가하지 않습니다.
- 시연 데이터는 [고정 UUID 시드 목록](../specs/sprint-1.md#demo-data-scope)으로 구분하며 업무 테이블에 `is_demo` 컬럼을 두지 않습니다. 시연 표시가 권한·무결성 제약을 우회하지 않습니다.

계정 탈퇴·팀 삭제·보존 기간은 [미정 사항](decisions.md#open-decisions)이 결정된 뒤 삭제 순서·익명화·참조 처리까지 설계합니다.
