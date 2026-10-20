# API 공통 계약

이 문서는 **검토용 전송 설계**입니다. 제품 정책은 [기능 명세](../specs/README.md), 물리 저장 형식은 [DB 공통 기준](../database/conventions.md), 정확한 schema는 [OpenAPI 원본](README.md#openapi-source)을 따릅니다.

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
| 선택 항목 | 미입력은 `null`, 비어 있는 목록은 `[]`. 필드 생략 허용 여부는 schema에 명시 |
| 편집 저장 | 프로필 전체 저장은 `PUT`. 선택값 삭제는 명시적 `null` 또는 `[]`; 생략을 삭제로 추정하지 않음 |

일반 프로필·팀·메시지 텍스트의 길이 상한은 기능 명세를 참조합니다. Unicode 계수 단위가 미정인 항목에는 `x-policy-min-characters`·`x-policy-max-characters`로 정책 수치를 기록합니다. OpenAPI의 `minLength`·`maxLength`로 임의의 계수 방식을 확정하지 않습니다. 계수 단위를 정한 뒤 서버 검증과 schema를 함께 구체화합니다. 비밀번호는 이미 확정된 [NFC·Unicode 코드 포인트 기준](../specs/authentication.md#password-policy)을 적용합니다.

## 인증과 권한

API 설계에서 **누가 무엇을 할 수 있는지**와 **인증을 어떻게 전송하는지**를 구분합니다.

| `x-auth-policy` | 의미 |
| --- | --- |
| `public` | 공개 공고·팀·공통 목록 등 로그인 없이 허용된 조회 또는 가입·로그인 |
| `authenticated` | 현재 로그인 필요 |
| `self` | 인증 주체 자신의 리소스. 클라이언트가 보낸 사용자 ID를 소유자로 신뢰하지 않음 |
| `owner` / `recipient-leader` | 해당 팀장 또는 해당 지원을 받은 팀장 |
| `applicant` / `applicant-or-recipient-leader` | 지원 본인 또는 명시된 지원 관계 |
| `current-team-member` | 현재 팀장·확정 팀원 |
| `current-conversation-owner` / `request-owner-and-current-context` | 로그인 주체와 현재 AI 이용 맥락 및 대상 관계가 모두 일치 |

각 operation의 실제 허용 범위는 [접근 정책](../specs/authentication.md#access-policy)과 [프로필 공개 범위](../specs/profile.md#visibility)를 참조합니다. 일반 사람 상세, 지원 팀장의 지원자 상세, 팀 공간은 서로 다른 경로와 DTO로 분리합니다. 관리자의 공고 관리 권한이 비공개 프로필 조회 권한을 뜻하지 않습니다.

**인증 wire contract는 아직 미완성입니다.** 쿠키/Bearer 선택, CSRF 적용 방식, 세션 생성·만료·무효화, 응답 헤더 또는 토큰 구조, 로그인 제한 수치를 확정한 뒤 `securitySchemes`·`security`와 인증 응답에 추가해야 합니다. `x-auth-policy`는 검토용 확장 정보이며 실제 보안 설정이 아닙니다. `security` 생략을 모든 API의 공개 허용으로 읽으면 안 됩니다.

개인 프로필·지원·AI·알림 응답은 공유 캐시에 저장하지 않는 방향을 제안합니다. 비공개 전환 후 일반 조회가 이전 응답을 다시 사용하지 않도록 서버 재검증과 클라이언트 무효화 범위를 함께 구현합니다. 구체 캐시 기술은 이 문서로 선택하지 않습니다.

## 번호 페이지와 정렬

모든 탐색·워크스페이스 목록은 다음 형태를 사용합니다. 이 숫자는 **권한을 적용한 해당 검색 결과**이며 서비스 전체 회원 수가 아닙니다.

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
- 정렬에는 항상 ID를 최종 동률 기준으로 추가합니다. 공모전은 등록순·마감순, 팀은 생성순, 지원은 제출순, 내 팀은 소속 시작순, 알림은 실제 발생순입니다. 방향은 영역 문서와 OpenAPI에 명시합니다.
- 하나의 응답에서 목록과 `total`은 같은 권한·필터·읽기 시점을 사용합니다. 서로 다른 페이지 요청 사이의 데이터 변경까지 고정된 스냅샷을 보장하지는 않습니다.
- 화면의 필터·페이지 유지 규칙은 [탐색 페이지 정책](../specs/sprint-1.md#exploration-pagination)에 연결합니다.

## 실패를 읽는 방법

업무 오류는 HTTP 실패 코드와 안정적인 오류 코드를 함께 사용합니다. 문구를 비교해서 분기하지 않습니다.

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
| 403 | 확인 가능한 리소스의 행동 권한 없음 | `FORBIDDEN` |
| 404 | 없음 또는 존재 자체를 노출하면 안 되는 개인 리소스 | `RESOURCE_NOT_FOUND` |
| 409 | 유일성·현재 상태·버전 충돌 | `LOGIN_ID_TAKEN`, `VERSION_CONFLICT`, `TEAM_FULL` 등 |
| 422 | 요청 필드·형식·검증 실패 | FastAPI 호환 `detail[]`의 `loc`, `msg`, `type` |
| 429 | 요청 제한 | `RATE_LIMITED`; 구체 제한 수치는 미정 |
| 503 | 일시적 서비스 장애 | `TEMPORARY_UNAVAILABLE` |
| 500 | 예상하지 못한 내부 오류 | `INTERNAL_ERROR`; 미정 기능을 임시 500으로 제공하지 않음 |

422의 `loc`는 `body`, `query`, 필드명·배열 위치를 담습니다. 비밀번호 등 입력 원문을 `input`이나 오류 메시지에 복제하지 않습니다. 다른 팀의 지원 여부를 오류 세부사항으로 추가하지 않습니다. 로그인 오류에서도 아이디 존재 여부를 구분하지 않습니다. 가입 전 아이디 중복 확인 API의 `available` 응답은 별도로 명시한 공개 계약입니다.

## 쓰기·충돌·재시도

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
| 세션 전달·수명·가입 후 자동 로그인 | 계정 응답 데이터만 제안. 인증 응답 확정 전 구현·SDK 생성 보류 | [AUTH 미정 사항](../specs/authentication.md#open-questions) |
| 탈퇴·복구·이전 데이터 표시 | DELETE 계정·복구 endpoint를 만들지 않음 | [PROFILE-04](../specs/profile.md#open-questions) |
| 일반 텍스트 계수·URL 길이 | 정책 수치는 확장 속성, 미확정 상한을 새로 추가하지 않음 | [PROFILE-07](../specs/profile.md#open-questions) |
| 소속 중 새 지원, 팀 생성 시 기존 대기 지원, 미선발·폐기 후 재지원 | 확정된 정상·취소 후 재지원 외 분기는 성공·거부를 임의 확정하지 않음 | [TEAM-04](../specs/team-recruitment.md#open-questions) |
| 모집 종료 후 선발·검토 시작·팀 전체 확정·미선발 처리 | 범용 상태 PATCH·미선발·팀장 선발취소 endpoint 없음. 선발 endpoint의 미정 분기는 명시적으로 후속 검토 | [TEAM-02·03](../specs/team-recruitment.md#open-questions) |
| 모집 정보 편집·제출 후 메시지 수정·팀 삭제 | 범용 수정·삭제 endpoint 없음 | [TEAM-07~09](../specs/team-recruitment.md#open-questions) |
| 마감 공고 목록 기본 배치·기본 필터 | 상세 열람은 정의. 목록의 미지정 상태 조건은 CONTEST-05 검토 필요 | [공고 미정 사항](../specs/contests.md#open-questions) |
| 관리자 공고 관리·공식 조건 변경 영향 | 관리 책임만 유지. 관리자 CRUD·일괄 소급 변경 API 없음 | [공고 운영](../specs/contests.md#operation-flow), [TEAM-06](../specs/team-recruitment.md#open-questions) |
| AI 서버 보존·제공자·실행·스트리밍 | 외부 요청·결과 모양만 제안. 현재 대화 조회를 과거 대화 복원 API로 확대하지 않음 | [MATCH-10·12·13·14](../specs/matching.md#open-questions) |

미정 분기는 운영에서 임시 500을 반환하도록 구현하라는 뜻이 아닙니다. 해당 유스케이스를 출시하기 전에 정책을 결정하고 성공·실패 계약을 완성해야 합니다.
