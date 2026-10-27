# API 공통 계약

이 문서는 **검토용 전송 설계**입니다. 제품 정책은 [기능 명세](../specs/README.md), 물리 저장 형식은 [DB 공통 기준](../database/conventions.md), 개별 요청·응답 필드는 [영역별 API 문서](README.md)를 따릅니다. 공통 타입·성공 응답·페이지·오류는 여기서만 정의합니다.

**공통 기반 구현:** [DTO·응답 모델·전송 타입](../../backend/app/core/http/schemas.py), [애플리케이션 예외](../../backend/app/core/exceptions.py)와 [HTTP 핸들러](../../backend/app/core/http/handlers.py)를 제공합니다. 아래 계약의 제품 endpoint 적용 여부는 각 영역의 구현 상태를 따릅니다. 상세 사용법과 책임 경계는 [백엔드 공통 기반](../development/backend.md#api-core), 실제 HTTP·OpenAPI 대응은 [계약 테스트](../../backend/tests/integration/test_api_contract.py)에서 확인합니다. 공통 기반 구현이 인증·도메인 API 구현 완료를 뜻하지 않습니다.

<a id="types"></a>

## 주소와 값의 표현

| 항목 | 계약 |
| --- | --- |
| 경로 | `/api/v1` 아래 리소스 경로. 아래 영역 문서의 표는 이 접두사를 생략 |
| 본문 | `application/json`, camelCase. 선언하지 않은 필드·snake_case·혼용 요청은 422 |
| ID | 사용자·공고·팀·지원·알림 ID는 UUID 문자열. 학사 항목 ID는 증가형 BIGINT의 십진 문자열이며 로그인 아이디·표시명과 분리 |
| 코드 | 분야·역할·역량 등은 최대 64자의 카탈로그 코드. 표시명으로 저장 요청하지 않음 |
| BIGINT | `version`, `expectedVersion`, `capacity`, `minimumMembers`, `maximumMembers`, 학사 `id`·`parentId`·`academicUnitId`는 **십진 문자열**. 예: `"4"`. 최대 `9223372036854775807`은 저장 표현 한계이며 서비스 정원 상한이 아님 |
| 개수·페이지 | `page`, `pageSize`, `total`, `memberCount` 등은 JSON 정수. 안전 정수 범위를 벗어나는 집계가 필요해지면 계약 버전을 먼저 변경 |
| 시각 | UTC ISO 8601의 `Z` 표기. 원문 시간대·마감 보완 사실은 별도 필드로 제공 |
| 선택 항목 | 미입력은 `null`, 비어 있는 목록은 `[]`. 필드의 생략 가능 여부와 NULL 허용은 별개이며 영역별 표에 명시 |
| 편집 저장 | 프로필 전체 저장은 `PUT`. 선택값 삭제는 명시적 `null` 또는 `[]`; 생략을 삭제로 추정하지 않음 |

### 공통 타입과 표 읽기

아래 타입 이름은 문서에서 반복을 줄이는 표기이며 구현 클래스명을 강제하지 않습니다. 예를 들어 `Id`는 JSON에서 UUID **문자열**, `Success<Profile>`은 `data`에 프로필을 담은 객체, `Page<Profile>`은 `data`에 프로필 배열을 담은 페이지 객체입니다. 전송 구조는 아래 [성공 응답](#success-responses)과 [페이지](#pagination) 정의를 따릅니다.

| 타입 | JSON 표현·검증 |
| --- | --- |
| `Id` | UUID 문자열. 특정 UUID 생성 버전을 전제하지 않음 |
| `Timestamp` | 유효한 날짜·시각을 담은 UTC ISO 8601 문자열, 끝은 `Z` |
| `CatalogCode` | 길이 1~64인 코드 문자열. 공통 선택지 7종은 해당 애플리케이션 enum으로 검증. 학사 선택은 별도 코드 없이 `PositiveBigInt` ID로 참조 |
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

일반 프로필·팀·메시지 텍스트의 길이 상한은 영역별 표와 연결된 기능 명세를 참조합니다. 2026-10-24 사용자 결정으로 프로필·팀·지원 메시지는 NFC 정규화 후 Unicode 코드 포인트로 셉니다. 각 필드의 공백 제거 규칙을 함께 적용합니다. 비밀번호는 이미 확정된 [NFC·Unicode 코드 포인트 기준](../specs/authentication.md#password-policy)을 적용합니다. 입력을 잘라 저장하지 않습니다.

<a id="success-responses"></a>

## 성공 응답

제품 API의 본문이 있는 성공 응답은 **최상위 `data`에 실제 결과를 담습니다.** 단건·복합 객체와 배열을 같은 위치에서 읽고, 페이지 정보 등 부가 정보는 그 밖에 둡니다.

| 성공 타입 | JSON 구조 | 적용 |
| --- | --- | --- |
| `Success<T>` | `{ "data": T }` | 단건·복합 객체 또는 페이지 없는 배열. `T`는 영역별 응답 타입 |
| `Page<T>` | `{ "data": T[], "pagination": PageMeta }` | 번호 페이지 목록. 빈 결과는 `data: []` |
| `NotificationPage` | `Page<Notification>`의 전체 필드와 `unreadCount` | 알림 목록과 전체 미읽음 수 |
| 204 | 본문 없음 | 로그아웃. 빈 객체나 `data: null`을 반환하지 않음 |

`Success<T>.data`는 필수이며 현재 제품 API에서는 `null`을 허용하지 않습니다. 내부 선택 필드의 `null` 허용은 각 DTO 정의를 따릅니다. 영역 문서의 응답 필드 표는 `data`에 담기는 DTO를 정의하며, `Page<T>`·`NotificationPage` 표는 응답 전체를 정의합니다. 페이지 객체를 다시 `Success`로 감싸거나 중첩 DTO마다 `data`를 추가하지 않습니다. 요청 본문과 [오류 응답](#errors)은 이 규칙으로 감싸지 않습니다.

예를 들어 전체 미읽음 수 조회의 `Success<UnreadCount>`는 다음과 같습니다.

```json
{
  "data": {
    "unreadCount": 0
  }
}
```

HTTP 상태는 각 API의 200·201·202·204를 그대로 사용합니다. 가입·로그인의 `Set-Cookie`와 로그아웃의 쿠키 만료 등 경로별 헤더도 유지합니다. 성공 여부·HTTP 상태를 중복하는 `success`·`statusCode`나 공통 성공 문구는 추가하지 않습니다. 구현 시 Pydantic 응답 모델과 생성된 OpenAPI에도 이 구조를 명시하고 실제 응답과 대조합니다.

[AI 스트리밍](ai.md#streaming-proposal)은 200 `text/event-stream`으로, 응답 전체를 JSON `Success<T>`로 감싸지 않습니다. 스트림 시작 전 HTTP 오류와 시작 후 이벤트 오류를 구분합니다. 이전 AI `202 + Location + polling` 초안은 대체했으며 구현하지 않습니다.

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
| 가입·로그인 성공 | 암호학적으로 안전한 난수로 새 토큰을 생성하고, 서버에는 SHA-256 해시와 세션 상태를 저장. 저장 트랜잭션이 커밋된 뒤 `Set-Cookie`로 원문 토큰 전달. 가입 시 계정·자체 인증 정보·세션은 함께 커밋 |
| 쿠키 속성 | `HttpOnly`, `Secure`, `SameSite=Lax`. `Domain`을 지정하지 않는 host-only 지속 쿠키. 운영에서는 HTTPS 사용 |
| 인증이 필요한 요청 | 브라우저가 전송한 쿠키의 토큰을 해시하여 서버 세션 조회. 존재·회수 여부·유휴 만료·절대 만료를 공통 인증 의존성에서 검사하고 계정 식별 |
| 현재 세션 로그아웃 | 현재 서버 세션을 즉시 회수하고, 회수 커밋 뒤 같은 이름·범위의 쿠키를 만료시킴. 다른 세션의 상태·수명에는 영향 없음 |

`Max-Age`는 발급 시 서버의 절대 만료 시각 `expires_at`까지 남은 초를 내림하여 설정하며 신규 세션에서도 최대 `604800`초입니다. `Expires`를 함께 쓰면 같은 `expires_at`에 맞춥니다. 브라우저 재시작 후에도 남아 있는 쿠키로 같은 서버 세션을 검사하며, 재시작이나 일반 요청으로 새 7일의 유효기간을 부여하지 않습니다. 쿠키가 남아 있어도 유휴·절대 만료와 회수 검사를 모두 통과해야 합니다. 별도 로그인 유지 체크박스나 `rememberMe` 요청 필드를 두지 않고 모든 가입·로그인에 같은 정책을 적용합니다.

인증이 필요한 요청에 토큰이 없거나 세션이 존재하지 않거나 회수·만료되었으면 `401 UNAUTHENTICATED`입니다. 기간은 [서버 세션 정책](../specs/authentication.md#session-policy)을 적용하고, `현재 시각 >= last_seen_at + 유휴 만료 기간` 또는 `현재 시각 >= expires_at`이면 만료로 처리합니다. 유휴 만료는 마지막 유효 활동 시각을 갱신하기 **전에** 검사하며, 로그인 발급 시 정한 절대 만료 시각은 활동으로 연장하지 않습니다. 세션에서 얻은 계정 ID로 각 API의 현재 소속·지원·프로필 접근 관계를 다시 확인합니다. 세션에 저장된 과거 권한만으로 요청을 허용하지 않습니다.

동시 로그인을 허용하며 각 로그인 세션은 독립적으로 관리합니다. 새 로그인이나 다른 세션의 사용·로그아웃으로 기존 세션을 회수하거나 수명을 변경하지 않습니다. 기기 수 상한이나 기존 세션 자동 축출 규칙은 추가하지 않습니다. 로그인 실패·세션 만료의 화면 처리는 [간단한 안내와 재로그인 흐름](../specs/authentication.md#auth-failures)을 따르며, 아래 401·403·429의 구분은 유지합니다.

세션 토큰 원문·해시는 JSON 응답에 포함하지 않습니다. 프론트엔드는 세션 토큰을 JavaScript나 `localStorage`로 관리하지 않으며 브라우저의 쿠키 전달을 사용합니다. 현재 계약에 JWT·Bearer 인증이나 재발급 endpoint를 추가하지 않습니다.

로그인·로그아웃을 포함한 모든 상태 변경 요청에 CSRF 보호를 적용합니다. `HttpOnly`·`SameSite`만으로 보호가 완성되었다고 판단하지 않습니다. CSRF 검사 실패는 공통 `403 FORBIDDEN`이며 업무 상태를 변경하지 않습니다. 이 규칙은 각 endpoint 표에 반복하지 않고 공통으로 적용합니다.

<a id="csrf-transport"></a>

### 쿠키와 CSRF 전송

[인증 전송 설계 #98](https://github.com/wejo-team/sku-dreamon/issues/98)의 구현 계약입니다. 아래 전송 규칙은 인증 구현과 함께 HTTP·OpenAPI로 검증하며, 문서 반영만으로 구현 완료를 뜻하지 않습니다.

| 항목 | 계약 |
| --- | --- |
| 세션 쿠키 | `__Host-sku-dreamon-session`, `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax`; `Domain` 미지정. 32바이트 이상의 암호학적 난수로 토큰 생성 |
| CSRF 발급 | `GET /api/v1/auth/csrf`. 로그인 전에도 호출 가능. 같은 인증 상태의 유효한 기존 쿠키는 재사용하고 없거나 무효일 때만 발급. `Success<CsrfToken>`의 `data.csrfToken`과 쿠키 값은 같으며 `Cache-Control: no-store` 적용 |
| CSRF 쿠키 | `__Host-sku-dreamon-csrf`, `Path=/`, `Secure`, `HttpOnly`, `SameSite=Lax`; `Domain` 미지정. 브라우저 메모리에 보관할 토큰은 발급 응답에서 읽음 |
| 상태 변경 | `X-CSRF-Token` 헤더를 전달. 쿠키·헤더의 일치, 서버 HMAC 서명, 현재 세션에 대한 결합을 함께 확인. 가입·로그인·로그아웃에도 적용 |
| 출처 검사 | 설정된 HTTPS origin과 요청의 `Origin`을 정확히 비교. `Origin`이 없으면 `Referer`의 origin을 검사하고 둘 다 없거나 불일치하면 403 |
| 인증 전환 | 가입·로그인 성공 시 세션과 CSRF 값을 새로 발급. 기존 로그인 전 토큰이나 다른 세션의 토큰을 재사용하지 않음. 로그아웃 성공 시 두 쿠키 삭제 |
| 실패 | 토큰 누락·위조·불일치·출처 오류는 `403 FORBIDDEN`; 계정·세션 발급/회수와 업무 쓰기를 시작하지 않음. 오류·로그에 토큰 원문을 넣지 않음 |

CSRF 토큰은 임의 nonce에 HMAC-SHA-256을 적용하며 로그인 후에는 현재 세션 토큰의 해시와 결합합니다. 로그인 전에는 별도 무작위 nonce와 서버 서명으로 보호합니다. HMAC 키는 운영 설정으로 주입하고 저장소·프론트 번들에 포함하지 않습니다. 로그인 후 발급 토큰은 세션 자체가 유효할 때만 상태 변경에 사용할 수 있습니다. 응답에 세션 원문이나 그 해시를 포함하지 않습니다.

`/auth/csrf`는 만료·회수·미존재 세션의 쿠키가 남아 있어도 재로그인을 막지 않습니다. 해당 요청은 익명 상태로 처리하고 무효 세션 쿠키를 만료시킨 뒤 로그인 전 CSRF 토큰을 제공합니다. 이 과정에서 기존 세션을 되살리거나 새 로그인 세션을 만들지 않습니다.

프론트는 가입·로그인 전과 인증 전환 후 `/auth/csrf`에서 토큰을 읽고, 상태 변경 요청에 `credentials: "include"`와 `X-CSRF-Token`을 보냅니다. CSRF 토큰은 현재 화면의 메모리에만 보관하며 로그인 세션이 바뀌면 폐기합니다. 같은 세션의 다른 탭이 토큰을 조회해도 기존 쿠키를 교체하지 않습니다. 쿠키가 없는 최초 동시 발급이나 다른 탭의 로그인 전환으로 403이 발생하면 토큰을 다시 조회하고 사용자가 요청을 재시도할 수 있게 합니다. 업무 403과 구별하지 않고 상태 변경을 자동 재전송하지 않습니다. JSON 본문이 있는 요청의 `Content-Type`은 `application/json`입니다.

운영 도메인은 배포 설정으로 전달하고 허용 origin에 wildcard를 쓰지 않습니다. `SameSite=Lax`를 유지하므로 프론트와 API는 같은 HTTPS site에 배치합니다. 같은 site 안의 서로 다른 origin이면 명시한 origin·credentials·CSRF 헤더에 대해서만 CORS를 허용하고, 같은 origin의 reverse proxy도 사용할 수 있습니다. 서로 다른 site의 cross-site 배치는 이 계약의 지원 범위가 아닙니다. 로컬 브라우저 검증 역시 HTTPS를 사용하며 개발 편의를 위한 비보안 쿠키 전환은 제공하지 않습니다.

세션의 `last_seen_at`은 유효 조건을 만족하는 행에 대해서만 짧은 인증 트랜잭션에서 갱신·커밋합니다. 이후 업무 트랜잭션이 실패해도 유효한 활동 기록은 유지하며, 회수·유휴 만료·절대 만료된 세션을 갱신으로 되살리지 않습니다. 업무 권한은 해당 요청에서 현재 관계를 다시 검사합니다.

시도 제한 수치와 로컬 차단 목록 공급 방식은 [인증 운영 기준](../specs/authentication.md#auth-operation-settings)을 따릅니다. 실제 파일·설정 배포와 종료 세션의 정리·보존 기간은 후속 운영 범위입니다. 이 전송 계약으로 자동 삭제나 계정 잠금 정책을 추가하지 않습니다. 설계 근거는 [OWASP의 서명된 double-submit 및 origin 검사](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), [세션 관리](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)입니다.

로그인이 필요한 개인 프로필·사람 조회·지원·AI·알림 응답은 `Cache-Control: no-store`로 브라우저와 공유 HTTP 캐시에 저장하지 않도록 합니다. 공통 인증 의존성이 일반 성공 응답에 적용하고, 명시적으로 반환하는 `Response`·AI 스트림은 반환 응답에 직접 설정합니다. 공통 오류 처리에도 적용해 인증 실패·권한 거부·비공개 또는 없는 자원의 404·입력 검증 실패 응답을 재사용하지 않도록 합니다. 공개 공고와 정적 파일의 정상 응답은 이 규칙의 적용 대상이 아닙니다. 비공개 전환 후 서버의 현재 권한 재검사와 프론트의 화면 데이터 무효화는 계속 필요하며, `no-store`가 이미 화면에 보관된 데이터를 제거하는 것은 아닙니다.

<a id="pagination"></a>

## 번호 페이지와 정렬

탐색·워크스페이스·알림의 번호 페이지 목록은 `Page<T>` 형태를 사용합니다. `data`에 결과 배열, 같은 객체의 `pagination`에 페이지 정보를 담습니다. 이 숫자는 **권한을 적용한 해당 검색 결과**이며 서비스 전체 회원 수가 아닙니다.

| `Page<T>` 필드 | 타입 | 의미 |
| --- | --- | --- |
| `data` | `T[]` | 조회 항목. 결과 없으면 `[]` |
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
| `status` | ApplicationStatus, 기본 전체 | [지원 상태](applications.md#values)의 한 값 |

`Page<T>`·`PageMeta`의 모든 필드는 필수이며 NULL을 허용하지 않습니다. 빈 결과 예시는 다음과 같습니다.

```json
{
  "data": [],
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
| 429 | 요청 제한 | `RATE_LIMITED`; 인증 수치는 [운영 기준](../specs/authentication.md#auth-operation-settings) 적용 |
| 503 | 일시적 서비스 장애 | `TEMPORARY_UNAVAILABLE` |
| 500 | 예상하지 못한 내부 오류 | `INTERNAL_ERROR`; 미정 기능을 임시 500으로 제공하지 않음 |

### 409 업무 코드

코드의 사용 API와 충돌 조건은 각 영역 문서에 연결합니다. 클라이언트는 같은 HTTP 409라도 코드를 구분합니다.

| 코드 | 의미·상세 원본 |
| --- | --- |
| `LOGIN_ID_TAKEN` | 정규화한 아이디 중복. [계정](auth.md) |
| `VERSION_CONFLICT` | 현재 버전과 예상 버전 불일치 |
| `INVALID_CATALOG_SELECTION`, `INVALID_ACADEMIC_PATH` | 선택지·소속 경로의 현재 유효성 충돌. [프로필](profiles.md) |
| `PROFILE_REQUIRED`, `PROFILE_PRIVATE` | 신규 지원의 필수 프로필 또는 공개 조건 미충족. [지원](applications.md) |
| `CONTEST_NOT_OPEN`, `RECRUITMENT_CLOSED`, `RECRUITMENT_DEADLINE_PASSED` | 공고·팀의 현재 접수 상태 또는 기한 충돌. [팀](teams.md) |
| `CAPACITY_OUT_OF_RANGE`, `TEAM_FULL` | 공식 참가 인원 범위 위반 또는 빈자리 없음. [팀](teams.md) |
| `DUPLICATE_APPLICATION`, `MEMBERSHIP_CONFLICT` | 유효 지원 중복 또는 확정 소속 충돌. [지원·선발](applications.md) |
| `REAPPLICATION_NOT_ALLOWED` | 미선발 이력이 있는 같은 팀에 새로 지원함. [재지원](applications.md#transitions) |
| `INVALID_APPLICATION_STATE`, `INVALID_RECRUITMENT_STATE` | 요청 행동을 할 수 없는 지원·모집 상태. [지원](applications.md#transitions)·[모집](teams.md#transitions) |
| `REQUEST_ID_REUSED` | 같은 생성 UUID를 다른 정규화 본문에 재사용 |
| `MESSAGE_ID_CONFLICT`, `REQUEST_ALREADY_RUNNING` | 같은 메시지 ID의 다른 본문 또는 진행 중 요청과 충돌. [AI](ai.md) |
| `REQUEST_NOT_RETRYABLE`, `ATTEMPT_CONFLICT` | 재시도 불가 상태 또는 현재 시도 불일치. [AI](ai.md) |

422의 `loc`는 `body`, `query`, 필드명·배열 위치를 담습니다. 비밀번호 등 입력 원문을 `input`이나 오류 메시지에 복제하지 않습니다. 다른 팀의 지원 여부를 오류 세부사항으로 추가하지 않습니다. 로그인 오류에서도 아이디 존재 여부를 구분하지 않습니다. 가입 전 아이디 중복 확인 API의 `available` 응답은 별도로 명시한 공개 계약입니다.

<a id="versioned-action"></a>

## 쓰기·충돌·재시도

`VersionedAction` 요청은 `{ "expectedVersion": "1" }` 형태입니다. `expectedVersion: Version` 하나가 필수이며 NULL·추가 필드는 허용하지 않습니다. 검토 시작·미선발·선발·취소는 지원 버전, 모집 종료·재개는 팀 버전을 전달합니다. 프로필 요청은 해당 영역의 전체 편집/공개 전환 객체에 같은 버전 필드를 둡니다.

| 요청 | 재시도와 충돌 계약 |
| --- | --- |
| 프로필 최초 저장 | `expectedVersion="0"`. 이미 생성됐다면 409. 자동 덮어쓰기 없음 |
| 프로필 수정·공개 전환 | 조회한 `version`을 `expectedVersion`으로 전달. 다른 변경이 먼저 저장됐다면 409 후 다시 조회 |
| 팀·지원 생성 | 사용자가 실행한 생성 시도마다 UUID `requestId`. 응답 유실 후 같은 시도는 동일 ID·동일 정규화된 본문으로 재전송. 첫 생성 201, 동일 시도 재전송 200, 같은 ID의 다른 본문은 409 `REQUEST_ID_REUSED` |
| 검토 시작·미선발·선발·지원 취소·모집 종료·재개 | 대상의 `expectedVersion`. 버전을 먼저 비교하여 다르면 409. 일치하는 버전에서 해당 행동의 no-op 조건을 충족하면 200과 현재 값을 반환하고 버전·사건·알림을 추가하지 않음. 정확한 전이·조건은 [지원 행동](applications.md#transitions)과 [모집 행동](teams.md#transitions)을 따르며 응답 유실 시 먼저 재조회하여 결과 확인 |
| AI 메시지 전송 | 현재 대화 내 `clientMessageId`로 사용자 메시지 중복 방지. 내용이 다르면 409 |
| AI 실패 재시도·중단 | `expectedAttempt`로 현재 시도를 지정. 이전 시도의 응답·취소가 새 시도에 적용되지 않음 |
| 알림 읽음 | 이미 읽은 항목의 최초 `readAt` 유지. 업무 상태·알림 사건을 새로 만들지 않음 |

`requestId`의 재사용과 `expectedVersion`은 다른 문제를 해결합니다. 전자는 **같은 생성 시도**, 후자는 **수정 대상의 최신 상태**를 확인합니다. 버전 비교는 DB 잠금·정원·현재 소속의 제약 검사를 대신하지 않습니다. 여러 행이 함께 바뀌는 작업은 [DB 트랜잭션 설계](../database/transactions.md)를 따릅니다.

<a id="deferred"></a>

## 아직 endpoint로 확정하지 않은 범위

| 결정이 필요한 부분 | 현재 API 설계의 경계 | 정책 원본 |
| --- | --- | --- |
| 인증 운영 설정 | 쿠키·CSRF 전송 계약은 정의. 운영 origin·키와 제한 수치·차단 목록·보존은 실제 운영 전에 준비하며 인증 구현 완료와 구분 | [CSRF 전송](#csrf-transport), [AUTH 미정 사항](../specs/authentication.md#open-questions) |
| 탈퇴·이전 데이터 표시 | DELETE 계정 endpoint를 만들지 않음 | [PROFILE-04](../specs/profile.md#open-questions) |
| 계정 복구 — MVP 범위 밖 | 복구 endpoint를 만들지 않으며 현재 인증 구현의 선행 조건으로 두지 않음. 복구 도입 시 정책·계약 후속 검토 | [계정 복구 범위](../specs/authentication.md#account-recovery) |
| 일반 텍스트·URL의 추가 제한 | 프로필·팀·지원 메시지의 NFC·코드 포인트 기준은 확정. URL의 운영 길이 상한 등 명시하지 않은 추가 제한은 보류 | [프로필 입력](../specs/profile.md#input-validation) |
| 팀장 선발 취소·강퇴·팀장 탈퇴·팀 삭제 — MVP 범위 밖 | 관리 endpoint나 범용 상태 PATCH로 제공하지 않음. 본인의 선발 후 지원 취소는 확정 계약 유지 | [소속 관리 제외 범위](../specs/team-recruitment.md#membership-exclusions) |
| 모집 정보 편집·제출 후 메시지 수정 | 범용 수정 endpoint 없음 | [TEAM-07~09](../specs/team-recruitment.md#open-questions) |
| 마감 공고 목록 기본 배치·기본 필터 | 상세 열람은 정의. 상태 생략 시 전체·최신 등록순으로 확정. 삭제·보존은 후속 범위 | [공고 미정 사항](../specs/contests.md#open-questions) |
| 관리자 공고 관리·공식 조건 변경 영향 | 관리 책임만 유지. 관리자 CRUD·일괄 소급 변경 API 없음 | [공고 운영](../specs/contests.md#operation-flow), [TEAM-06](../specs/team-recruitment.md#open-questions) |
| AI 프론트·운영·추가 개인화 | 서버 스트림·실행 메타데이터·현재 권한 재검증 구현. UI·운영 설정·품질 평가는 별도 | [SDD 후속 작업](../development-plans/ai-agent.md#open-decisions) |

미정 분기는 운영에서 임시 500을 반환하도록 구현하라는 뜻이 아닙니다. 해당 유스케이스를 출시하기 전에 정책을 결정하고 성공·실패 계약을 완성해야 합니다.
