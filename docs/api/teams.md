# 팀 API

**상태: 공개 팀 조회 구현 · 생성·워크스페이스 설계.** 공개 팀 목록·상세·공고 하위 팀 목록의 [라우터](../../backend/app/routers/teams.py), [요청·응답 DTO](../../backend/app/schemas/teams.py), [조회 서비스](../../backend/app/services/teams.py)와 [저장 조회](../../backend/app/repositories/teams.py)를 구현했습니다. 생성·모집 변경·워크스페이스 API는 아래 설계 대상으로 남습니다. 경로는 `/api/v1` 기준이며, 제품 정책은 연결한 기능 명세를 따릅니다.

- 먼저 [API 목록](#endpoints)에서 경로·권한·성공 응답을 찾습니다.

- 입력은 [검색 조건](#queries)과 [요청 본문](#requests), 출력은 [팀 데이터](#team-summary)의 코드와 남은 설계 표에서 확인합니다.

- ID·코드·시각·정원·버전은 [공통 타입](conventions.md#types), 실패는 [공통 오류](conventions.md#errors)를 사용합니다. 단건·복합 성공은 [Success&lt;T&gt;](conventions.md#success-responses), 목록은 [Page&lt;T&gt;](conventions.md#pagination)를 사용하며 `Page<T>`는 `data: T[]`와 `pagination`을 가진 응답입니다.

**표 읽기:** 응답 DTO 표는 `data` 내부에서 사용하는 데이터 구조를 정의하며, 각 DTO의 모든 필드는 필수입니다. `null` 허용 여부는 타입에 따로 표시하며, `null`인 필드를 생략하지 않습니다. 요청은 각 표에 필수 여부를 표시합니다. 선언하지 않은 요청 필드는 422입니다. 일반 텍스트의 정책상 글자 수와 Unicode 계수 단위의 미정 사항은 [공통 계약](conventions.md)을 따릅니다.

<a id="endpoints"></a>

## API 목록

아래 모든 작업에 입력 형식 오류 **422**, 일시 장애 **503**, 내부 오류 **500**이 공통 적용됩니다. 로그인 또는 관계 권한이 필요한 작업에는 **401**, 상태 변경 요청에는 [공통 CSRF 검사 실패의 403](conventions.md#session-auth)도 적용됩니다. 표의 실패 열은 그 밖의 응답을 나타냅니다. 실패 본문 형식은 [공통 오류 계약](conventions.md)에 있습니다.

### 공개 팀 탐색

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /contests/{contestId}/teams` | 공개, 공고 UUID·팀 검색 조건 | 200 `Page<TeamSummary>` | 404 공고 없음 |
| `GET /teams` | 공개, 팀 검색 조건·선택 `contestId` | 200 `Page<TeamSummary>` | — |
| `GET /teams/{teamId}` | 공개, 팀 UUID | 200 `Success<TeamDetail>` | 404 팀 없음 |

공개 팀 응답에는 지원서·지원자 프로필·팀 공간 데이터를 포함하지 않습니다. 화면별 정보 구분은 [공고 탐색](../specs/contests.md#exploration-ui)과 [팀 모집 명세](../specs/team-recruitment.md)를 따릅니다. 공모전 목록·상세 조회는 [공모전 API](contests.md#endpoints)에 정의합니다.

### 팀 생성과 워크스페이스

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /teams` | 로그인, `TeamCreate` | 첫 생성 201 `Success<Team>`, 동일 요청 재전송 200 `Success<Team>` | 404 공고 없음, 409 공고·정원·소속·코드·요청 ID 충돌 |
| `GET /me/teams` | 본인, 페이지 조건 | 200 `Page<WorkspaceTeam>` | — |
| `GET /teams/{teamId}/space` | 현재 팀장·확정 팀원, 팀 UUID | 200 `Success<TeamSpace>` | 403 현재 소속 아님, 404 팀 없음 |
| `PUT /teams/{teamId}/recruitment/closure` | 해당 팀장, 팀 UUID·`VersionedAction` | 200 `Success<RecruitmentResult>` | 403 권한, 404 팀 없음, 409 상태·버전 충돌 |
| `PUT /teams/{teamId}/recruitment/reopening` | 해당 팀장, 팀 UUID·`VersionedAction` | 200 `Success<RecruitmentResult>` | 403 권한, 404 팀 없음, 409 기한·정원·상태·버전 충돌 |

`GET /me/teams`는 현재 팀장·확정 팀원인 팀만 반환합니다. 대기 지원은 [내 지원 목록](applications.md#endpoints)에서 조회합니다. 팀 공간과 최신 프로필의 열람 범위는 [팀원 데이터](#team-member)에 정의합니다.

<a id="queries"></a>

## 검색 조건과 정렬

경로 변수 `contestId`, `teamId`는 해당 경로에서 모두 필수 `Id`입니다. 목록의 아래 query는 모두 선택 입력입니다.

공개 조회의 정확한 query 이름·타입·기본값은 [TeamSearch·AllTeamSearch](../../backend/app/schemas/teams.py)와 서버의 `/docs`, `/openapi.json`에서 확인합니다. 페이지는 기본 1·20, 크기는 최대 100이며 마지막 페이지 보정은 [공통 계약](conventions.md)을 따릅니다. `roleCode`는 모집 역할 일치, `recruitingOnly`는 현재 공통 모집 가능 조건으로 제한합니다. `contestId`는 전체 팀 경로에서만 받습니다.

검색어는 앞뒤 공백을 제거하고 빈 값이면 검색하지 않습니다. `%`·`_`는 와일드카드가 아닌 문자로 검색합니다. 목록과 총원·페이지 보정·현재 인원은 같은 SQL 스냅샷에서 계산합니다.

| 목록 | 검색 대상 | 안정 정렬 |
| --- | --- | --- |
| 특정 공모전의 팀 | 팀명·소개/목표·모집 역할 표시명 | `createdAt DESC, id DESC` |
| 전체 팀 | 팀명·소개/목표·모집 역할 표시명·공모전명 | `createdAt DESC, id DESC` |
| 내 팀 | 검색어 없음, 현재 소속만 | 소속의 `joinedAt DESC, membershipId DESC` |

`TeamSummary.isRecruiting`은 서버가 계산한 공통 모집 표시로, 특정 회원의 신규 지원 성공을 보장하지 않습니다.

<a id="values"></a>

## 팀 모집 상태값

| 타입 | 값과 의미 |
| --- | --- |
| `RecruitmentState` | `open` 모집 중, `closed` 모집 마감 |

팀 모집은 두 상태만 사용하며 검토는 [개별 지원 상태](applications.md#values)입니다. 팀의 `open`은 저장 상태이고, `isRecruiting`은 그 상태와 현재 공고·팀 기한·잔여 정원을 함께 평가한 신규 접수 가능 표시입니다. 기한 경과 시 `recruitmentState="open"`이면서 `isRecruiting=false`일 수 있으며, 화면의 모집 배지·버튼은 실제 접수 불가를 모집 마감으로 표시합니다. 기한이 지났다고 저장 상태를 자동으로 `closed`로 바꾸는 작업을 전제하지 않습니다. 실제 전이는 [모집 상태 정책](../specs/team-recruitment.md#team-state-transitions)과 [지원 상태 정책](../specs/team-recruitment.md#application-transitions)을 따릅니다.

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

### 상태 변경 본문

모집 종료·재개에는 **팀의 버전**을 [VersionedAction](conventions.md#versioned-action)의 필수 `expectedVersion`으로 보냅니다. 지원 상태 변경은 [지원 API](applications.md#requests)의 버전을 사용합니다.

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

<a id="team-summary"></a>

## 팀과 워크스페이스 응답

### TeamSummary — 팀 목록

정확한 필드는 [TeamSummary](../../backend/app/schemas/teams.py)와 생성 OpenAPI를 따릅니다. `memberCount`는 종료되지 않은 실제 소속을 팀장 포함 집계하고, `fieldCodes`는 현재 공고의 분야입니다. `isDemo`는 [승인된 시연 목록](../../backend/app/core/demo_data.py)을 조회합니다.

`isRecruiting`은 저장 상태 `open`, 공고 접수 시작 이상·마감 미만, 팀 마감 미만, 잔여 정원을 모두 만족할 때만 참입니다. 저장 상태가 열려 있어도 기한이 지나거나 정원이 찼으면 거짓이며, 특정 회원의 신규 지원 성공을 보장하지 않습니다. 종료·정원 충족·접수 예정 팀도 공개 조회할 수 있습니다.

<a id="team"></a>

### TeamDetail — 공개 모집글

[TeamDetail](../../backend/app/schemas/teams.py)은 `TeamSummary`에 현재 팀장 계정과 연결 공고의 [ContestSummary](contests.md#contest-summary)를 추가합니다. 공고 요약의 `teamCount`는 모집 가능 여부와 무관한 연결 팀 전체 수입니다. 지원서·지원자 프로필·팀 공간의 비공개 데이터는 포함하지 않습니다.

<a id="team-member"></a>

### TeamMember — 현재 팀원의 소속 표시

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `membershipId` | `Id` | 현재 소속 식별자 |
| `accountId` | `Id` | 소속 계정 식별자 |
| `realName` | string | 현재 같은 팀 구성원을 식별하는 실명 |
| `isDemo` | boolean | 계정용 고정 UUID 시드 목록에 `accountId`가 포함되는지 서버에서 판정. 전체 프로필 열람 여부와 별개로 팀원 시연 표시 제공 |
| `membershipRole` | `leader` 또는 `member` | 팀장/팀원 구분 |
| `roleCode` | `CatalogCode` 또는 null | 선발된 지원 역할. 지원을 통해 생성되지 않은 팀장 소속은 null |
| `joinedAt` | `Timestamp` | 소속 시작 시각 |
| `profile` | [Profile](profiles.md#profile) 또는 null | 전체 현재 프로필. 본인·공개 프로필·지원받은 팀장 권한에서만 제공 |

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

지원자 내용은 별도의 [팀장 지원자 API](applications.md#endpoints)로 조회합니다. 팀 공간에 일반 팀원의 지원자 관리 권한을 추가하지 않습니다.

<a id="workspace-team"></a>

### WorkspaceTeam — 내 팀 목록 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `team` | `TeamSummary` | 현재 소속 팀 요약 |
| `membershipId` | `Id` | 본인 현재 소속 식별자 |
| `membershipRole` | `leader` 또는 `member` | 본인 소속 역할 |
| `roleCode` | `CatalogCode` 또는 null | 본인 선발 역할. 팀장 소속은 null |
| `pendingApplicationCount` | integer 또는 null | 팀장에게만 대기 지원 수, 일반 팀원에게 null. 범위는 `TeamSpace`와 같음 |

<a id="action-results"></a>

### 모집 처리 결과

| 응답 타입 | 필수 필드 | 의미 |
| --- | --- | --- |
| `RecruitmentResult` | `team: TeamSummary` | 모집 종료·재개 후 팀의 현재 상태와 버전 |

<a id="transitions"></a>

## 상태 변경·충돌·재시도

### 생성 요청의 재전송

팀 생성에서 서버는 인증 주체·경로·정규화한 최초 입력으로 같은 시도를 판별합니다. 첫 생성은 201, 같은 `requestId`와 같은 입력의 재전송은 기존 리소스를 200으로 반환합니다. 같은 ID의 다른 입력은 409 `REQUEST_ID_REUSED`입니다. 이후 팀의 상태가 바뀌어도 과거 생성 재시도를 새 행동으로 실행하지 않습니다.

팀 생성의 프로필 완성 요구는 [PROFILE-03](../specs/profile.md#open-questions)에 남깁니다. 지원의 생성·재지원은 [지원 API의 재시도 계약](applications.md#transitions)을 따릅니다.

### 버전이 있는 행동

행동 권한·열람 관계를 확인하고 대상을 잠근 뒤, 대상 버전과 `expectedVersion`을 **상태 전이 판단보다 먼저 비교**합니다. 다르면 현재 상태가 요청 결과와 같아도 409 `VERSION_CONFLICT`입니다. 아래 재요청 성공은 일치하는 현재 버전이 전제입니다.

| 행동 | 허용된 전이·재요청 | 성공 시 함께 처리하는 것 |
| --- | --- | --- |
| 모집 종료 | `open` → `closed`, 사유 `leader_closed`. 이미 `closed`이면 사유를 보존하고 no-op 200 | 기존 지원·소속 유지. 대기 지원을 자동 미선발 처리하지 않음 |
| 모집 재개 | `closed` → `open`, 마감 사유 null. 이미 `open`이며 현재 모집 가능하면 no-op 200 | 현재 공고 접수·팀 모집 기한·잔여 정원 확인. 폐기 지원 복원 없음 |

no-op은 버전·사건·알림을 추가하지 않습니다. 팀 생성에 따른 다른 대기 지원 폐기의 원자성은 [팀 생성 본문](#team-create)과 [지원 상태 변경](applications.md#transitions)에 정의합니다. 응답 유실 후에는 현재 리소스를 다시 조회해 결과와 버전을 확인합니다.

### 409 업무 오류

| 요청 | 정의한 오류 코드 |
| --- | --- |
| 팀 생성 | `CONTEST_NOT_OPEN`, `CAPACITY_OUT_OF_RANGE`, `MEMBERSHIP_CONFLICT`, `INVALID_CATALOG_SELECTION`, `REQUEST_ID_REUSED` |
| 모집 종료 | `VERSION_CONFLICT`, `INVALID_RECRUITMENT_STATE` |
| 모집 재개 | `VERSION_CONFLICT`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `RECRUITMENT_DEADLINE_PASSED`, `INVALID_RECRUITMENT_STATE` |

다른 팀의 지원 목록이나 건수를 오류 세부사항에 포함하지 않습니다.

팀장 탈퇴·팀 삭제 등을 포함한 [MVP 제외 동작과 편집 미정 범위](applications.md#scope-boundaries)는 상태 변경 API로 확장하지 않습니다.

## DB 연결

- 팀·지원·현재 소속·상태 사건: [팀과 지원 테이블](../database/teams.md)
- 선발·취소·멱등성과 잠금: [트랜잭션 설계](../database/transactions.md)
