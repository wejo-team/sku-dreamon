# API 공통 계약

이 문서는 **검토용 전송 설계**입니다. 제품 정책은 [기능 명세](../specs/README.md), 물리 저장 형식은 [DB 공통 기준](../database/conventions.md), 개별 요청·응답 필드는 [영역별 API 문서](README.md)를 따릅니다. 공통 타입·페이지·오류는 여기서만 정의합니다.

<a id="types"></a>

## 주소와 값의 표현

| 항목 | 계약 |
| --- | --- |
| 경로 | `/api/v1` 아래 리소스 경로. 아래 영역 문서의 표는 이 접두사를 생략 |
| 본문 | `application/json`, camelCase. 선언하지 않은 필드·snake_case·혼용 요청은 422 |
| ID | 사용자·공고·팀·지원·알림 ID는 UUID 문자열. 로그인 아이디·표시명과 분리 |
| 코드 | 분야·역할·역량 등은 최대 64자의 카탈로그 코드. 표시명으로 저장 요청하지 않음 |
| BIGINT | `version`, `expectedVersion`, `capacity`, `minimumMembers`, `maximumMembers`는 **십진 문자열**. 예: `"4"`. 최대 `9223372036854775807`은 저장 표현 한계이며 서비스 정원 상한이 아님 |
| 개수·페이지 | `page`, `pageSize`, `total`, `memberCount` 등은 JSON 정수. 안전 정수 범위를 벗어나는 집계가 필요해지면 계약 버전을 먼저 변경 |
| 시각 | UTC ISO 8601의 `Z` 표기. 원문 시간대·마감 보완 사실은 별도 필드로 제공 |
| 선택 항목 | 미입력은 `null`, 비어 있는 목록은 `[]`. 필드의 생략 가능 여부와 NULL 허용은 별개이며 영역별 표에 명시 |
| 편집 저장 | 프로필 전체 저장은 `PUT`. 선택값 삭제는 명시적 `null` 또는 `[]`; 생략을 삭제로 추정하지 않음 |

### 공통 타입과 표 읽기

아래 타입 이름은 문서에서 반복을 줄이는 표기입니다. 예를 들어 `Id`는 JSON에서 UUID **문자열**, `Page<Profile>`은 아래 페이지 객체입니다. 구현 클래스명이나 추가 JSON 감싸기를 요구하지 않습니다.

| 타입 | JSON 표현·검증 |
| --- | --- |
| `Id` | UUID 문자열. 특정 UUID 생성 버전을 전제하지 않음 |
| `Timestamp` | 유효한 날짜·시각을 담은 UTC ISO 8601 문자열, 끝은 `Z` |
| `CatalogCode` | 길이 1~64인 코드 문자열. 해당 분류 목록의 실제 코드인지 별도 확인 |
| `HttpUrl` | `http://` 또는 `https://`로 시작하는 유효한 절대 URL. 입력 URL의 운영 길이 상한은 PROFILE-07 미정 |
| `PositiveBigInt` | 1~9223372036854775807의 십진 문자열. 부호·소수점·선행 0 없음 |
| `NonnegativeBigInt` | `PositiveBigInt` 또는 문자열 `"0"` |
| `Version` | `PositiveBigInt`. 리소스 변경 버전 |
| `integer` | 소수부 없는 JSON 숫자. 개수·순번·시도·페이지는 최대 9007199254740991. 각 필드의 최소값·별도 최대값 우선 |
| `int32` | -2147483648~2147483647의 JSON 정수. 카탈로그 `sortOrder` 등에서 사용 |
| `boolean` | JSON `true` / `false` |
| `string` | JSON 문자열. 길이·정규화는 해당 필드 계약을 따름 |
| `T[]` | 타입 `T`의 배열. 빈 배열 허용 여부·최소/최대 개수·중복 금지는 개별 표에 명시 |

- 요청 표의 **필수**는 JSON 키 또는 query 항목이 있어야 한다는 뜻입니다. NULL 허용 필드라도 필수 키라면 생략할 수 없습니다.
- 응답은 표에 적힌 키를 모두 반환합니다. 값이 없으면 허용한 곳에서만 `null` 또는 `[]`를 반환하며 키를 임의 생략하지 않습니다.
- 개별 정의의 `T 또는 null`은 타입 `T`와 JSON `null`만 허용합니다. 문자열 `"null"`·빈 문자열·0을 미입력 대용으로 사용하지 않습니다.
- 선언하지 않은 객체 필드는 요청·응답 계약에 없습니다. 요청은 중첩 객체까지 검증하여 오타·snake_case·혼용을 422로 거부하고 응답에는 인증정보 등 추가 값을 섞지 않습니다.
- `A의 전체 필드 + 아래 필드` 표기는 평탄한 객체 확장입니다. 실제 JSON에 `A`라는 하위 객체를 만들지 않습니다. 이름을 가진 하위 필드 표는 그 이름의 객체로 반환합니다.

일반 프로필·팀·메시지 텍스트의 길이 상한은 영역별 표와 연결된 기능 명세를 참조합니다. Unicode 계수 단위가 미정인 항목은 정책상의 글자 수와 계수 방식 미정을 함께 표시합니다. 비밀번호는 이미 확정된 [NFC·Unicode 코드 포인트 기준](../specs/authentication.md#password-policy)을 적용합니다. 계수 단위를 임의로 확정하거나 입력을 잘라 저장하지 않습니다.

<a id="access"></a>

## 인증과 권한

API 설계에서 **누가 무엇을 할 수 있는지**와 **인증을 어떻게 전송하는지**를 구분합니다.

| 접근 구분 | 의미 |
| --- | --- |
| `public` | 공개 공고·팀·공통 목록 등 로그인 없이 허용된 조회 또는 가입·로그인 |
| `authenticated` | 현재 로그인 필요 |
| `self` | 인증 주체 자신의 리소스. 클라이언트가 보낸 사용자 ID를 소유자로 신뢰하지 않음 |
| `owner` / `recipient-leader` | 해당 팀장 또는 해당 지원을 받은 팀장 |
| `applicant` / `applicant-or-recipient-leader` | 지원 본인 또는 명시된 지원 관계 |
| `current-team-member` | 현재 팀장·확정 팀원 |
| `current-conversation-owner` / `request-owner-and-current-context` | 로그인 주체와 현재 AI 이용 맥락 및 대상 관계가 모두 일치 |

각 API의 실제 허용 범위는 [접근 정책](../specs/authentication.md#access-policy)과 [프로필 공개 범위](../specs/profile.md#visibility)를 참조합니다. 일반 사람 상세, 지원 팀장의 지원자 상세, 팀 공간은 서로 다른 경로와 DTO로 분리합니다. 관리자의 공고 관리 권한이 비공개 프로필 조회 권한을 뜻하지 않습니다.

<a id="session-auth"></a>

### 서버 세션과 쿠키 전달

[서버 세션 정책](../specs/authentication.md#session-policy)에 따라 PostgreSQL에 로그인 상태를 저장하고, 브라우저에는 불투명한 세션 토큰을 쿠키로 전달합니다. 세션 저장 필드·제약은 [인증 세션 DB 설계](../database/identity.md#auth-sessions)를 따릅니다.

| 단계 | API 계약 |
| --- | --- |
| 로그인 성공 | 암호학적으로 안전한 난수로 새 토큰을 생성하고, 서버에는 SHA-256 해시와 세션 상태를 저장. 저장 트랜잭션이 커밋된 뒤 `Set-Cookie`로 원문 토큰 전달 |
| 쿠키 속성 | `HttpOnly`, `Secure`, `SameSite=Lax`. `Domain`을 지정하지 않는 host-only 쿠키. 운영에서는 HTTPS 사용 |
| 인증이 필요한 요청 | 브라우저가 전송한 쿠키의 토큰을 해시하여 서버 세션 조회. 존재·회수 여부·유휴 만료·절대 만료를 공통 인증 의존성에서 검사하고 계정 식별 |
| 현재 세션 로그아웃 | 서버 세션 회수를 커밋한 뒤 같은 이름·범위의 쿠키를 만료시킴. 쿠키 삭제만으로 로그아웃을 완료하지 않음 |

인증이 필요한 요청에 토큰이 없거나 세션이 존재하지 않거나 회수·만료되었으면 `401 UNAUTHENTICATED`입니다. 유휴 만료는 마지막 사용 시각을 갱신하기 **전에** 검사하며, 활동이 있어도 절대 만료 시각을 넘길 수 없습니다. 세션에서 얻은 계정 ID로 각 API의 현재 소속·지원·프로필 접근 관계를 다시 확인합니다. 세션에 저장된 과거 권한만으로 요청을 허용하지 않습니다.

세션 토큰 원문·해시는 JSON 응답에 포함하지 않습니다. 프론트엔드는 세션 토큰을 JavaScript나 `localStorage`로 관리하지 않으며 브라우저의 쿠키 전달을 사용합니다. 현재 계약에 JWT·Bearer 인증이나 재발급 endpoint를 추가하지 않습니다.

로그인·로그아웃을 포함한 모든 상태 변경 요청에 CSRF 보호를 적용합니다. `HttpOnly`·`SameSite`만으로 보호가 완성되었다고 판단하지 않습니다. CSRF 검사 실패는 공통 `403 FORBIDDEN`이며 업무 상태를 변경하지 않습니다. 이 규칙은 각 endpoint 표에 반복하지 않고 공통으로 적용합니다.

**구체 전송 계약은 후속 설계가 필요합니다.** 쿠키 이름·경로·브라우저 보존 설정, 로그인 전 CSRF 보호값 발급·전달 헤더·검증 방식, 운영 도메인·CORS와 로컬 개발 설정은 아직 확정하지 않습니다. 세션 수명·동시 로그인·로그인 유지 선택·가입 후 자동 로그인·시도 제한은 [AUTH 미정 사항](../specs/authentication.md#open-questions)을 따릅니다. 구현 PR에서 FastAPI의 인증 의존성·응답과 자동 생성 OpenAPI의 쿠키 보안 설정·CSRF 계약을 함께 확인합니다. 방식 선택은 인증 구현 완료를 뜻하지 않습니다.

개인 프로필·지원·AI·알림 응답은 공유 캐시에 저장하지 않는 방향을 제안합니다. 비공개 전환 후 일반 조회가 이전 응답을 다시 사용하지 않도록 서버 재검증과 클라이언트 무효화 범위를 함께 구현합니다. 구체 캐시 기술은 이 문서로 선택하지 않습니다.

<a id="pagination"></a>

## 번호 페이지와 정렬

탐색·워크스페이스·알림의 번호 페이지 목록은 `Page<T>` 형태를 사용합니다. 이 숫자는 **권한을 적용한 해당 검색 결과**이며 서비스 전체 회원 수가 아닙니다.

| `Page<T>` 필드 | 타입 | 의미 |
| --- | --- | --- |
| `items` | `T[]` | 조회 항목. 결과 없으면 `[]` |
| `pagination` | `PageMeta` | 아래 페이지 정보 |

| `PageMeta` 필드 | 타입·범위 | 의미 |
| --- | --- | --- |
| `page` | integer, 1 이상 | 보정된 현재 페이지 |
| `pageSize` | integer, 1~100 | 적용된 페이지 크기 |
| `total` | integer, 0 이상 | 권한·필터에 맞는 전체 항목 수 |
| `totalPages` | integer, 0 이상 | `ceil(total / pageSize)`; 결과 없으면 0 |

### 공통 query

각 API의 조건 표에 있는 항목만 받습니다. 아래 항목은 모두 선택 입력이며 개별 조건 표가 사용할 항목을 지정합니다.

| 항목 | 타입·기본값 | 검증·처리 |
| --- | --- | --- |
| `page` | integer, 기본 1 | 1 이상·안전 정수 범위. 유효 범위 밖이면 422 |
| `pageSize` | integer, 기본 20 | 1~100. 유효 범위 밖이면 422 |
| `q` | string, 기본 검색 없음 | 앞뒤 공백 제거. 빈 문자열은 검색 없음. 검색 대상은 영역 문서 참조 |
| `fieldCode` | CatalogCode, 기본 필터 없음 | 저장된 전체 분야 중 해당 코드 포함 여부 |
| `roleCode` | CatalogCode, 기본 필터 없음 | 해당 목록의 모집/희망 역할 조건 |
| `recruitingOnly` | boolean, 기본 false | true이면 현재 공통 모집 가능 조건을 충족한 팀만 |
| `status` | ApplicationStatus, 기본 전체 | [지원 상태](contests-teams.md#values)의 한 값 |

`Page<T>`·`PageMeta`의 모든 필드는 필수이며 NULL을 허용하지 않습니다. 빈 결과 예시는 다음과 같습니다.

```json
{
  "items": [],
  "pagination": {
    "page": 1,
    "pageSize": 20,
    "total": 0,
    "totalPages": 0
  }
}
```

- `page`는 1부터, `pageSize`는 기본 20·최대 100으로 제안합니다. 이는 조회 비용을 제한하는 기술값이며 UI에서 반드시 20개를 보여야 한다는 제품 정책은 아닙니다.
- 조건에 맞는 결과가 없으면 `page=1`, `totalPages=0`입니다. 마지막 페이지를 넘으면 마지막 유효 페이지로 보정하고 응답의 `page`를 URL에 반영합니다. 0·음수·비정수는 422입니다.
- 정렬에는 항상 ID를 최종 동률 기준으로 추가합니다. 공모전은 등록순·마감순, 팀은 생성순, 지원은 제출순, 내 팀은 소속 시작순, 알림은 실제 발생순입니다. 방향은 각 영역 문서에 명시합니다.
- 하나의 응답에서 목록과 `total`은 같은 권한·필터·읽기 시점을 사용합니다. 서로 다른 페이지 요청 사이의 데이터 변경까지 고정된 스냅샷을 보장하지는 않습니다.
- 화면의 필터·페이지 유지 규칙은 [탐색 페이지 정책](../specs/sprint-1.md#exploration-pagination)에 연결합니다.

<a id="errors"></a>

## 실패를 읽는 방법

업무 오류는 HTTP 실패 코드와 안정적인 오류 코드를 함께 사용합니다. 문구를 비교해서 분기하지 않습니다.

| 객체 | 필드·타입 | 필수·의미 |
| --- | --- | --- |
| `Error` | `error: ErrorDetail`, `requestId: string` | 두 키 필수. `requestId`는 요청 추적용 문자열이며 생성 재전송용 UUID와 다름 |
| `ErrorDetail` | `code: string`, `message: string` | 두 키 필수. 아래 정의한 코드, 사람이 읽을 안내 |
| `ValidationError` | `detail: ValidationIssue[]` | 필수, 하나 이상의 검증 오류 |
| `ValidationIssue` | `loc: (string 또는 integer)[]`, `msg: string`, `type: string` | 세 키 필수. 위치 경로, 안내, 안정적인 검증 종류 |

모든 오류 필드는 NULL을 허용하지 않습니다. 인증이 필요한 API에는 401을 적용하고, 상태 변경 API에는 공통 CSRF 검사 실패의 403을 적용하며, 모든 API에 500·503이 가능합니다. 요청 필드·path·query가 있는 API의 형식 오류는 422이며 영역별 표에는 업무상 추가 오류를 함께 적습니다.

```json
{
  "error": {
    "code": "VERSION_CONFLICT",
    "message": "정보가 변경되었습니다. 최신 상태를 확인해 주세요."
  },
  "requestId": "request-correlation-example"
}
```

| HTTP | 의미 | 대표 코드 |
| --- | --- | --- |
| 401 | 인증 실패·만료 | `UNAUTHENTICATED`, 로그인만 `INVALID_CREDENTIALS` |
| 403 | 확인 가능한 리소스의 행동 권한 없음 또는 CSRF 검사 실패 | `FORBIDDEN` |
| 404 | 없음 또는 존재 자체를 노출하면 안 되는 개인 리소스 | `RESOURCE_NOT_FOUND` |
| 409 | 유일성·현재 상태·버전 충돌 | `LOGIN_ID_TAKEN`, `VERSION_CONFLICT`, `TEAM_FULL` 등 |
| 422 | 요청 필드·형식·검증 실패 | FastAPI 호환 `detail[]`의 `loc`, `msg`, `type` |
| 429 | 요청 제한 | `RATE_LIMITED`; 구체 제한 수치는 미정 |
| 503 | 일시적 서비스 장애 | `TEMPORARY_UNAVAILABLE` |
| 500 | 예상하지 못한 내부 오류 | `INTERNAL_ERROR`; 미정 기능을 임시 500으로 제공하지 않음 |

### 409 업무 코드

코드의 사용 API와 충돌 조건은 각 영역 문서에 연결합니다. 클라이언트는 같은 HTTP 409라도 코드를 구분합니다.

| 코드 | 의미·상세 원본 |
| --- | --- |
| `LOGIN_ID_TAKEN` | 정규화한 아이디 중복. [계정](accounts-profiles.md) |
| `VERSION_CONFLICT` | 현재 버전과 예상 버전 불일치 |
| `INVALID_CATALOG_SELECTION`, `INVALID_ACADEMIC_PATH` | 선택지·소속 경로의 현재 유효성 충돌. [프로필](accounts-profiles.md) |
| `PROFILE_REQUIRED`, `PROFILE_PRIVATE` | 신규 지원의 필수 프로필 또는 공개 조건 미충족. [지원](contests-teams.md) |
| `CONTEST_NOT_OPEN`, `RECRUITMENT_CLOSED`, `RECRUITMENT_DEADLINE_PASSED` | 공고·팀의 현재 접수 상태 또는 기한 충돌. [팀](contests-teams.md) |
| `CAPACITY_OUT_OF_RANGE`, `TEAM_FULL` | 공식 참가 인원 범위 위반 또는 빈자리 없음. [팀](contests-teams.md) |
| `DUPLICATE_APPLICATION`, `MEMBERSHIP_CONFLICT` | 유효 지원 중복 또는 확정 소속 충돌. [지원·선발](contests-teams.md) |
| `INVALID_APPLICATION_STATE`, `INVALID_RECRUITMENT_STATE` | 요청 행동을 할 수 없는 지원·모집 상태. [상태 처리](contests-teams.md) |
| `REQUEST_ID_REUSED` | 같은 생성 UUID를 다른 정규화 본문에 재사용 |
| `MESSAGE_ID_CONFLICT`, `REQUEST_ALREADY_RUNNING` | 같은 메시지 ID의 다른 본문 또는 진행 중 요청과 충돌. [AI](ai-notifications.md) |
| `REQUEST_NOT_RETRYABLE`, `ATTEMPT_CONFLICT` | 재시도 불가 상태 또는 현재 시도 불일치. [AI](ai-notifications.md) |

422의 `loc`는 `body`, `query`, 필드명·배열 위치를 담습니다. 비밀번호 등 입력 원문을 `input`이나 오류 메시지에 복제하지 않습니다. 다른 팀의 지원 여부를 오류 세부사항으로 추가하지 않습니다. 로그인 오류에서도 아이디 존재 여부를 구분하지 않습니다. 가입 전 아이디 중복 확인 API의 `available` 응답은 별도로 명시한 공개 계약입니다.

<a id="versioned-action"></a>

## 쓰기·충돌·재시도

`VersionedAction` 요청은 `{ "expectedVersion": "1" }` 형태입니다. `expectedVersion: Version` 하나가 필수이며 NULL·추가 필드는 허용하지 않습니다. 선발·취소는 지원 버전, 모집 종료·재개는 팀 버전을 전달합니다. 프로필 요청은 해당 영역의 전체 편집/공개 전환 객체에 같은 버전 필드를 둡니다.

| 요청 | 재시도와 충돌 계약 |
| --- | --- |
| 프로필 최초 저장 | `expectedVersion="0"`. 이미 생성됐다면 409. 자동 덮어쓰기 없음 |
| 프로필 수정·공개 전환 | 조회한 `version`을 `expectedVersion`으로 전달. 다른 변경이 먼저 저장됐다면 409 후 다시 조회 |
| 팀·지원 생성 | 사용자가 실행한 생성 시도마다 UUID `requestId`. 응답 유실 후 같은 시도는 동일 ID·동일 정규화된 본문으로 재전송. 첫 생성 201, 동일 시도 재전송 200, 같은 ID의 다른 본문은 409 `REQUEST_ID_REUSED` |
| 선발·지원 취소·모집 종료·재개 | 대상의 `expectedVersion`. 버전을 먼저 비교하여 다르면 409. 일치하는 버전에서 같은 결과 상태이면 200과 현재 값을 반환하고 추가 사건을 만들지 않음. 응답 유실 시 먼저 재조회하여 결과 확인 |
| AI 메시지 전송 | 현재 대화 내 `clientMessageId`로 사용자 메시지 중복 방지. 내용이 다르면 409 |
| AI 실패 재시도·중단 | `expectedAttempt`로 현재 시도를 지정. 이전 시도의 응답·취소가 새 시도에 적용되지 않음 |
| 알림 읽음 | 이미 읽은 항목의 최초 `readAt` 유지. 업무 상태·알림 사건을 새로 만들지 않음 |

`requestId`의 재사용과 `expectedVersion`은 다른 문제를 해결합니다. 전자는 **같은 생성 시도**, 후자는 **수정 대상의 최신 상태**를 확인합니다. 버전 비교는 DB 잠금·정원·현재 소속의 제약 검사를 대신하지 않습니다. 여러 행이 함께 바뀌는 작업은 [DB 트랜잭션 설계](../database/transactions.md)를 따릅니다.

<a id="deferred"></a>

## 아직 endpoint로 확정하지 않은 범위

| 결정이 필요한 부분 | 현재 API 설계의 경계 | 정책 원본 |
| --- | --- | --- |
| 세션 수명·동시 로그인·로그인 유지 선택·가입 후 자동 로그인 | 서버 세션·쿠키 전달은 확정. 미정 수치·옵션과 전체 기기 로그아웃·재발급 endpoint는 추가하지 않음 | [서버 세션 정책](../specs/authentication.md#session-policy), [AUTH 미정 사항](../specs/authentication.md#open-questions) |
| 쿠키 세부 설정·CSRF 전송 계약·운영 도메인 | 보호 원칙은 적용. 쿠키 이름·경로·보존 설정과 로그인 전 보호값 발급·헤더·검증 방식, CORS는 구현 전에 설계하며 현재 인증 계약을 완성된 SDK 입력으로 취급하지 않음 | [공통 세션 계약](#session-auth), [서버 세션 정책](../specs/authentication.md#session-policy) |
| 탈퇴·복구·이전 데이터 표시 | DELETE 계정·복구 endpoint를 만들지 않음 | [PROFILE-04](../specs/profile.md#open-questions) |
| 일반 텍스트 계수·URL 길이 | 정책 수치는 필드 표에 기록, 계수 방식·미확정 상한은 임의 추가하지 않음 | [PROFILE-07](../specs/profile.md#open-questions) |
| 소속 중 새 지원, 팀 생성 시 기존 대기 지원, 미선발·폐기 후 재지원 | 확정된 정상·취소 후 재지원 외 분기는 성공·거부를 임의 확정하지 않음 | [TEAM-04](../specs/team-recruitment.md#open-questions) |
| 모집 종료 후 선발·검토 시작·팀 전체 확정·미선발 처리 | 범용 상태 PATCH·미선발·팀장 선발취소 endpoint 없음. 선발 endpoint의 미정 분기는 명시적으로 후속 검토 | [TEAM-02·03](../specs/team-recruitment.md#open-questions) |
| 모집 정보 편집·제출 후 메시지 수정·팀 삭제 | 범용 수정·삭제 endpoint 없음 | [TEAM-07~09](../specs/team-recruitment.md#open-questions) |
| 마감 공고 목록 기본 배치·기본 필터 | 상세 열람은 정의. 목록의 미지정 상태 조건은 CONTEST-05 검토 필요 | [공고 미정 사항](../specs/contests.md#open-questions) |
| 관리자 공고 관리·공식 조건 변경 영향 | 관리 책임만 유지. 관리자 CRUD·일괄 소급 변경 API 없음 | [공고 운영](../specs/contests.md#operation-flow), [TEAM-06](../specs/team-recruitment.md#open-questions) |
| AI 서버 보존·제공자·실행·스트리밍 | 외부 요청·결과 모양만 제안. 현재 대화 조회를 과거 대화 복원 API로 확대하지 않음 | [MATCH-10·12·13·14](../specs/matching.md#open-questions) |

미정 분기는 운영에서 임시 500을 반환하도록 구현하라는 뜻이 아닙니다. 해당 유스케이스를 출시하기 전에 정책을 결정하고 성공·실패 계약을 완성해야 합니다.
