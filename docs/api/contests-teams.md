# 공모전과 팀 API

**상태: 설계 제안 · 미구현.** 공모전 탐색, 팀 생성·모집, 지원·검토·선발과 워크스페이스의 전송 계약을 정의합니다. 경로는 `/api/v1` 기준이며, 제품 정책은 연결한 기능 명세를 따릅니다.

- 먼저 [API 목록](#endpoints)에서 경로·권한·성공 응답을 찾습니다.
- 입력은 [검색 조건](#queries)과 [요청 본문](#requests), 출력은 [공모전](#contest-summary)·[팀](#team-summary)·[지원](#application) 데이터 표에서 확인합니다.
- ID·코드·시각·정원·버전은 [공통 타입](conventions.md#types), 페이지는 [Page&lt;T&gt;](conventions.md#pagination), 실패는 [공통 오류](conventions.md#errors)를 사용합니다. `Page<T>`는 `items: T[]`와 `pagination`을 가진 공통 응답입니다.

**표 읽기:** 응답 표의 모든 필드는 필수입니다. `null` 허용 여부는 타입에 따로 표시하며, `null`인 필드를 생략하지 않습니다. 요청은 각 표에 필수 여부를 표시합니다. 선언하지 않은 요청 필드는 422입니다. 일반 텍스트의 정책상 글자 수와 Unicode 계수 단위의 미정 사항은 [공통 계약](conventions.md)을 따릅니다.

<a id="endpoints"></a>

## API 목록

아래 모든 작업에 입력 형식 오류 **422**, 일시 장애 **503**, 내부 오류 **500**이 공통 적용됩니다. 로그인 또는 관계 권한이 필요한 작업에는 **401**, 상태 변경 요청에는 [공통 CSRF 검사 실패의 403](conventions.md#session-auth)도 적용됩니다. 표의 실패 열은 그 밖의 응답을 나타냅니다. 실패 본문 형식은 [공통 오류 계약](conventions.md)에 있습니다.

### 공모전과 공개 팀 탐색

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /contests` | 공개, 공모전 검색 조건 | 200 `Page<ContestSummary>` | — |
| `GET /contests/{contestId}` | 공개, 공고 UUID | 200 `Contest` | 404 공고 없음 |
| `GET /contests/{contestId}/teams` | 공개, 공고 UUID·팀 검색 조건 | 200 `Page<TeamSummary>` | 404 공고 없음 |
| `GET /teams` | 공개, 팀 검색 조건·선택 `contestId` | 200 `Page<TeamSummary>` | — |
| `GET /teams/{teamId}` | 공개, 팀 UUID | 200 `Team` | 404 팀 없음 |

공고는 접수 예정·중·마감 상태 모두 상세 열람할 수 있습니다. 공개 팀 응답에는 지원서·지원자 프로필·팀 공간 데이터를 포함하지 않습니다. 화면별 정보 구분은 [공고 탐색](../specs/contests.md#exploration-ui)과 [팀 모집 명세](../specs/team-recruitment.md)를 따릅니다.

### 팀 생성과 워크스페이스

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /teams` | 로그인, `TeamCreate` | 첫 생성 201 `Team`, 동일 요청 재전송 200 `Team` | 404 공고 없음, 409 공고·정원·소속·코드·요청 ID 충돌 |
| `GET /me/teams` | 본인, 페이지 조건 | 200 `Page<WorkspaceTeam>` | — |
| `GET /teams/{teamId}/space` | 현재 팀장·확정 팀원, 팀 UUID | 200 `TeamSpace` | 403 현재 소속 아님, 404 팀 없음 |
| `PUT /teams/{teamId}/recruitment/closure` | 해당 팀장, 팀 UUID·`VersionedAction` | 200 `RecruitmentResult` | 403 권한, 404 팀 없음, 409 상태·버전 충돌 |
| `PUT /teams/{teamId}/recruitment/reopening` | 해당 팀장, 팀 UUID·`VersionedAction` | 200 `RecruitmentResult` | 403 권한, 404 팀 없음, 409 기한·정원·상태·버전 충돌 |

`GET /me/teams`는 현재 팀장·확정 팀원인 팀만 반환합니다. 대기 지원은 내 지원 목록에서 조회합니다. 팀 공간과 최신 프로필의 열람 범위는 [팀원 데이터](#team-member)에 정의합니다.

### 지원과 팀장 검토

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /teams/{teamId}/applications` | 로그인, 팀 UUID·`ApplicationCreate` | 첫 접수 201 `Application`, 동일 요청 재전송 200 `Application` | 404 팀 없음, 409 프로필·모집·중복·재지원·소속·코드·요청 ID 충돌 |
| `GET /me/applications` | 본인, 페이지 조건·선택 `status` | 200 `Page<MyApplication>` | — |
| `GET /applications/{applicationId}` | 지원 본인 또는 받은 팀장, 지원 UUID | 200 `Application` | 404 없음 또는 관계 밖 |
| `PUT /applications/{applicationId}/cancellation` | 지원 본인, 지원 UUID·`VersionedAction` | 200 `CancellationResult` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `GET /teams/{teamId}/applicants` | 해당 팀장, 팀 UUID·페이지 조건·선택 `status` | 200 `Page<Applicant>` | 403 권한, 404 팀 없음 |
| `GET /applications/{applicationId}/applicant` | 받은 팀장, 지원 UUID | 200 `Applicant` | 403 행동 권한, 404 없음 또는 관계 밖 |
| `PUT /applications/{applicationId}/review-start` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `Application` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `PUT /applications/{applicationId}/rejection` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `Application` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `PUT /applications/{applicationId}/selection` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `SelectionResult` | 403 행동 권한, 404 없음 또는 관계 밖, 409 공고 기한·상태·정원·소속·버전 충돌 |

다른 팀·일반 팀원·일반 사용자는 지원서 존재를 확인할 수 없도록 404로 처리합니다. 존재를 확인할 수 있는 관계라도 해당 행동을 수행할 권한이 없으면 403입니다. 목록·상세·AI 결과 조회만으로 지원 상태를 `reviewing`으로 변경하지 않으며, 팀장이 검토 시작 API를 명시적으로 실행해야 합니다. 검토 시작은 선발·미선발의 필수 선행 작업이 아닙니다.

<a id="queries"></a>

## 검색 조건과 정렬

경로 변수 `contestId`, `teamId`, `applicationId`는 해당 경로에서 모두 필수 `Id`입니다. 목록의 아래 query는 모두 선택 입력입니다.

| query | 타입·기본값 | 적용 범위·의미 |
| --- | --- | --- |
| `page`, `pageSize` | 정수, 기본 1·20, 페이지 크기 최대 100 | 모든 페이지 목록. 범위·마지막 페이지 보정은 [공통 계약](conventions.md) |
| `q` | 문자열, 생략 또는 trim 후 빈 값은 검색 없음 | 공모전·팀 탐색. 검색 대상은 아래 표 |
| `fieldCode` | `CatalogCode`, 생략 시 제한 없음 | 공모전 목록. 저장된 전체 분야 중 하나라도 해당 코드를 포함 |
| `sort` | `created_desc` 또는 `deadline_asc`, 기본 `created_desc` | 공모전 목록 |
| `registrationStatus` | `RegistrationStatus` | 공모전 목록. 지정한 접수 상태만 조회 |
| `roleCode` | `CatalogCode`, 생략 시 제한 없음 | 팀 목록. 모집 역할 하나와 일치하는 팀 |
| `recruitingOnly` | boolean, 기본 `false` | 팀 목록. `true`이면 공통 모집 가능 조건을 충족한 팀만 |
| `contestId` | `Id`, 생략 시 제한 없음 | `GET /teams`만. 해당 공고의 팀으로 제한 |
| `status` | `ApplicationStatus`, 생략 시 모든 상태 | 내 지원·팀장 지원자 목록 |

| 목록 | 검색 대상 | 안정 정렬 |
| --- | --- | --- |
| 공모전 | 제목·주최자·분야 표시명 | 등록순 `createdAt DESC, id DESC`; 마감순 `endsAt ASC, id ASC` |
| 특정 공모전의 팀 | 팀명·소개/목표·모집 역할 표시명 | `createdAt DESC, id DESC` |
| 전체 팀 | 팀명·소개/목표·모집 역할 표시명·공모전명 | `createdAt DESC, id DESC` |
| 내 팀 | 검색어 없음, 현재 소속만 | 소속의 `joinedAt DESC, membershipId DESC` |
| 내 지원·팀장 지원자 | 검색어 없음, 지원 시도별 목록 | 지원의 `submittedAt DESC, id DESC` |

`Contest.teamCount`는 연결된 **전체 팀 수**이고 페이지의 `pagination.total`은 현재 권한·필터에 맞는 결과 수입니다. `TeamSummary.isRecruiting`은 서버가 계산한 공통 모집 표시로, 특정 회원의 신규 지원 성공을 보장하지 않습니다.

`registrationStatus` 생략 시 마감 공고의 기본 포함·배치는 [CONTEST-05](../specs/contests.md#open-questions) 결정이 필요합니다. 등록순 기본 정렬만으로 이 제품 정책을 확정하지 않습니다.

<a id="values"></a>

## 공통 상태값

| 타입 | 값과 의미 |
| --- | --- |
| `RegistrationStatus` | `scheduled` 접수 예정, `open` 접수 중, `closed` 접수 마감 |
| `AudienceCode` | `student` 대학생, `general` 일반인, `unrestricted` 제한 없음, `unknown` 미확인 |
| `RecruitmentState` | `open` 모집 중, `closed` 모집 마감 |
| `ApplicationStatus` | `submitted` 지원 완료, `reviewing` 검토 중, `selected` 선발, `rejected` 미선발, `canceled` 취소, `discarded` 폐기 |

팀 모집은 두 상태만 사용하며 검토는 개별 지원 상태입니다. 팀의 `open`은 저장 상태이고, `isRecruiting`은 그 상태와 현재 공고·팀 기한·잔여 정원을 함께 평가한 신규 접수 가능 표시입니다. 기한 경과 시 `recruitmentState="open"`이면서 `isRecruiting=false`일 수 있으며, 화면의 모집 배지·버튼은 실제 접수 불가를 모집 마감으로 표시합니다. 기한이 지났다고 저장 상태를 자동으로 `closed`로 바꾸는 작업을 전제하지 않습니다. 실제 전이는 [모집 상태 정책](../specs/team-recruitment.md#team-state-transitions)과 [지원 상태 정책](../specs/team-recruitment.md#application-transitions)을 따릅니다.

<a id="requests"></a>

## 요청 본문

<a id="team-create"></a>

### TeamCreate — 팀 생성

| 필드 | 타입 | 필수 | 제약·처리 |
| --- | --- | --- | --- |
| `requestId` | `Id` | 예 | 생성 시도 식별 UUID. 같은 시도의 재전송은 같은 값 |
| `contestId` | `Id` | 예 | 참여할 공고 |
| `name` | string | 예 | 팀명 2~40자 |
| `introduction` | string | 예 | 소개/목표 10~1,000자 |
| `capacity` | `PositiveBigInt` | 예 | 팀장 포함 목표 정원의 십진 문자열. 공식 인원 조건에 맞아야 함 |
| `roleCodes` | `CatalogCode[]` | 예 | 중복 불가. `capacity="1"`이면 `[]`, 2명 이상이면 1~6개 |
| `recruitmentDeadline` | `DeadlineInput` | 예 | 입력 날짜·선택 시각·선택 시간대 |

선택 역할은 공통 목록을 사용합니다. 공고 분야·개인/팀 유형·주당 시간·팀장 ID는 입력에 없습니다. 서버가 인증 주체를 팀장으로 사용합니다. 팀·팀장 소속 생성과 같은 공모전에서 본인이 제출한 `submitted`·`reviewing` 지원의 폐기·사건·본인 알림을 한 트랜잭션에서 처리합니다. 다른 공모전이나 이미 종결된 지원은 변경하지 않으며, 생성 실패 시 대기 지원도 유지합니다. 근거는 [동시 지원과 소속 확정](../specs/team-recruitment.md#parallel-applications)에 있습니다. 정원에 기본값이나 별도 서비스 상한을 추가하지 않으며 [공식 정원과 생성 항목](../specs/team-recruitment.md#official-capacity)을 따릅니다.

다음 예시의 UUID와 `ROLE_EXAMPLE`은 형식 설명용이며 실제 운영 코드가 아닙니다.

```json
{
  "requestId": "11111111-1111-4111-8111-111111111111",
  "contestId": "22222222-2222-4222-8222-222222222222",
  "name": "예시 프로젝트 팀",
  "introduction": "공모전에 함께 참여할 동료를 찾는 예시 팀입니다.",
  "capacity": "4",
  "roleCodes": ["ROLE_EXAMPLE"],
  "recruitmentDeadline": { "date": "2026-11-30", "time": null, "timeZone": null }
}
```

<a id="application-create"></a>

### ApplicationCreate — 신규 지원

| 필드 | 타입 | 필수 | 제약·처리 |
| --- | --- | --- | --- |
| `requestId` | `Id` | 예 | 새 접수 시도 식별 UUID. 취소·폐기 후 허용된 재지원은 새 값 |
| `roleCode` | `CatalogCode` | 예 | 공통 역할 하나. 팀 모집 역할과 다르다는 이유로 거절하지 않음 |
| `message` | string 또는 null | 아니오 | 최대 1,000자. 생략·null·trim 후 빈 본문은 메시지 없음인 null로 정규화 |

공개 전환·프로필 보완은 접수와 별도 저장입니다. 서버가 [지원 직전 확인](../specs/profile.md#before-application)과 [현재 모집 조건](../specs/team-recruitment.md#recruitment-conditions)을 다시 검사하며, 비공개 프로필을 자동으로 공개하지 않습니다. 같은 공모전에 현재 확정 소속이 있으면 신규 지원을 거부하며, 대상 팀의 미선발 이력이 있으면 같은 팀 재지원을 거부합니다. 미선발 검사는 최신 지원 한 건만이 아니라 해당 팀에 대한 본인의 종결 이력 전체를 확인합니다. 취소·폐기 후 새 지원에도 현재 프로필 공개·필수 입력·무소속·모집 조건을 다시 적용하며 아래 [재지원 계약](#transitions)을 따릅니다.

다음 UUID·역할 코드는 형식 설명용입니다.

```json
{
  "requestId": "33333333-3333-4333-8333-333333333333",
  "roleCode": "ROLE_EXAMPLE",
  "message": "자료조사 역할로 함께 참여하고 싶습니다."
}
```

### 상태 변경 본문

검토 시작·미선발·선발·취소에는 **지원의 버전**, 모집 종료·재개에는 **팀의 버전**을 [VersionedAction](conventions.md#versioned-action)의 필수 `expectedVersion`으로 보냅니다.

```json
{ "expectedVersion": "3" }
```

<a id="deadline-input"></a>

### DeadlineInput — 원문 마감 입력

| 필드 | 타입 | 필수 | 제약·처리 |
| --- | --- | --- | --- |
| `date` | string (`YYYY-MM-DD`) | 예 | 실제 달력 날짜 |
| `time` | string 또는 null | 아니오 | 24시간 `HH:mm` 또는 `HH:mm:ss`. 시 00~23, 분·초 00~59. 생략은 null |
| `timeZone` | string 또는 null | 아니오 | IANA 시간대 또는 명시적 UTC offset으로 정규화·검증. 생략은 null |

서버가 원문 우선 정책으로 UTC 마감 경계와 보완 정보를 계산합니다. 시간대가 없으면 한국시간, 시각이 없으면 해당 날짜 끝까지이며, 반환 경계는 다음 날 00시인 **제외 경계**입니다. 유효하지 않거나 단일 시각으로 결정할 수 없는 입력은 422로 응답합니다. 원문·보완 안내의 근거는 [공고 일정 정책](../specs/contests.md)에 있습니다.

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
| `isDemo` | boolean | 시연 데이터 여부 |
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

<a id="team-summary"></a>

## 팀과 워크스페이스 응답

### TeamSummary — 팀 목록

| 필드 | 타입 | 의미·제약 |
| --- | --- | --- |
| `id` | `Id` | 팀 식별자 |
| `version` | `Version` | 현재 팀 버전 |
| `contestId` | `Id` | 연결 공고 |
| `contestTitle` | string | 연결 공고 제목 |
| `name`, `introduction` | string | 팀명·소개/목표 |
| `fieldCodes` | `CatalogCode[]` | 연결 공고에서 조회한 분야, 중복 없이 0~3개 |
| `roleCodes` | `CatalogCode[]` | 모집 역할, 중복 없이 최대 6개. 정원 1명은 빈 배열 |
| `capacity` | `PositiveBigInt` | 팀장 포함 목표 정원 |
| `memberCount` | integer | 현재 팀장·확정 팀원 수, 1~9,007,199,254,740,991 |
| `recruitmentState` | `RecruitmentState` | 저장된 `open`·`closed` 상태. 기한·정원을 반영한 현재 접수 가능 여부는 `isRecruiting` |
| `closedReason` | `capacity_reached`, `leader_closed` 또는 null | 저장 상태가 `closed`일 때 사유, `open`이면 null. 단순 기한 경과의 사유값은 추가하지 않음 |
| `recruitmentEndsAt` | `Timestamp` | 팀 모집 마감의 제외 경계 |
| `isRecruiting` | boolean | 현재 공통 모집 가능 조건에 따른 계산값 |
| `isDemo` | boolean | 시연 데이터 여부 |
| `createdAt` | `Timestamp` | 팀 생성 시각 |
| `recruitmentDeadline` | `DeadlineInterpretation` | 모집 마감의 원문·보완 정보 |

<a id="team"></a>

### Team — 공개 모집글

`TeamSummary`의 **모든 필드**에 아래 필드를 추가합니다.

| 추가 필드 | 타입 | 의미 |
| --- | --- | --- |
| `ownerAccountId` | `Id` | 팀장 계정 식별자 |
| `contest` | `ContestSummary` | 연결된 공고 요약 |

<a id="team-member"></a>

### TeamMember — 현재 팀원의 소속 표시

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `membershipId` | `Id` | 현재 소속 식별자 |
| `accountId` | `Id` | 소속 계정 식별자 |
| `realName` | string | 현재 같은 팀 구성원을 식별하는 실명 |
| `isDemo` | boolean | `accounts.is_demo`의 서버 관리값. 전체 프로필 열람 여부와 별개로 팀원 시연 표시를 제공 |
| `membershipRole` | `leader` 또는 `member` | 팀장/팀원 구분 |
| `roleCode` | `CatalogCode` 또는 null | 선발된 지원 역할. 지원을 통해 생성되지 않은 팀장 소속은 null |
| `joinedAt` | `Timestamp` | 소속 시작 시각 |
| `profile` | [Profile](accounts-profiles.md#profile) 또는 null | 전체 현재 프로필. 본인·공개 프로필·지원받은 팀장 권한에서만 제공 |

**소속 표시와 프로필 열람을 분리합니다.** 현재 팀원에게는 팀 화면의 실명 표시 정책에 맞춰 `realName`과 소속 정보를 제공하지만, 일반 팀원이 비공개 팀원을 조회하면 `profile=null`입니다. 이때도 [시연 데이터 안내](../specs/sprint-1.md#demo-data-scope)를 위해 `isDemo`는 제공합니다. 비공개 사진·학사 정보·경험·포트폴리오를 소속 응답에 별도 복제하지 않습니다. `realName`은 팀 공간 접근 권한 안에서만 제공하며 일반 검색·AI 사람 추천의 공개 예외로 확대하지 않습니다.

근거는 [팀 화면의 실명 표시](../specs/team-recruitment.md)와 [팀 공간 접근](../specs/team-recruitment.md#team-workspace-access), [프로필 공개 범위](../specs/profile.md#visibility)입니다. 팀장이라는 이유만으로 지원 관계가 없는 비공개 프로필까지 열람할 수는 없습니다.

<a id="team-space"></a>

### TeamSpace — 팀 공간

| 필드 | 타입 | 의미·제약 |
| --- | --- | --- |
| `team` | `Team` | 팀 상세 |
| `members` | `TeamMember[]` | 현재 구성원, 팀장 포함 최소 1명 |
| `viewerRole` | `leader` 또는 `member` | 현재 조회자의 소속 역할 |
| `pendingApplicationCount` | integer 또는 null | 팀장에게만 0~9,007,199,254,740,991 범위의 대기 지원 수. 일반 팀원에게 null |

지원자 내용은 별도의 팀장 API로 조회합니다. 팀 공간에 일반 팀원의 지원자 관리 권한을 추가하지 않습니다.

<a id="workspace-team"></a>

### WorkspaceTeam — 내 팀 목록 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `team` | `TeamSummary` | 현재 소속 팀 요약 |
| `membershipId` | `Id` | 본인 현재 소속 식별자 |
| `membershipRole` | `leader` 또는 `member` | 본인 소속 역할 |
| `roleCode` | `CatalogCode` 또는 null | 본인 선발 역할. 팀장 소속은 null |
| `pendingApplicationCount` | integer 또는 null | 팀장에게만 대기 지원 수, 일반 팀원에게 null. 범위는 `TeamSpace`와 같음 |

<a id="application"></a>

## 지원과 처리 결과 응답

### Application — 지원서

| 필드 | 타입 | 의미·제약 |
| --- | --- | --- |
| `id` | `Id` | 지원 시도 식별자. 신규·재지원마다 새 ID |
| `version` | `Version` | 현재 지원 버전 |
| `teamId`, `contestId` | `Id` | 지원한 팀과 공고 |
| `applicantAccountId` | `Id` | 지원자 계정 |
| `roleCode` | `CatalogCode` | 지원 역할 하나 |
| `message` | string 또는 null | 선택 메시지, 최대 1,000자 |
| `status` | `ApplicationStatus` | 현재 지원 상태 |
| `discardReason` | `selected_elsewhere`, `team_created_elsewhere` 또는 null | 다른 팀 선발 또는 본인 팀 생성에 따른 폐기 사유. `discarded`일 때 필수 값, 그 외 null |
| `discardedByApplicationId` | `Id` 또는 null | 다른 팀 선발로 폐기된 경우 원인 지원 ID. 해당 지원도 열람할 수 있는 본인에게만 제공하며 받은 팀장에게는 null |
| `discardedByTeamId` | `Id` 또는 null | 본인 팀 생성으로 폐기된 경우 생성한 팀 ID. 본인에게만 제공하며 받은 팀장에게는 null |
| `submittedAt`, `updatedAt` | `Timestamp` | 최초 접수·마지막 변경 시각 |

`Application`에는 프로필을 포함하지 않습니다. 지원서 열람 권한만으로 모든 조회자에게 팀장 검토용 최신 전체 프로필을 제공하지 않습니다. 폐기 원인 ID 두 필드는 동시에 값을 갖지 않습니다. 받은 팀장에게도 폐기 사유는 제공하지만 다른 팀·지원의 원인 ID는 제공하지 않습니다. 팀 생성 폐기의 원인 팀은 DB에 기록한 팀장 소속에서 조회하며 가상의 선발 지원 ID를 만들지 않습니다.

<a id="my-application"></a>

### MyApplication — 내 지원 목록 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `application` | `Application` | 본인 지원 시도 |
| `team` | `TeamSummary` | 지원한 팀 요약 |
| `isCurrentMember` | boolean | 현재 해당 팀 소속인지 여부 |

취소·폐기된 이전 시도와 신규 지원을 구분합니다. 과거 지원의 보존 기간은 별도 미정입니다.

<a id="applicant"></a>

### Applicant — 팀장 검토 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `application` | `Application` | 받은 지원서 |
| `profile` | [Profile](accounts-profiles.md#profile) | 해당 지원자의 최신 전체 프로필. `version`과 시연 데이터 여부인 `isDemo` 포함 |
| `isSelectionCandidate` | boolean | 현재 지원이 `submitted`·`reviewing`이고 같은 공모전의 확정 소속이 없는지. 마감·정원까지 검증한 실제 선발 실행 허가는 아님 |

지원 후 비공개 전환, 취소·미선발·폐기 이후에도 받은 팀장의 [최신 프로필 열람 관계](../specs/profile.md#application-profile)를 유지합니다. 새 후보 여부와 기존 AI 검토 가능 여부는 다르며, 이 관계를 일반 사람 검색에 확대하지 않습니다.

<a id="action-results"></a>

### 처리 결과

| 응답 타입 | 필수 필드 | 의미 |
| --- | --- | --- |
| `SelectionResult` | `application: Application`, `team: TeamSummary`, `membershipId: Id` | 선발한 지원·해당 팀·생성된 현재 소속. 다른 팀 지원 목록·메시지·건수는 포함하지 않음 |
| `CancellationResult` | `application: Application`, `membershipEnded: boolean` | 선발 후 취소로 소속을 종료했다면 true. 이미 취소된 요청은 기존 취소 결과를 유지하며 자리를 다시 반환하지 않음 |
| `RecruitmentResult` | `team: TeamSummary` | 모집 종료·재개 후 팀의 현재 상태와 버전 |

<a id="transitions"></a>

## 상태 변경·충돌·재시도

### 생성 요청의 재전송

팀·지원 생성에서 서버는 인증 주체·경로·정규화한 최초 입력으로 같은 시도를 판별합니다. 첫 생성은 201, 같은 `requestId`와 같은 입력의 재전송은 기존 리소스를 200으로 반환합니다. 같은 ID의 다른 입력은 409 `REQUEST_ID_REUSED`입니다. 이후 팀·지원의 상태가 바뀌어도 과거 생성 재시도를 새 행동으로 실행하지 않습니다.

취소·폐기 후에는 같은 공모전에 현재 소속이 없고 현재 모집·프로필 조건을 충족하면 새 `requestId`·새 지원 ID로 접수합니다. 미선발 이력이 있는 같은 팀에는 재지원할 수 없고, 다른 팀에는 현재 조건을 충족하면 지원할 수 있습니다. `rejected`·`canceled`·`discarded` 기록은 복원하거나 다른 상태로 바꾸지 않습니다. 이전 시도에 대한 늦은 요청은 새 시도를 변경하지 않습니다. 근거는 [재지원](../specs/team-recruitment.md#reapplication)과 [소속 확정 시 다른 대기 지원 폐기](../specs/team-recruitment.md#parallel-applications)입니다. 팀 생성의 프로필 완성 요구는 [PROFILE-03](../specs/profile.md#open-questions)에 남깁니다.

### 버전이 있는 행동

행동 권한·열람 관계를 확인하고 대상을 잠근 뒤, 대상 버전과 `expectedVersion`을 **상태 전이 판단보다 먼저 비교**합니다. 다르면 현재 상태가 요청 결과와 같아도 409 `VERSION_CONFLICT`입니다. 아래 재요청 성공은 일치하는 현재 버전이 전제입니다.

| 행동 | 허용된 전이·재요청 | 성공 시 함께 처리하는 것 |
| --- | --- | --- |
| 검토 시작 | `submitted` → `reviewing`. 이미 `reviewing`이면 no-op 200 | 해당 지원 버전·사건·본인 알림만 갱신. 팀 모집 상태·정원은 유지 |
| 미선발 | `submitted`·`reviewing` → `rejected`. 이미 `rejected`이면 no-op 200 | 해당 지원 버전·사건·본인 알림 갱신. 소속·정원은 유지 |
| 선발 | `submitted`·`reviewing` → `selected`. 이미 `selected`이며 동일한 현재 소속이면 no-op 200 | 현재 소속 생성, 같은 공모전 다른 대기 지원 폐기, 사건·알림. 정원 충족 시 모집 마감 |
| 본인 취소 | `submitted`·`reviewing`·`selected` → `canceled`. 이미 `canceled`이면 no-op 200 | 선발 후 취소는 소속 종료·자리 반환·사건·알림. 자동 모집 재개·폐기 지원 복원 없음 |
| 모집 종료 | `open` → `closed`, 사유 `leader_closed`. 이미 `closed`이면 사유를 보존하고 no-op 200 | 기존 지원·소속 유지. 대기 지원을 자동 미선발 처리하지 않음 |
| 모집 재개 | `closed` → `open`, 마감 사유 null. 이미 `open`이며 현재 모집 가능하면 no-op 200 | 현재 공고 접수·팀 모집 기한·잔여 정원 확인. 폐기 지원 복원 없음 |

미선발은 팀장의 명시적 요청에서만 실행하며 모집 종료·기한 경과·정원 충족으로 자동 실행하지 않습니다. `rejected`·`canceled`·`discarded`에서 다른 상태로 가는 요청은 `INVALID_APPLICATION_STATE`이며, 표의 동일 상태 no-op은 상태 복원이 아닙니다. no-op은 버전·사건·알림을 추가하지 않습니다.

실제로 `submitted`·`reviewing`을 선발하려면 현재 공고 접수 기간 안이고 여석·무소속·팀장 권한을 충족해야 합니다. 선발 검사는 신규 접수용 `isRecruiting`과 독립적이며, 팀의 저장 상태가 `closed`이거나 팀 모집 기한이 지났어도 기존 유효 지원은 선발할 수 있습니다. `현재 시각 >= 공고 endsAt`이면 실제 선발을 `CONTEST_NOT_OPEN`으로 거부합니다. 이미 선발된 동일 소속에 대한 버전 일치 no-op은 새 선발이 아니므로 이후 공고 마감만으로 실패시키지 않습니다. 정책 원본은 [기존 지원 선발 가능 기간](../specs/team-recruitment.md#selection-window)입니다.

팀 생성에 따른 폐기, 검토 시작·미선발·선발·취소의 지원 상태·소속·사건·알림 변경은 해당 유스케이스의 [동일 트랜잭션](../database/transactions.md)에서 처리합니다. 실패하면 부분 선발·부분 폐기를 성공 결과로 반환하지 않습니다. 응답 유실 후에는 현재 리소스를 다시 조회해 결과와 버전을 확인합니다.

### 409 업무 오류

| 요청 | 정의한 오류 코드 |
| --- | --- |
| 팀 생성 | `CONTEST_NOT_OPEN`, `CAPACITY_OUT_OF_RANGE`, `MEMBERSHIP_CONFLICT`, `INVALID_CATALOG_SELECTION`, `REQUEST_ID_REUSED` |
| 신규 지원 | `PROFILE_REQUIRED`, `PROFILE_PRIVATE`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `RECRUITMENT_CLOSED`, `RECRUITMENT_DEADLINE_PASSED`, `DUPLICATE_APPLICATION`, `REAPPLICATION_NOT_ALLOWED`, `MEMBERSHIP_CONFLICT`, `INVALID_CATALOG_SELECTION`, `REQUEST_ID_REUSED` |
| 검토 시작·미선발 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE` |
| 선발 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `MEMBERSHIP_CONFLICT` |
| 본인 취소 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE` |
| 모집 종료 | `VERSION_CONFLICT`, `INVALID_RECRUITMENT_STATE` |
| 모집 재개 | `VERSION_CONFLICT`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `RECRUITMENT_DEADLINE_PASSED`, `INVALID_RECRUITMENT_STATE` |

공개 전환을 화면에서 확인했더라도 지원 직전 비공개로 바뀌었다면 `PROFILE_PRIVATE`입니다. 현재 유효 지원의 중복은 `DUPLICATE_APPLICATION`, 대상 팀의 미선발 이력에 따른 재지원 거부는 `REAPPLICATION_NOT_ALLOWED`, 같은 공모전의 현재 소속 충돌은 `MEMBERSHIP_CONFLICT`입니다. 다른 팀의 지원 목록이나 건수를 오류 세부사항에 포함하지 않습니다.

팀장 선발 취소·강퇴·팀장 탈퇴·팀 삭제와 별도 소속 탈퇴 API는 [MVP 범위 밖](../specs/team-recruitment.md#membership-exclusions)입니다. 본인의 선발 후 지원 취소는 위 계약을 유지합니다. 모집 정보 편집과 제출 후 지원 메시지 수정은 [미정 사항](../specs/team-recruitment.md#open-questions)이며 범용 상태 `PATCH`로 정의하지 않은 행동을 허용하지 않습니다.

## DB 연결

- 공고의 물리 항목·일정·분류: [공모전 테이블](../database/contests.md)
- 팀·지원·현재 소속·상태 사건: [팀과 지원 테이블](../database/teams.md)
- 선발·취소·멱등성과 잠금: [트랜잭션 설계](../database/transactions.md)
