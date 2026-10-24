# 프로필 API

**상태: 조회·전체 저장·공개 전환 구현.** `GET /me/profile`, `GET /people`, `GET /people/{accountId}`를 [프로필 라우터](../../backend/app/routers/profiles.py)에서 제공합니다. 본인 전체 저장·공개 전환은 [쓰기 DTO](../../backend/app/schemas/profile_write.py)·[트랜잭션 서비스](../../backend/app/services/profile_write.py)·[DB/HTTP 테스트](../../backend/tests/integration/test_profile_write.py)를 따릅니다. 경로에는 `/api/v1` 접두사가 붙습니다. JSON 표기와 타입은 [공통 타입](conventions.md#types), 실패 응답은 [오류 계약](conventions.md#errors)을 따릅니다.

구현된 조회의 정확한 필드·query·오류 응답은 [응답 DTO와 query 모델](../../backend/app/schemas/profiles.py), 실행 앱의 `/docs`·`/openapi.json`이 원본입니다. [HTTP·PostgreSQL 검증](../../backend/tests/integration/test_people_api.py)에서 공개 범위·필터·페이지 보정·동시 공개 변경과 읽기 시점의 일치를 확인합니다. 읽기 서비스는 저장된 텍스트를 반환하며 미정인 입력 정규화·길이 계약을 확정하지 않습니다.

| 확인할 내용 | 위치 |
| --- | --- |
| 본인 프로필 저장·공개 전환 | [프로필 API](#profile-endpoints), [Profile](#profile), [ProfileWrite](#profile-write) |
| 공개 사람 목록·상세 | [사람 탐색 API](#directory-endpoints), [PersonSummary](#person-summary) |
| 공통 선택지·학사 목록 | [선택지 API](catalogs.md) |

모든 객체는 아래에 정의된 필드만 사용합니다. **본문의 필드는 별도 표시가 없으면 모두 필수**이며, `null` 허용과 필드 생략 허용은 다릅니다. 읽기 전용 필드·선언하지 않은 필드·snake_case를 쓰기 본문으로 보내면 422입니다. 아래 오류 표 외에 모든 API는 공통 `500 INTERNAL_ERROR`, `503 TEMPORARY_UNAVAILABLE`를 사용하며, 상태 변경 요청에는 [공통 CSRF 보호와 실패 응답](conventions.md#session-auth)이 적용됩니다.

성공 응답의 본문은 [공통 성공 응답](conventions.md#success-responses)을 따르며, 아래 응답 DTO 표는 `data` 안의 값과 하위 객체를 정의합니다.

<a id="profile-endpoints"></a>

## 본인 프로필 저장과 공개 전환

| 메서드·경로 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- |
| `GET /me/profile` | 본문 없음 | 200 [Success&lt;Profile&gt;](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND` |
| `PUT /me/profile` | 본문 [ProfileWrite](#profile-write) | 최초·수정 모두 200 [Success&lt;Profile&gt;](#profile) | 401 `UNAUTHENTICATED`; 409 아래 충돌 코드; 422 |
| `PUT /me/profile/visibility` | 본문 [VisibilityWrite](#visibility-write) | 200 [Success&lt;Profile&gt;](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND`; 409 `VERSION_CONFLICT`; 422 |

세 API는 인증 주체 자신의 프로필만 취급합니다. 프로필 미저장 조회는 404입니다. 저장 충돌 코드는 다음과 같습니다.

| 409 코드 | 조건 | 클라이언트 처리 |
| --- | --- | --- |
| `VERSION_CONFLICT` | 요청 버전이 현재 버전과 다름 | 최신 값을 확인하고 편집값을 재검토. 조용히 덮어써 재시도하지 않음 |
| `INVALID_CATALOG_SELECTION` | 선택 코드가 해당 목록·선택 가능 조건에 맞지 않음 | 최신 카탈로그를 확인하고 해당 선택을 수정 |
| `INVALID_ACADEMIC_PATH` | 선택한 학사 항목의 부모 경로·계층이 유효하지 않음 | 학사 목록을 다시 확인하고 유효한 항목으로 수정 |

저장 흐름은 다음과 같습니다.

1. 최초 조회가 404이면 전체 편집값과 `expectedVersion="0"`을 보냅니다. 최초 저장의 `version`은 `"1"`, `isPublic`은 `false`입니다.
2. 기존 프로필은 조회한 버전과 전체 편집값을 보냅니다. 기본 항목·연결 목록·포트폴리오는 한 번에 저장하며 일반 편집으로 공개 상태를 바꾸지 않습니다.
3. 공개 전환은 확인 팝업을 거친 뒤 별도 API로 요청합니다. 취소하면 요청하지 않습니다. 현재 버전이 일치해야 하며, 이미 같은 공개 상태이면 상태·버전을 바꾸지 않고 200을 반환합니다.
4. 저장 성공 응답으로 화면을 갱신합니다. 오류이면 기존 저장값을 유지하고 편집값을 보존합니다.

상세 제품 동작은 [프로필 저장](../specs/profile.md#input-validation), [공개 전환](../specs/profile.md#visibility-changes), 저장 원자성과 버전 검사는 [DB 트랜잭션](../database/transactions.md)을 참조합니다.

<a id="profile"></a>

### Profile — 전체 현재 프로필

`ProfileResponse`의 전체 필드는 [응답 모델](../../backend/app/schemas/profiles.py)과 생성 OpenAPI에서 확인합니다. `accountId`는 공유 PK인 `profiles.profile_id`를 명시적으로 매핑하고, `version`·`academicUnitId`는 십진 문자열로 전달합니다. 모든 키를 항상 반환하며 미입력은 해당 필드의 `null` 또는 빈 목록으로 표현합니다. 아래 [공통 편집 필드](#profile-fields)는 아직 구현하지 않은 저장 요청의 설계로 유지합니다.

[시연 데이터 정책](../specs/sprint-1.md#demo-data-scope)에 따라 서버가 리소스 종류와 고정 UUID 시드 목록으로 `isDemo`를 계산합니다. 이름·모델 출력·클라이언트의 추측으로 판정하지 않으며, 프로필 저장·공개 전환 요청에서 이 값을 받지 않습니다.

권한이 있는 조회에서만 전체 프로필을 반환합니다. 교내 인증은 현재 [미인증 표시 규칙](../specs/authentication.md#verification-meaning)을 사용하므로 `Profile`에 별도 인증 상태 필드를 추가하지 않습니다. 화면은 미인증으로 표시하며 실제 학교 인증이 도입되면 별도 계약 변경이 필요합니다. 로그인 아이디·인증 정보·미수집 연락처는 포함하지 않습니다.

<a id="profile-fields"></a>

### 프로필 저장의 편집 필드 설계

이 표의 **13개 키를 모두 포함**합니다. 선택 입력도 키를 생략하지 않고 `null` 또는 `[]`를 전송합니다. 문자열은 2026-10-24 사용자 결정에 따라 NFC·앞뒤 공백 제거 후 Unicode 코드 포인트로 셉니다. 운영 URL 상한 등 추가 제한은 도입하지 않습니다.

정확한 13개 필드와 길이·개수는 [ProfileWrite](../../backend/app/schemas/profile_write.py)와 생성 OpenAPI에서 확인합니다. 선택 필드도 생략하지 않고 null 또는 빈 배열을 전달합니다.

코드는 [Catalogs](catalogs.md#catalogs)로 표시명을 해석하며 서버의 같은 공통 enum으로 입력을 검증합니다. 새 선택은 현재 유효한 항목이어야 하며, 기존 비활성 학사 경로를 그대로 유지한 다른 항목의 수정은 허용합니다. 학사 항목과 부모 경로는 [학사 저장 정책](../specs/academic-structure.md#selection-policy)에 따라 검증하며, 상위값 변경 시 [유효하지 않은 하위 선택만 초안에서 초기화](../specs/academic-structure.md#dependent-selection)합니다.

<a id="experience"></a>

### ExperienceState — 경험 상태와 본문

| 저장 후 상태 | `experienceBody` 응답 | 요청 정규화 |
| --- | --- | --- |
| `unspecified` | `null` | 미입력으로 저장하며 경험 유무를 추정하지 않음 |
| `none` | `null` | 이전 본문 제거 |
| `provided` | 공백 제거 후 비어 있지 않은 string | 본문이 공백 제거 후 비면 `unspecified`와 `null`로 저장. 최대 500자 초과는 422 |

편집 취소와 상태 전환의 제품 동작은 [경험 명세](../specs/profile.md#experience)를 참조합니다. 서버는 정규화한 상태·본문을 응답하여 클라이언트가 보낸 불일치 초안을 그대로 표시하지 않게 합니다.

<a id="portfolio"></a>

### Portfolio — 선택 포트폴리오

| 필드 | 타입 | null | 제약 |
| --- | --- | --- | --- |
| `url` | HttpUrl | 불가 | HTTP(S) 절대 URL. 길이 상한은 PROFILE-07에서 결정 |
| `title` | string | 허용 | 선택 제목, 앞뒤 공백 제거 후 최대 50자 |

객체가 있으면 두 키를 모두 포함합니다. URL 제거는 `portfolio: null`로 보내 제목까지 함께 지웁니다. URL 없는 제목 객체·잘못된 URL은 422입니다. 파일 업로드·외부 내용 AI 분석은 [포트폴리오 정책](../specs/profile.md#portfolio)에 포함되지 않습니다.

<a id="profile-write"></a>

### ProfileWrite — 전체 편집 요청

전체 키는 [공통 편집 필드 13개](#profile-fields)와 `expectedVersion`입니다. `expectedVersion`은 `NonnegativeBigInt`이며 최초 `"0"`, 수정 시 조회한 `version`을 넣습니다. `accountId`, `version`, `updatedAt`, `isPublic`, `isDemo`는 받지 않습니다.

최초 저장 요청 예시입니다. `FIELD_EXAMPLE`과 `ROLE_EXAMPLE`은 문서용 코드이며 실제 카탈로그 값은 아닙니다.

```json
{
  "expectedVersion": "0",
  "realName": "예시 사용자",
  "profileImageCode": null,
  "academicStatusCode": null,
  "gradeCode": null,
  "weeklyAvailabilityCode": null,
  "academicUnitId": null,
  "experienceState": "unspecified",
  "experienceBody": null,
  "introduction": null,
  "fieldCodes": ["FIELD_EXAMPLE"],
  "roleCodes": ["ROLE_EXAMPLE"],
  "skillCodes": [],
  "portfolio": null
}
```

<a id="visibility-write"></a>

### VisibilityWrite — 공개 상태 변경 요청

| 필드 | 타입 | null | 제약 |
| --- | --- | --- | --- |
| `expectedVersion` | Version | 불가 | 저장된 프로필의 현재 양의 버전 |
| `isPublic` | boolean | 불가 | 확인 팝업에서 결정한 공개 상태 |

버전을 먼저 검사합니다. 같은 상태를 요청하더라도 과거 버전이면 409이며, 현재 버전과 상태가 모두 같을 때만 변경 없는 200입니다. 일반 검색·AI의 후속 응답에는 저장된 새 공개 상태를 적용합니다.

<a id="directory-endpoints"></a>

## 공개 사람 탐색

| 메서드·경로 | 접근 | 입력 | 성공 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /people` | 로그인 | 아래 query | 200 `Page<PersonSummary>` | 401 `UNAUTHENTICATED`; 422 |
| `GET /people/{accountId}` | 로그인 | 필수 path `accountId: Id` | 200 [Success&lt;Profile&gt;](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND`; 422 |

### 사람 목록 검색 조건

정확한 query 이름·타입·기본값·범위는 [PeopleQuery](../../backend/app/schemas/profiles.py)와 생성 OpenAPI를 따릅니다. 선언하지 않은 query와 snake_case 이름은 422로 거부합니다. `q`는 앞뒤 공백을 제거하고 이름·자기소개·분야·역할·역량의 표시명을 검색하며, 빈 문자열은 검색 없음입니다. `%`·`_`는 SQL 패턴이 아닌 검색 문자로 취급합니다. 분야·역할 필터는 해당 선택 코드가 포함된 사람만 반환하며 여러 일치 항목 때문에 한 사람이 중복되지 않습니다.

정렬은 `updatedAt DESC, accountId ASC`입니다. `Page<PersonSummary>`는 필수 `data: PersonSummary[]`, `pagination: PageMeta`로 구성됩니다. 두 값은 `null`을 허용하지 않으며 [공통 페이지 계약](conventions.md#pagination)의 조회·집계 일치와 빈 결과 처리를 적용합니다.

[조회 서비스](../../backend/app/services/profiles.py)와 [저장 접근](../../backend/app/repositories/profiles.py)는 별도 인증 처리가 끝난 새 요청 DB 세션에서 REPEATABLE READ로 읽습니다. 목록·총원·프로필 선택 항목을 같은 스냅샷에서 조회하고, 범위를 넘는 페이지는 마지막 페이지로 보정합니다. 공개 변경 이후 시작한 다음 요청은 새 공개 상태를 반영합니다. 이 서비스는 commit하지 않으며 요청 세션 종료 시 읽기 트랜잭션을 정리합니다.

현재 공개 프로필만 목록·집계에 포함합니다. 비공개·미존재 상세는 같은 404로 처리합니다. 지원받은 팀장도 `/people`에서는 이 경계를 지키며 비공개 열람 예외는 [지원자 상세 API](applications.md#applicant)의 `/applications/{applicationId}/applicant`에서 관계를 확인합니다. 제품 정책 원본은 [사람 탐색](../specs/profile.md#people-directory)입니다.

<a id="person-summary"></a>

### PersonSummary — 공개 사람 카드

정확한 필드·필수값·NULL·선택 코드 타입은 [PersonSummary](../../backend/app/schemas/profiles.py)와 생성 OpenAPI가 원본입니다. 카드에는 소유 계정 ID와 현재 이름·이미지·소개·분야·역할·역량 및 고정 UUID 목록 기반 시연 표시를 제공합니다. 인증정보나 비공개 프로필은 이 객체를 통해 노출하지 않습니다.

학사 정보·포트폴리오 등 상세 항목은 권한을 확인한 `Profile` 조회로 제공합니다. 공개 미리보기는 본인의 현재 프로필을 화면에 보여주는 동작이며 실제 공개 전환 요청이 아닙니다.

## DB 연결과 남은 범위

| API 정보 | 저장·정의 원본 |
| --- | --- |
| `Profile`·버전·연결 목록·포트폴리오 | [계정과 프로필 테이블](../database/identity.md) |

파일 업로드 API는 이번 설계에 추가하지 않습니다. 팀 생성·개인화 추천의 프로필 완성 요구, 일반 텍스트 Unicode 처리, 포트폴리오 URL 길이 등 남은 결정은 [프로필 미정 사항](../specs/profile.md#open-questions)에 둡니다. 계정·로그인 응답은 [인증 API](auth.md), 선택지 응답은 [선택지 API](catalogs.md)가 원본입니다.

## 쓰기 검증

최초 버전 0→1, 기본 비공개, 전체 편집의 공개 상태 보존, 명시적 null·빈 배열 삭제, 최신 버전 충돌, 같은 공개 상태의 무변경 응답을 검증합니다. 계정→프로필 잠금으로 동시 최초 저장의 하나만 성공하며, 연결 저장 실패에는 본문·버전·선택지를 모두 롤백합니다. 학사 검증은 기존 비활성 선택 유지와 새 경로 검사를 재사용합니다.
