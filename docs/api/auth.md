# 계정·인증 API

**상태: 구현 중.** CSRF·본인 계정 조회와 현재 세션 로그아웃의 [라우터](../../backend/app/routers/auth.py)·[응답 DTO](../../backend/app/schemas/auth.py)·[HTTPS 통합 테스트](../../backend/tests/integration/test_auth_http.py)를 구현했습니다. 가입·로그인·아이디 중복 확인은 후속 범위입니다. 경로에는 `/api/v1` 접두사가 붙습니다. JSON 표기와 타입은 [공통 타입](conventions.md#types), 실패 응답은 [오류 계약](conventions.md#errors)을 따릅니다.

| 확인할 내용 | 위치 |
| --- | --- |
| 가입·로그인·본인 계정 | [API 목록](#account-endpoints) |
| 요청·응답 필드 | [Credentials](#credentials), [Account](#account), [가입·로그인 결과](#auth-results) |
| 세션 전달·만료·CSRF | [공통 서버 세션 계약](conventions.md#session-auth) |

모든 객체는 아래에 정의된 필드만 사용합니다. **본문의 필드는 별도 표시가 없으면 모두 필수**이며, `null` 허용과 필드 생략 허용은 다릅니다. 읽기 전용 필드·선언하지 않은 필드·snake_case를 쓰기 본문으로 보내면 422입니다. 아래 오류 표 외에 모든 API는 공통 `500 INTERNAL_ERROR`, `503 TEMPORARY_UNAVAILABLE`를 사용하며, 상태 변경 요청에는 [공통 CSRF 보호와 실패 응답](conventions.md#session-auth)이 적용됩니다.

성공 응답의 본문은 [공통 성공 응답](conventions.md#success-responses)을 따르며, 아래 응답 DTO 표는 `data` 안의 값과 하위 객체를 정의합니다.

<a id="account-endpoints"></a>

## 계정과 로그인

| 메서드·경로 | 접근 | 요청 | 성공 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /auth/csrf` | 공개 | 본문 없음 | 200 `Success<CsrfToken>`, CSRF 쿠키 | 공통 500·503 |
| `POST /accounts` | 공개 | 본문 [Credentials](#credentials) | 201 [Success&lt;SignupResult&gt;](#auth-results) | 409 `LOGIN_ID_TAKEN`; 422; 429 `RATE_LIMITED` |
| `GET /auth/login-id-availability` | 공개 | 필수 query `loginId: string` | 200 [Success&lt;LoginIdAvailability&gt;](#auth-results) | 422; 429 `RATE_LIMITED` |
| `POST /auth/login` | 공개 | 본문 [Credentials](#credentials) | 200 [Success&lt;LoginResult&gt;](#auth-results) | 401 `INVALID_CREDENTIALS`; 422; 429 `RATE_LIMITED` |
| `POST /auth/logout` | 로그인 | 본문 없음, CSRF 헤더 | 204, 본문 없음 | 401 `UNAUTHENTICATED`; 403 `FORBIDDEN` |
| `GET /me` | 로그인한 본인 | 본문 없음 | 200 [Success&lt;Account&gt;](#account) | 401 `UNAUTHENTICATED` |

가입은 자체 로그인 정보를 포함한 `accounts`와 새 `auth_sessions`를 같은 트랜잭션에서 생성하며, 저장 시 아이디 유일성을 확인합니다. 모두 커밋된 뒤 201 `Success<SignupResult>`와 `Set-Cookie`를 반환하여 바로 로그인시킵니다. 세션 저장이 실패하면 가입 전체를 롤백하며 성공 응답·인증 쿠키를 발급하지 않습니다. 클라이언트는 가입 성공 후 `GET /me` 응답의 `data.id`가 가입 응답의 `data.account.id`와 일치하는지 확인하고 프로필 설정으로 이동합니다. 다른 계정의 기존 쿠키가 남아 있다면 자동 로그인 성공으로 취급하지 않고 가입한 계정의 로그인을 안내합니다. 중복 확인 응답은 가입 예약이 아닙니다. 탈퇴 아이디 재사용은 [탈퇴 정책](../specs/profile.md#account-withdrawal)이 확정되기 전에 가입 가능으로 안내하지 않습니다.

가입 응답이 유실되어도 서버의 커밋은 완료되었을 수 있습니다. 클라이언트는 계정을 삭제하거나 자동으로 다시 가입하지 않고 로그인 상태를 확인합니다. 이때 응답 계정 ID를 알 수 없다면 `GET /me` 응답의 `data.loginId`가 가입 요청의 정규화된 아이디와 일치하는지 확인하고, 미인증·불일치이면 입력한 계정으로 로그인하도록 안내합니다. 일시적인 조회 실패는 가입 실패나 만료로 단정하지 않고 다시 확인할 수 있게 합니다. 이는 MVP에서 제외한 분실 계정 복구 기능을 추가하는 것이 아닙니다.

로그인 실패는 아이디 존재 여부와 비밀번호 오류를 구분하지 않는 `INVALID_CREDENTIALS` 응답을 제안합니다. 화면은 [실패·만료 안내 정책](../specs/authentication.md#auth-failures)에 따라 간단히 안내하고 다시 로그인을 시도할 수 있게 합니다. 로그인 성공 시 새 서버 세션의 저장이 커밋된 뒤 `Set-Cookie`로 토큰을 전달하고, JSON 본문의 `data`에는 아래 `LoginResult`의 계정 데이터만 반환합니다. 세션 저장에 실패하면 로그인 성공 응답이나 새 인증 쿠키를 발급하지 않습니다.

[인증 서비스](../../backend/app/services/auth.py)는 [인증 Repository](../../backend/app/repositories/auth.py)의 계정·프로필 존재 조회 결과를 응답 DTO로 구성합니다. 세션 유효성 판단·활동 시각 변경·회수는 [세션 서비스](../../backend/app/services/sessions.py)가 맡으며 Repository는 조회·행 잠금·flush만 수행합니다. 인증 활동의 독립 트랜잭션과 업무 트랜잭션을 합치지 않습니다.

`GET /me`와 다른 인증 필요 요청은 [공통 서버 세션 검사](conventions.md#session-auth)로 계정을 식별합니다. 만료된 세션은 401을 반환하고 화면에서 재로그인을 안내합니다. 로그아웃은 현재 서버 세션을 즉시 회수하고, 회수를 커밋한 뒤 쿠키를 만료시켜 204를 반환합니다. 동시 로그인을 허용하며 다른 로그인 세션의 상태·수명은 변경하지 않습니다. 성공 후 클라이언트는 계정별 AI 화면·초안을 지우고 진행 중 응답을 취소합니다.

로그아웃은 인증을 먼저 확인한 뒤 CSRF·출처를 검사합니다. 인증 또는 CSRF 검증 실패에는 세션 회수·쿠키 변경이 없습니다. 회수 시에도 잠금 후 현재 세션의 유효성을 다시 검사하며, 커밋이 실패하면 롤백하고 쿠키를 유지합니다. 성공 응답은 `Cache-Control: no-store`와 세션·CSRF 쿠키 두 개의 삭제만 반환합니다. 이후 `GET /auth/csrf`에서 익명 토큰을 받을 수 있습니다.

**인증 방식·세션 수명·동시 로그인·브라우저 재시작 후 유지·가입 직후 자동 로그인은 [서버 세션 정책](../specs/authentication.md#session-policy)을 따릅니다.** 별도 로그인 유지 선택 없이 같은 지속 쿠키를 사용하며, 브라우저 재시작으로 세션 만료 시각을 연장하지 않습니다. 로그인·로그아웃·가입에도 [쿠키·CSRF 전송 계약](conventions.md#session-auth)을 적용합니다. `CsrfToken`은 필수·NULL 불가 문자열 `csrfToken` 하나를 갖습니다. 로그인 세션 토큰과 다른 값이며 인증 수단으로 사용할 수 없습니다. 차단 목록·시도 제한·보존 등 운영 결정은 [AUTH 미정 사항](../specs/authentication.md#open-questions)을 따릅니다.

CSRF 조회는 같은 인증 상태의 유효한 쿠키를 재사용하고 `Cache-Control: no-store`를 반환합니다. 만료·회수·미존재·잘못된 형식의 세션 쿠키가 있으면 해당 쿠키를 만료시키고 익명 CSRF를 제공합니다. 새 로그인 세션을 생성하거나 만료 시각을 연장하지 않습니다. CSRF 쿠키는 `Secure`, `HttpOnly`, `SameSite=Lax`, `Path=/`이며 `Domain`을 지정하지 않습니다. 응답 필드와 쿠키의 토큰 값은 같고, 다른 세션에 결합된 토큰은 재사용하지 않습니다.

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

`Account`는 본인에게만 반환하며 `Cache-Control: no-store`를 적용합니다. 계정과 저장된 프로필의 존재 여부를 같은 SELECT에서 읽습니다. 다른 사람의 프로필·팀원·AI 응답에 로그인 아이디나 인증 정보를 섞지 않습니다. 학교 이메일·연락처·권한 부여 이력·비밀번호 해시·세션 값은 이 객체에 포함하지 않습니다. 실제 필드 정의는 [AccountResponse](../../backend/app/schemas/auth.py)와 라우터에서 생성한 OpenAPI를 따릅니다.

[계정 DB 설계](../database/identity.md#accounts)의 학교 이메일·인증 완료 시각은 후속 인증 기능을 위한 저장 필드입니다. 현재 입력·응답 필드나 인증 API를 추가하지 않으며, `schoolVerification`은 계속 `unverified`만 반환합니다.

<a id="auth-results"></a>

### 가입·로그인·중복 확인 응답

| 객체 | 전체 필드 | 의미 |
| --- | --- | --- |
| `SignupResult` | `account: Account` | 계정·인증 정보·세션 생성 성공. 별도 `Set-Cookie`로 자동 로그인하며 클라이언트는 로그인 상태 확인 후 프로필 설정으로 이동 |
| `LoginResult` | `account: Account` | 본인 계정 데이터. 세션 토큰은 본문에 포함하지 않고 별도 `Set-Cookie`로 전달 |
| `LoginIdAvailability` | `normalizedLoginId: string`, `available: boolean` | 정규화한 아이디와 현재 중복 여부. 아이디 형식은 `^[a-z0-9]{4,24}$` |

모든 필드는 필수이며 `null`을 허용하지 않습니다. 가입·로그인 제한 수치와 기간은 미정이며 429 계약만 제안합니다.

## DB 연결과 남은 범위

| API 정보 | 저장·정의 원본 |
| --- | --- |
| `Account`·로그인·`isDemo` | [계정과 프로필 테이블](../database/identity.md), [시연 데이터 식별](../specs/sprint-1.md#demo-data-scope) |

계정 탈퇴·학교 인증 API는 이번 설계에 추가하지 않습니다. [계정 복구](../specs/authentication.md#account-recovery)는 MVP 범위에서 제외하므로 복구 API를 만들지 않으며 현재 인증 구현의 선행 조건으로 두지 않습니다. 가입 후 프로필 설정·사람 탐색은 [프로필 API](profiles.md)를 따릅니다.
