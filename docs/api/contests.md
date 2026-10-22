# 공모전 API

**상태: 설계 제안 · 미구현.** 공모전 목록·상세 탐색의 전송 계약을 정의합니다. 경로는 `/api/v1` 기준이며, 제품 정책은 연결한 기능 명세를 따릅니다.

- 먼저 [API 목록](#endpoints)에서 경로·권한·성공 응답을 찾습니다.

- 입력은 [검색 조건](#queries), 출력은 [공모전 데이터](#contest-summary) 표에서 확인합니다.

- ID·코드·시각·정원·버전은 [공통 타입](conventions.md#types), 페이지는 [Page&lt;T&gt;](conventions.md#pagination), 실패는 [공통 오류](conventions.md#errors)를 사용합니다. `Page<T>`는 `items: T[]`와 `pagination`을 가진 공통 응답입니다.

**표 읽기:** 응답 표의 모든 필드는 필수입니다. `null` 허용 여부는 타입에 따로 표시하며, `null`인 필드를 생략하지 않습니다. 요청은 각 표에 필수 여부를 표시합니다. 선언하지 않은 요청 필드는 422입니다. 일반 텍스트의 정책상 글자 수와 Unicode 계수 단위의 미정 사항은 [공통 계약](conventions.md)을 따릅니다.

<a id="endpoints"></a>

## API 목록

아래 모든 작업에 입력 형식 오류 **422**, 일시 장애 **503**, 내부 오류 **500**이 공통 적용됩니다. 로그인 또는 관계 권한이 필요한 작업에는 **401**, 상태 변경 요청에는 [공통 CSRF 검사 실패의 403](conventions.md#session-auth)도 적용됩니다. 표의 실패 열은 그 밖의 응답을 나타냅니다. 실패 본문 형식은 [공통 오류 계약](conventions.md)에 있습니다.

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /contests` | 공개, 공모전 검색 조건 | 200 `Page<ContestSummary>` | — |
| `GET /contests/{contestId}` | 공개, 공고 UUID | 200 `Contest` | 404 공고 없음 |

공고는 접수 예정·중·마감 상태 모두 상세 열람할 수 있습니다. 화면별 정보 구분은 [공고 탐색](../specs/contests.md#exploration-ui)을 따릅니다. 공고에 연결된 팀 목록 `GET /contests/{contestId}/teams`는 [팀 API](teams.md#endpoints)에 정의합니다.

<a id="queries"></a>

## 검색 조건과 정렬

경로 변수 `contestId`는 해당 경로에서 필수 `Id`입니다. 목록의 아래 query는 모두 선택 입력입니다.

| query | 타입·기본값 | 적용 범위·의미 |
| --- | --- | --- |
| `page`, `pageSize` | 정수, 기본 1·20, 페이지 크기 최대 100 | 모든 페이지 목록. 범위·마지막 페이지 보정은 [공통 계약](conventions.md) |
| `q` | 문자열, 생략 또는 trim 후 빈 값은 검색 없음 | 공모전 탐색. 검색 대상은 아래 표 |
| `fieldCode` | `CatalogCode`, 생략 시 제한 없음 | 공모전 목록. 저장된 전체 분야 중 하나라도 해당 코드를 포함 |
| `sort` | `created_desc` 또는 `deadline_asc`, 기본 `created_desc` | 공모전 목록 |
| `registrationStatus` | `RegistrationStatus` | 공모전 목록. 지정한 접수 상태만 조회 |

| 목록 | 검색 대상 | 안정 정렬 |
| --- | --- | --- |
| 공모전 | 제목·주최자·분야 표시명 | 등록순 `createdAt DESC, id DESC`; 마감순 `endsAt ASC, id ASC` |

`Contest.teamCount`는 연결된 **전체 팀 수**이고 페이지의 `pagination.total`은 현재 권한·필터에 맞는 결과 수입니다.

`registrationStatus` 생략 시 마감 공고의 기본 포함·배치는 [CONTEST-05](../specs/contests.md#open-questions) 결정이 필요합니다. 등록순 기본 정렬만으로 이 제품 정책을 확정하지 않습니다.

<a id="values"></a>

## 공모전 상태값

| 타입 | 값과 의미 |
| --- | --- |
| `RegistrationStatus` | `scheduled` 접수 예정, `open` 접수 중, `closed` 접수 마감 |
| `AudienceCode` | `student` 대학생, `general` 일반인, `unrestricted` 제한 없음, `unknown` 미확인 |

<a id="contest-summary"></a>

## 공모전 응답

### ContestSummary — 목록 카드

| 필드 | 타입 | 의미·제약 |
| --- | --- | --- |
| `id` | `Id` | 공고 식별자 |
| `title` | string | 공고 제목 |
| `organizer` | string | 주최자 |
| `fieldCodes` | `CatalogCode[]` | 중복 없이 0~3개 |
| `posterUrl` | `HttpUrl` 또는 null | 포스터가 없으면 null |
| `registrationStatus` | `RegistrationStatus` | 현재 접수 상태 |
| `startsAt` | `Timestamp` | 접수 시작, 포함 경계 |
| `endsAt` | `Timestamp` | 접수 마감, 제외 경계 |
| `teamCount` | integer | 상태에 관계없는 연결 팀 전체 수, 0~9,007,199,254,740,991 |
| `isDemo` | boolean | 공고용 고정 UUID 시드 목록에 `id`가 포함되는지 서버에서 판정 |
| `createdAt` | `Timestamp` | 등록 시각 |
| `version` | `Version` | 공고의 현재 버전 |

D-day는 `endsAt`과 표시 시간대를 기준으로 표현합니다. 저장된 접수 상태 문자열이나 별도 팀 수를 클라이언트가 추정하지 않습니다.

<a id="contest"></a>

### Contest — 상세

`ContestSummary`의 **모든 필드**에 아래 필드를 추가합니다. 목록과 상세에 같은 이름으로 제공하는 값은 같은 의미·타입입니다.

| 추가 필드 | 타입 | 의미·제약 |
| --- | --- | --- |
| `description` | string 또는 null | 상세 설명 |
| `audienceCodes` | `AudienceCode[]` | 중복 없이 1~2개. `student`+`general`은 함께 가능, `unrestricted`·`unknown`은 단독 |
| `eligibilityText` | string | 원문의 참가 조건 |
| `capacity` | `ParticipationCapacity` | 원문 참가 인원 조건 |
| `timing` | `ContestTiming` | 원문 일정과 서비스 보완 사실 |
| `deliverables` | string 또는 null | 제출물 안내 |
| `awards` | string 또는 null | 시상 안내 |
| `contact` | string 또는 null | 문의처 |
| `verifiedAt` | `Timestamp` | 등록 전 자료 확인 시각 |
| `sourceUrl` | `HttpUrl` | 공식 원문 링크 |

<a id="participation-capacity"></a>

### ParticipationCapacity — 참가 인원 조건

각 형태에서 `kind`, `minimumMembers`, `maximumMembers`는 모두 필수입니다. 수치는 `PositiveBigInt` 십진 문자열이고, 정보가 없으면 null입니다.

| `kind` | `minimumMembers` | `maximumMembers` | 조합 규칙 |
| --- | --- | --- | --- |
| `range` | 양의 십진 문자열 | 양의 십진 문자열 | 최소 ≤ 최대. 두 값이 같으면 고정 정원 |
| `unlimited` | 양의 십진 문자열 또는 null | null | 최대 제한 없음. 확인된 최소가 없으면 최소도 null |
| `unknown` | null | null | 미확인 정보 표현용 |

`unknown`은 미확인 필수 인원 자료의 신규 등록·팀 생성을 허용하는 계약이 아닙니다. `unlimited` 공고라도 팀장은 양의 목표 정원을 직접 입력합니다.

<a id="contest-timing"></a>

### ContestTiming — 접수 일정

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `startsAt`, `endsAt` | `Timestamp` | 상위 `Contest`의 동일 이름 필드와 같은 시작·마감 경계 |
| `openSourceDate` | string (`YYYY-MM-DD`) | 원문 접수 시작 날짜 |
| `openSourceTime` | string 또는 null | 원문 시작 시각 |
| `openSourceTimeZone` | string 또는 null | 원문 시작 시간대 |
| `openEffectiveTimeZone` | string | 계산에 적용한 시간대 |
| `openTimeZoneDefaulted` | boolean | 시작 시간대를 서비스 기준으로 보완했는지 여부 |
| `closing` | `DeadlineInterpretation` | 마감 원문과 보완 여부 |

원문에 시작 시각이 없거나 모호한 경우의 처리까지 이 계약으로 확정하지 않습니다. 등록 전 확인과 미정 범위는 [공고 테이블](../database/contests.md)을 따릅니다.

<a id="deadline-interpretation"></a>

### DeadlineInterpretation — 마감 안내 정보

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `sourceDate` | string (`YYYY-MM-DD`) | 원문 또는 사용자가 입력한 날짜 |
| `sourceTime` | string 또는 null | 원문 시각, 없으면 null |
| `sourceTimeZone` | string 또는 null | 원문 시간대, 없으면 null |
| `effectiveTimeZone` | string | 계산에 적용한 시간대 |
| `timeDefaulted` | boolean | 시각을 날짜 끝까지로 보완했는지 여부 |
| `timeZoneDefaulted` | boolean | 시간대를 한국시간으로 보완했는지 여부 |

실제 마감 경계는 상위의 `endsAt` 또는 `recruitmentEndsAt`으로 제공합니다. 원문 입력과 서비스가 보완한 값을 구분해 안내합니다.

## DB 연결

- 공고의 물리 항목·일정·분류: [공모전 테이블](../database/contests.md)
