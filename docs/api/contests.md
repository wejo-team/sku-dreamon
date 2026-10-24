# 공모전 API

**상태: 공개 상세 구현 · 목록 설계.** 공모전 상세의 [라우터](../../backend/app/routers/contests.py), [조회 서비스](../../backend/app/services/contests.py)와 [저장 조회](../../backend/app/repositories/contests.py), [응답 DTO](../../backend/app/schemas/contests.py)를 구현했습니다. 경로는 `/api/v1` 기준이며, 제품 정책은 연결한 기능 명세를 따릅니다.

[공고 저장 모델·접수 규칙](../database/contests.md)은 별도로 구현했습니다. 팀 공개 상세에서 사용하는 [ContestSummary·DeadlineInterpretation](../../backend/app/schemas/contests.py)와 실제 전체 팀 수 집계는 구현했습니다. 상세는 원문·대상·분야·전체 팀 수를 단일 SQL 스냅샷으로 반환합니다. 공고 목록 HTTP 경로는 아직 제공하지 않으며, 목록 기본 상태·정렬 및 공고 등록·수정 운영 정책은 별도로 검토합니다.

- 먼저 [API 목록](#endpoints)에서 경로·권한·성공 응답을 찾습니다.

- 입력은 [검색 조건](#queries), 출력은 [공모전 데이터](#contest-summary)의 코드·생성 문서에서 확인합니다.

- ID·코드·시각·정원·버전은 [공통 타입](conventions.md#types), 실패는 [공통 오류](conventions.md#errors)를 사용합니다. 단건·복합 성공은 [Success&lt;T&gt;](conventions.md#success-responses), 목록은 [Page&lt;T&gt;](conventions.md#pagination)를 사용하며 `Page<T>`는 `data: T[]`와 `pagination`을 가진 응답입니다.

**표 읽기:** 응답 DTO 표는 `data` 내부에서 사용하는 데이터 구조를 정의하며, 각 DTO의 모든 필드는 필수입니다. `null` 허용 여부는 타입에 따로 표시하며, `null`인 필드를 생략하지 않습니다. 요청은 각 표에 필수 여부를 표시합니다. 선언하지 않은 요청 필드는 422입니다. 일반 텍스트의 정책상 글자 수와 Unicode 계수 단위의 미정 사항은 [공통 계약](conventions.md)을 따릅니다.

<a id="endpoints"></a>

## API 목록

아래 모든 작업에 입력 형식 오류 **422**, 일시 장애 **503**, 내부 오류 **500**이 공통 적용됩니다. 로그인 또는 관계 권한이 필요한 작업에는 **401**, 상태 변경 요청에는 [공통 CSRF 검사 실패의 403](conventions.md#session-auth)도 적용됩니다. 표의 실패 열은 그 밖의 응답을 나타냅니다. 실패 본문 형식은 [공통 오류 계약](conventions.md)에 있습니다.

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /contests` | 공개, 공모전 검색 조건 | 200 `Page<ContestSummary>` | — |
| `GET /contests/{contestId}` | 공개, 공고 UUID | 200 `Success<ContestDetail>` | 404 `CONTEST_NOT_FOUND` 공고 없음 |

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

정확한 필드는 [ContestSummary](../../backend/app/schemas/contests.py)와 생성 OpenAPI를 따릅니다. 이 DTO는 공개 팀 상세의 중첩 공고 요약과 공고 상세의 공통 필드에 사용합니다. 분야는 실제 공고 분야이고, `teamCount`는 상태에 관계없는 연결 팀 전체 수이며, `registrationStatus`는 같은 조회 시각의 시작·마감 경계로 계산합니다. `isDemo`는 [승인된 시연 목록](../../backend/app/core/demo_data.py)을 조회합니다.

D-day는 `endsAt`과 표시 시간대를 기준으로 표현합니다. 저장된 접수 상태 문자열이나 별도 팀 수를 클라이언트가 추정하지 않습니다.

<a id="contest"></a>

### ContestDetail — 상세

정확한 필드는 [ContestDetail](../../backend/app/schemas/contests.py)과 서버의 `/docs`, `/openapi.json`을 따릅니다. `ContestSummary`의 모든 필드에 확인된 설명·참가 대상·원문 참가 조건·참가 인원·일정 근거·제출물·시상·문의처·자료 확인 시각·공식 원문 URL을 추가합니다. 선택 정보는 값이 없더라도 필드를 생략하지 않고 null로 제공합니다.

참가 대상은 중복 없이 1~2개이며 `student`와 `general`은 함께 제공할 수 있습니다. `unrestricted`·`unknown`은 단독이며 이를 사용자 자격의 자동 판정으로 확대하지 않습니다. 응답에 팀장·지원자·계정·세션 정보나 내부 생성 요청 식별값은 포함하지 않습니다.

<a id="participation-capacity"></a>

### ParticipationCapacity — 참가 인원 조건

정확한 필드·타입은 [ParticipationCapacity](../../backend/app/schemas/contests.py)와 생성 OpenAPI를 따릅니다. `kind`, `minimumMembers`, `maximumMembers`는 모두 필수이며 수치는 `PositiveBigInt` 십진 문자열입니다. `range`는 양의 최소·최대와 최소 ≤ 최대를 요구하고, `unlimited`는 최대가 null이며 확인된 최소만 제공합니다. `unknown`은 양쪽 모두 null입니다.

`unknown`은 미확인 필수 인원 자료의 신규 등록·팀 생성을 허용하는 계약이 아닙니다. `unlimited` 공고라도 팀장은 양의 목표 정원을 직접 입력합니다.

<a id="contest-timing"></a>

### ContestTiming — 접수 일정

정확한 필드는 [ContestTiming](../../backend/app/schemas/contests.py)과 생성 OpenAPI를 따릅니다. 시작·마감 경계는 상위 `ContestDetail`과 같은 값을 반환하며, 원문 시작 날짜·선택 시각·선택 시간대와 실제 적용 시간대·시간대 보완 여부를 구분합니다. 마감은 아래 `DeadlineInterpretation`으로 제공합니다.

상세 조회는 확인되어 저장된 경계와 원문을 그대로 읽으며 누락된 시작 시각을 임의 보완하거나 날짜·시간대를 다시 해석하지 않습니다. 접수 상태는 조회 시각이 시작 경계 이상·마감 경계 미만일 때만 `open`이고, 마감 상태에서도 상세와 원문 링크는 공개합니다.

원문에 시작 시각이 없거나 모호한 경우의 처리까지 이 계약으로 확정하지 않습니다. 등록 전 확인과 미정 범위는 [공고 테이블](../database/contests.md)을 따릅니다.

<a id="deadline-interpretation"></a>

### DeadlineInterpretation — 마감 안내 정보

정확한 필드는 [DeadlineInterpretation](../../backend/app/schemas/contests.py)와 생성 OpenAPI를 따릅니다. 원문 날짜·선택 시각·선택 시간대와 계산에 적용한 시간대·시각 보완 여부·시간대 보완 여부를 반환합니다. 원문 시각·시간대가 없으면 null을 유지합니다.

실제 마감 경계는 상위의 `endsAt` 또는 `recruitmentEndsAt`으로 제공합니다. 원문 입력과 서비스가 보완한 값을 구분해 안내합니다.

## 검증

[PostgreSQL·HTTP 상세 테스트](../../backend/tests/integration/test_contest_detail.py)는 미인증 열람·UUID 오류·시각 경계·원문/null 보존·정원 전송·전체 팀 수·동시 변경의 동일 스냅샷을 확인합니다. [DTO 테스트](../../backend/tests/unit/test_contest_detail_schemas.py)는 큰 정원의 십진 문자열과 필수 null 계약을 검증합니다. 목록 정책·운영 저장 경로·화면 완료 조건은 이 상세 API의 검증 범위에 포함하지 않습니다.

## DB 연결

- 공고의 물리 항목·일정·분류: [공모전 테이블](../database/contests.md)
