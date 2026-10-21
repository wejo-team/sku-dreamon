# 계정과 프로필 API

**상태: 설계 제안 · 미구현.** 계정·프로필·사람 탐색의 12개 API와 요청·응답 필드를 정의합니다. 경로에는 `/api/v1` 접두사가 붙습니다. JSON 표기와 타입은 [공통 타입](conventions.md#types), 실패 응답은 [오류 계약](conventions.md#errors)을 따릅니다.

| 확인할 내용 | 위치 |
| --- | --- |
| 회원가입·로그인과 본인 계정 | [계정 API](#account-endpoints), [입력·응답 필드](#credentials) |
| 프로필 편집·공개 전환 | [프로필 API](#profile-endpoints), [프로필 필드](#profile) |
| 선택지·학사 목록 | [목록 API](#directory-endpoints), [선택지 필드](#catalog-item) |
| 공개 사람 목록·상세 | [사람 탐색 API](#directory-endpoints), [목록 카드 필드](#person-summary) |

모든 객체는 아래에 정의된 필드만 사용합니다. **본문의 필드는 별도 표시가 없으면 모두 필수**이며, `null` 허용과 필드 생략 허용은 다릅니다. 읽기 전용 필드·선언하지 않은 필드·snake_case를 쓰기 본문으로 보내면 422입니다. 아래 오류 표 외에 모든 API는 공통 `500 INTERNAL_ERROR`, `503 TEMPORARY_UNAVAILABLE`를 사용하며, 상태 변경 요청에는 [공통 CSRF 보호와 실패 응답](conventions.md#session-auth)이 적용됩니다.

<a id="account-endpoints"></a>

## 계정과 로그인

| 메서드·경로 | 접근 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- | --- |
| `POST /accounts` | 공개 | 본문 [Credentials](#credentials) | 201 [SignupResult](#auth-results) | 409 `LOGIN_ID_TAKEN`; 422; 429 `RATE_LIMITED` |
| `GET /auth/login-id-availability` | 공개 | 필수 query `loginId: string` | 200 [LoginIdAvailability](#auth-results) | 422; 429 `RATE_LIMITED` |
| `POST /auth/login` | 공개 | 본문 [Credentials](#credentials) | 200 [LoginResult](#auth-results) | 401 `INVALID_CREDENTIALS`; 422; 429 `RATE_LIMITED` |
| `POST /auth/logout` | 로그인 | 본문 없음 | 204, 본문 없음 | 401 `UNAUTHENTICATED` |
| `GET /me` | 로그인한 본인 | 본문 없음 | 200 [Account](#account) | 401 `UNAUTHENTICATED` |

가입은 자체 로그인 정보를 포함한 `accounts`와 새 `auth_sessions`를 같은 트랜잭션에서 생성하며, 저장 시 아이디 유일성을 확인합니다. 모두 커밋된 뒤 201 `SignupResult`와 `Set-Cookie`를 반환하여 바로 로그인시킵니다. 세션 저장이 실패하면 가입 전체를 롤백하며 성공 응답·인증 쿠키를 발급하지 않습니다. 클라이언트는 가입 성공 후 `GET /me`의 `id`가 `SignupResult.account.id`와 일치하는지 확인하고 프로필 설정으로 이동합니다. 다른 계정의 기존 쿠키가 남아 있다면 자동 로그인 성공으로 취급하지 않고 가입한 계정의 로그인을 안내합니다. 중복 확인 응답은 가입 예약이 아닙니다. 탈퇴 아이디 재사용은 [탈퇴 정책](../specs/profile.md#account-withdrawal)이 확정되기 전에 가입 가능으로 안내하지 않습니다.

가입 응답이 유실되어도 서버의 커밋은 완료되었을 수 있습니다. 클라이언트는 계정을 삭제하거나 자동으로 다시 가입하지 않고 로그인 상태를 확인합니다. 이때 응답 계정 ID를 알 수 없다면 `GET /me`의 `loginId`가 가입 요청의 정규화된 아이디와 일치하는지 확인하고, 미인증·불일치이면 입력한 계정으로 로그인하도록 안내합니다. 일시적인 조회 실패는 가입 실패나 만료로 단정하지 않고 다시 확인할 수 있게 합니다. 이는 MVP에서 제외한 분실 계정 복구 기능을 추가하는 것이 아닙니다.

로그인 실패는 아이디 존재 여부와 비밀번호 오류를 구분하지 않는 `INVALID_CREDENTIALS` 응답을 제안합니다. 화면은 [실패·만료 안내 정책](../specs/authentication.md#auth-failures)에 따라 간단히 안내하고 다시 로그인을 시도할 수 있게 합니다. 로그인 성공 시 새 서버 세션의 저장이 커밋된 뒤 `Set-Cookie`로 토큰을 전달하고, JSON 본문에는 아래 `LoginResult`의 계정 데이터만 반환합니다. 세션 저장에 실패하면 로그인 성공 응답이나 새 인증 쿠키를 발급하지 않습니다.

`GET /me`와 다른 인증 필요 요청은 [공통 서버 세션 검사](conventions.md#session-auth)로 계정을 식별합니다. 만료된 세션은 401을 반환하고 화면에서 재로그인을 안내합니다. 로그아웃은 현재 서버 세션을 즉시 회수하고, 회수를 커밋한 뒤 쿠키를 만료시켜 204를 반환합니다. 동시 로그인을 허용하며 다른 로그인 세션의 상태·수명은 변경하지 않습니다. 성공 후 클라이언트는 계정별 AI 화면·초안을 지우고 진행 중 응답을 취소합니다.

**인증 방식·세션 수명·동시 로그인·브라우저 재시작 후 유지·가입 직후 자동 로그인은 [서버 세션 정책](../specs/authentication.md#session-policy)을 따릅니다.** 별도 로그인 유지 선택 없이 같은 지속 쿠키를 사용하며, 브라우저 재시작으로 세션 만료 시각을 연장하지 않습니다. 로그인·로그아웃·가입에도 [공통 인증·CSRF 계약](conventions.md#session-auth)을 적용하고, 쿠키 이름·경로와 CSRF의 구체 전송 계약 등 남은 결정은 [AUTH 미정 사항](../specs/authentication.md#open-questions)을 따릅니다.

<a id="credentials"></a>

### Credentials — 가입·로그인 요청

| 필드 | 타입 | null | 입력 처리 |
| --- | --- | --- | --- |
| `loginId` | string | 불가 | 앞뒤 공백 제거 → ASCII 소문자화 → `^[a-z0-9]{4,24}$` 검증. 밑줄·하이픈 미허용 |
| `password` | string | 불가 | NFC 정규화 후 Unicode 코드 포인트 15~128개. 공백·대소문자는 보존. 요청 전용으로 응답·오류·로그에 원문을 포함하지 않음 |

아이디 중복 확인의 query `loginId`에도 같은 정규화를 적용합니다. 가입·로그인 요청에 `rememberMe` 등 로그인 유지 선택 필드는 추가하지 않습니다. 정책 원본은 [로그인 아이디](../specs/authentication.md#login-identifier)와 [비밀번호](../specs/authentication.md#password-policy)입니다.

`login_id_normalized`의 [DB 저장 폭](../database/identity.md#accounts)은 향후 확장을 위해 `varchar(320)`으로 두지만, 현재 API는 위 4~24자 규칙을 그대로 적용하며 이메일 로그인을 허용하지 않습니다.

<a id="account"></a>

### Account — 본인 계정 응답

| 필드 | 타입 | null | 의미 |
| --- | --- | --- | --- |
| `id` | Id | 불가 | 계정 UUID |
| `loginId` | string | 불가 | 정규화된 로그인 아이디. `^[a-z0-9]{4,24}$` |
| `isDemo` | boolean | 불가 | 계정용 고정 UUID 시드 목록에 `id`가 포함되는지 서버에서 판정 |
| `hasProfile` | boolean | 불가 | 저장된 프로필 존재 여부 |
| `schoolVerification` | string | 불가 | 현재 허용값은 `unverified` 하나 |
| `createdAt` | Timestamp | 불가 | 계정 생성 시각 |

`Account`는 본인에게만 반환합니다. 다른 사람의 프로필·팀원·AI 응답에 로그인 아이디나 인증 정보를 섞지 않습니다. 학교 이메일·연락처·권한 부여 이력·비밀번호 해시·세션 값은 이 객체에 포함하지 않습니다.

[계정 DB 설계](../database/identity.md#accounts)의 학교 이메일·인증 완료 시각은 후속 인증 기능을 위한 저장 필드입니다. 현재 입력·응답 필드나 인증 API를 추가하지 않으며, `schoolVerification`은 계속 `unverified`만 반환합니다.

<a id="auth-results"></a>

### 가입·로그인·중복 확인 응답

| 객체 | 전체 필드 | 의미 |
| --- | --- | --- |
| `SignupResult` | `account: Account` | 계정·인증 정보·세션 생성 성공. 별도 `Set-Cookie`로 자동 로그인하며 클라이언트는 로그인 상태 확인 후 프로필 설정으로 이동 |
| `LoginResult` | `account: Account` | 본인 계정 데이터. 세션 토큰은 본문에 포함하지 않고 별도 `Set-Cookie`로 전달 |
| `LoginIdAvailability` | `normalizedLoginId: string`, `available: boolean` | 정규화한 아이디와 현재 중복 여부. 아이디 형식은 `^[a-z0-9]{4,24}$` |

모든 필드는 필수이며 `null`을 허용하지 않습니다. 가입·로그인 제한 수치와 기간은 미정이며 429 계약만 제안합니다.

<a id="profile-endpoints"></a>

## 본인 프로필 저장과 공개 전환

| 메서드·경로 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- |
| `GET /me/profile` | 본문 없음 | 200 [Profile](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND` |
| `PUT /me/profile` | 본문 [ProfileWrite](#profile-write) | 최초·수정 모두 200 [Profile](#profile) | 401 `UNAUTHENTICATED`; 409 아래 충돌 코드; 422 |
| `PUT /me/profile/visibility` | 본문 [VisibilityWrite](#visibility-write) | 200 [Profile](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND`; 409 `VERSION_CONFLICT`; 422 |

세 API는 인증 주체 자신의 프로필만 취급합니다. 프로필 미저장 조회는 404입니다. 저장 충돌 코드는 다음과 같습니다.

| 409 코드 | 조건 | 클라이언트 처리 |
| --- | --- | --- |
| `VERSION_CONFLICT` | 요청 버전이 현재 버전과 다름 | 최신 값을 확인하고 편집값을 재검토. 조용히 덮어써 재시도하지 않음 |
| `INVALID_CATALOG_SELECTION` | 선택 코드가 해당 목록·선택 가능 조건에 맞지 않음 | 최신 카탈로그를 확인하고 해당 선택을 수정 |
| `INVALID_ACADEMIC_PATH` | 학사 경로·미배정 값의 조합이 유효하지 않음 | 학사 경로를 다시 확인하고 유효한 조합으로 수정 |

저장 흐름은 다음과 같습니다.

1. 최초 조회가 404이면 전체 편집값과 `expectedVersion="0"`을 보냅니다. 최초 저장의 `version`은 `"1"`, `isPublic`은 `false`입니다.
2. 기존 프로필은 조회한 버전과 전체 편집값을 보냅니다. 기본 항목·연결 목록·포트폴리오는 한 번에 저장하며 일반 편집으로 공개 상태를 바꾸지 않습니다.
3. 공개 전환은 확인 팝업을 거친 뒤 별도 API로 요청합니다. 취소하면 요청하지 않습니다. 현재 버전이 일치해야 하며, 이미 같은 공개 상태이면 상태·버전을 바꾸지 않고 200을 반환합니다.
4. 저장 성공 응답으로 화면을 갱신합니다. 오류이면 기존 저장값을 유지하고 편집값을 보존합니다.

상세 제품 동작은 [프로필 저장](../specs/profile.md#input-validation), [공개 전환](../specs/profile.md#visibility-changes), 저장 원자성과 버전 검사는 [DB 트랜잭션](../database/transactions.md)을 참조합니다.

<a id="profile"></a>

### Profile — 전체 현재 프로필

`Profile`은 아래 서버 필드와 [공통 편집 필드 14개](#profile-fields)를 모두 포함합니다. 모든 필드는 항상 응답하며 미입력은 해당 필드의 `null` 또는 빈 목록으로 표현합니다.

| 서버 필드 | 타입 | null | 의미 |
| --- | --- | --- | --- |
| `accountId` | Id | 불가 | 프로필 소유 계정 |
| `version` | Version | 불가 | 현재 프로필 버전. 양의 BIGINT 십진 문자열 |
| `isPublic` | boolean | 불가 | 현재 전체 프로필 공개 상태 |
| `isDemo` | boolean | 불가 | 계정용 고정 UUID 시드 목록에 `accountId`가 포함되는지 서버에서 판정. 사람 카드·지원자 상세에서도 같은 기준 사용 |
| `updatedAt` | Timestamp | 불가 | 마지막 프로필 변경 시각 |

[시연 데이터 정책](../specs/sprint-1.md#demo-data-scope)에 따라 서버가 리소스 종류와 고정 UUID 시드 목록으로 `isDemo`를 계산합니다. 이름·모델 출력·클라이언트의 추측으로 판정하지 않으며, 프로필 저장·공개 전환 요청에서 이 값을 받지 않습니다.

권한이 있는 조회에서만 전체 프로필을 반환합니다. 교내 인증은 현재 [미인증 표시 규칙](../specs/authentication.md#verification-meaning)을 사용하므로 `Profile`에 별도 인증 상태 필드를 추가하지 않습니다. 화면은 미인증으로 표시하며 실제 학교 인증이 도입되면 별도 계약 변경이 필요합니다. 로그인 아이디·인증 정보·미수집 연락처는 포함하지 않습니다.

<a id="profile-fields"></a>

### 프로필 조회·저장의 공통 편집 필드

이 표의 **14개 키를 모두 포함**합니다. 선택 입력도 키를 생략하지 않고 `null` 또는 `[]`를 전송합니다. 문자열 길이의 정책 수치는 아래와 같고, 비밀번호 외 텍스트의 Unicode 계수·정규화 세부는 [PROFILE-07](../specs/profile.md#open-questions)에 남깁니다.

| 필드 | 타입 | null | 값·제약 |
| --- | --- | --- | --- |
| `realName` | string | 불가 | 앞뒤 공백 제거 후 1~50자 |
| `avatarCode` | CatalogCode | 허용 | 제공된 `avatarPresets` 코드. 미선택은 `null`, 화면 기본 이미지는 스콘 |
| `academicStatusCode` | CatalogCode | 허용 | `academicStatuses` 코드 |
| `gradeCode` | CatalogCode | 허용 | `grades` 코드 |
| `weeklyAvailabilityCode` | CatalogCode | 허용 | `weeklyAvailabilityRanges` 코드. 네 구간 중 하나 또는 미입력 |
| `academicPlacementId` | Id | 허용 | 선택한 학사 경로의 ID. 상위 경로는 [AcademicPlacement](#academic-placement)의 부모 연결로 해석 |
| `majorUnassigned` | boolean | 불가 | 해당 학사 경로에서 허용한 전공 미배정 여부. 경로가 없으면 `false` |
| `experienceState` | ExperienceState | 불가 | `unspecified`, `none`, `provided`. [상태별 본문 조합](#experience) 적용 |
| `experienceBody` | string | 허용 | 앞뒤 공백 제거 후 최대 500자. 응답의 상태와 본문은 아래 조합을 충족 |
| `introduction` | string | 허용 | 앞뒤 공백 제거 후 최대 300자 |
| `fieldCodes` | CatalogCode[] | 불가 | 관심 분야 1~3개, 중복 불가 |
| `roleCodes` | CatalogCode[] | 불가 | 희망 역할 1~2개, 중복 불가 |
| `skillCodes` | CatalogCode[] | 불가 | 목록 내 보유 역량, 중복 불가. 개수 상한 없음. 해제는 `[]` |
| `portfolio` | [Portfolio](#portfolio) | 허용 | 등록된 URL 1개와 선택 제목. 전체 제거는 `null` |

코드는 [Catalogs](#catalogs)로 표시명을 해석합니다. 새 선택은 현재 유효한 항목이어야 하며, 기존 비활성 학사 경로를 그대로 유지한 다른 항목의 수정은 허용합니다. 학사 경로·전공 미배정 조합은 [학사 저장 정책](../specs/academic-structure.md#selection-policy)에 따라 검증하며, 상위값 변경 시 [유효하지 않은 하위 선택만 초안에서 초기화](../specs/academic-structure.md#dependent-selection)합니다.

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

전체 키는 [공통 편집 필드 14개](#profile-fields)와 `expectedVersion`입니다. `expectedVersion`은 `NonnegativeBigInt`이며 최초 `"0"`, 수정 시 조회한 `version`을 넣습니다. `accountId`, `version`, `updatedAt`, `isPublic`, `isDemo`는 받지 않습니다.

최초 저장 요청 예시입니다. `FIELD_EXAMPLE`과 `ROLE_EXAMPLE`은 문서용 코드이며 실제 카탈로그 값은 아닙니다.

```json
{
  "expectedVersion": "0",
  "realName": "예시 사용자",
  "avatarCode": null,
  "academicStatusCode": null,
  "gradeCode": null,
  "weeklyAvailabilityCode": null,
  "academicPlacementId": null,
  "majorUnassigned": false,
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

## 선택지와 공개 사람 탐색

| 메서드·경로 | 접근 | 입력 | 성공 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /catalogs` | 공개 | 없음 | 200 [Catalogs](#catalogs) | 공통 500·503 |
| `GET /catalogs/academic-placements` | 공개 | 없음 | 200 [AcademicCatalog](#academic-placement) | 공통 500·503 |
| `GET /people` | 로그인 | 아래 query | 200 `Page<PersonSummary>` | 401 `UNAUTHENTICATED`; 422 |
| `GET /people/{accountId}` | 로그인 | 필수 path `accountId: Id` | 200 [Profile](#profile) | 401 `UNAUTHENTICATED`; 404 `RESOURCE_NOT_FOUND`; 422 |

### 사람 목록 검색 조건

| query | 타입 | 필수·기본값 | 의미 |
| --- | --- | --- | --- |
| `q` | string | 선택, 생략은 검색 없음 | 앞뒤 공백 제거. 빈 문자열도 검색 없음. 이름·자기소개·분야·역할·역량 표시명 검색 제안 |
| `fieldCode` | CatalogCode | 선택, 생략은 분야 제한 없음 | 관심 분야 중 해당 코드 하나를 포함하는 사람 |
| `roleCode` | CatalogCode | 선택, 생략은 역할 제한 없음 | 희망 역할 중 해당 코드 하나를 포함하는 사람 |
| `page` | integer | 선택, `1` | 1 이상 안전 정수. 마지막 페이지 초과는 마지막 유효 페이지로 보정 |
| `pageSize` | integer | 선택, `20` | 1~100. 기본·최대 크기는 기술 제안 |

정렬은 `updatedAt DESC, accountId ASC`입니다. `Page<PersonSummary>`는 필수 `items: PersonSummary[]`, `pagination: PageMeta`로 구성됩니다. 두 값은 `null`을 허용하지 않으며 [공통 페이지 계약](conventions.md#pagination)의 조회·집계 일치와 빈 결과 처리를 적용합니다.

현재 공개 프로필만 목록·집계에 포함합니다. 비공개·미존재 상세는 같은 404로 처리합니다. 지원받은 팀장도 `/people`에서는 이 경계를 지키며 비공개 열람 예외는 [지원자 상세 API](contests-teams.md)의 `/applications/{applicationId}/applicant`에서 관계를 확인합니다. 제품 정책 원본은 [사람 탐색](../specs/profile.md#people-directory)입니다.

<a id="person-summary"></a>

### PersonSummary — 공개 사람 카드

| 필드 | 타입 | null | 의미·제약 |
| --- | --- | --- | --- |
| `accountId` | Id | 불가 | 프로필 소유 계정 |
| `realName` | string | 불가 | 현재 실명, 프로필의 길이 기준 적용 |
| `isDemo` | boolean | 불가 | 계정용 고정 UUID 시드 목록에 `accountId`가 포함되는지 서버에서 판정. 카드의 시연 표시 근거 |
| `avatarCode` | CatalogCode | 허용 | 현재 이미지 선택. 미선택 기본 표시는 Profile과 같음 |
| `introduction` | string | 허용 | 현재 자기소개, 최대 300자 |
| `fieldCodes` | CatalogCode[] | 불가 | 관심 분야 1~3개, 중복 없음 |
| `roleCodes` | CatalogCode[] | 불가 | 희망 역할 1~2개, 중복 없음 |
| `skillCodes` | CatalogCode[] | 불가 | 역량 목록, 중복 없음. 미선택은 `[]` |

학사 정보·포트폴리오 등 상세 항목은 권한을 확인한 `Profile` 조회로 제공합니다. 공개 미리보기는 본인의 현재 프로필을 화면에 보여주는 동작이며 실제 공개 전환 요청이 아닙니다.

<a id="catalog-item"></a>

## 선택지 응답 필드

### CatalogItem과 AvatarPreset

| 필드 | 타입 | null | 의미 |
| --- | --- | --- | --- |
| `code` | CatalogCode | 불가 | 목록 내 불변 코드 |
| `displayName` | string | 불가 | 화면 표시명 |
| `isSelectable` | boolean | 불가 | 현재 새 선택 가능 여부 |
| `sortOrder` | integer (int32) | 불가 | 목록 정렬값 |

`CatalogItem`은 위 네 필드입니다. `AvatarPreset`은 위 네 필드와 **필수 `assetUrl: HttpUrl`**을 포함하며 `assetUrl`은 `null`을 허용하지 않습니다. 실제 아바타 코드는 [공통 카탈로그](../database/catalogs.md)에서 관리하며, 별도 파일 업로드 요청을 추가하지 않습니다.

<a id="catalogs"></a>

### Catalogs — 전체 공통 선택지

| 필드 | 타입 | 제공 목록 |
| --- | --- | --- |
| `fields` | CatalogItem[] | 관심·공모전 분야 |
| `roles` | CatalogItem[] | 희망·모집 역할 |
| `skills` | CatalogItem[] | 보유 역량 |
| `academicStatuses` | CatalogItem[] | 학적 상태 |
| `grades` | CatalogItem[] | 학년 |
| `weeklyAvailabilityRanges` | CatalogItem[] | 주당 참여 가능 시간 |
| `avatarPresets` | AvatarPreset[] | 프로필 이미지 선택지 |

일곱 목록은 모두 필수이며 `null`을 허용하지 않습니다. 각 목록은 `sortOrder ASC, code ASC`로 정렬합니다. 현재 선택 가능 항목과 기존 데이터의 표시를 위한 비활성 항목을 함께 제공합니다. 새 선택에는 `isSelectable=true`만 사용하며 실제 코드 사전은 [카탈로그 관리](../specs/profile-options.md#catalog-management)에서 검토합니다.

<a id="academic-placement"></a>

### AcademicPlacement와 AcademicCatalog — 학사 경로

`AcademicCatalog`의 전체 필드는 **필수 `items: AcademicPlacement[]`** 하나이며 `null`을 허용하지 않습니다. 현재·비활성 경로를 `id ASC`로 반환하며 부모 관계로 화면 트리를 구성합니다. 정렬은 기술 제안이며 학사 표시 순서 정책을 추가하는 의미가 아닙니다.

| AcademicPlacement 필드 | 타입 | null | 의미·허용값 |
| --- | --- | --- | --- |
| `id` | Id | 불가 | 학사 배치 경로 ID |
| `unitId` | Id | 불가 | 학사 단위 ID |
| `unitCode` | CatalogCode | 불가 | 학사 단위 불변 코드 |
| `kind` | string | 불가 | `college`, `department`, `major` |
| `label` | string | 불가 | 표시 이름 |
| `parentPlacementId` | Id | 허용 | 부모 경로. 루트는 `null` |
| `isSelectable` | boolean | 불가 | 현재 새 선택 가능 여부 |
| `majorSelectionMode` | string | 허용 | `none`, `selectable` 또는 `null` |
| `allowsUnassigned` | boolean | 불가 | 이 경로에서 전공 미배정 허용 여부 |
| `effectiveScope` | string | 허용 | 적용 범위 정보. 미입력은 `null` |
| `sourceReference` | string | 불가 | 공식 웹 주소 또는 공식 자료 식별 참조 |

실제 초기 학사 코드·공식 현행 목록과 미배정 가능 범위는 [학사 미정 사항](../specs/academic-structure.md#open-questions)을 검토한 뒤 등록합니다. 응답 구조가 존재한다는 이유로 이 목록이 확정되었다고 판단하지 않습니다.

## DB 연결과 남은 범위

| API 정보 | DB 원본 |
| --- | --- |
| `Account`·로그인·`isDemo` | [계정과 프로필 테이블](../database/identity.md), [시연 데이터 식별](../specs/sprint-1.md#demo-data-scope) |
| `Profile`·버전·연결 목록·포트폴리오 | [계정과 프로필 테이블](../database/identity.md) |
| 코드·학사 경로 | [공통 카탈로그](../database/catalogs.md) |

계정 탈퇴·파일 업로드·학교 인증 API는 이번 설계에 추가하지 않습니다. [계정 복구](../specs/authentication.md#account-recovery)는 MVP 범위에서 제외하므로 복구 API를 만들지 않으며 현재 인증 구현의 선행 조건으로 두지 않습니다. 팀 생성·개인화 추천의 프로필 완성 요구, 일반 텍스트 Unicode 처리, 포트폴리오 URL 길이 등 남은 결정은 [프로필 미정 사항](../specs/profile.md#open-questions)에 둡니다.
