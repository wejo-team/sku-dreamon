# 지원 API

**상태: 일부 구현.** 본인·받은 팀장의 지원 상세 조회와 본인 취소를 구현했습니다. 신규 지원·목록과 팀장 상태 변경은 아직 설계 단계입니다. 경로는 `/api/v1` 기준이며, 제품 정책은 연결한 기능 명세를 따릅니다.

구현 원본은 [지원 라우터](../../backend/app/routers/applications.py), [응답 DTO](../../backend/app/schemas/applications.py), [조회 쿼리](../../backend/app/queries/applications.py)입니다. [PostgreSQL HTTP 검사](../../backend/tests/integration/test_application_reads.py)는 실제 세션 쿠키의 권한·404 은닉·폐기 원인 공개 범위·조회 시 상태 보존을 검증합니다. 실행 앱의 `/docs`·`/openapi.json`에서 등록한 API 계약을 확인할 수 있습니다.

취소는 [계정·공고·팀·지원 잠금](../../backend/app/services/recruitment_locks.py)을 공유합니다. [취소 통합 검사](../../backend/tests/integration/test_application_cancellation.py)는 버전 우선 비교·변경 없는 재요청·선발 소속 종료·모집 상태 유지·알림 실패 시 전체 롤백·독립 연결의 동시 취소를 검증합니다.

- 먼저 [API 목록](#endpoints)에서 경로·권한·성공 응답을 찾습니다.

- 입력은 [검색 조건](#queries)과 [요청 본문](#requests), 출력은 [지원 데이터](#application) 표에서 확인합니다.

- ID·코드·시각·정원·버전은 [공통 타입](conventions.md#types), 실패는 [공통 오류](conventions.md#errors)를 사용합니다. 단건·복합 성공은 [Success&lt;T&gt;](conventions.md#success-responses), 목록은 [Page&lt;T&gt;](conventions.md#pagination)를 사용하며 `Page<T>`는 `data: T[]`와 `pagination`을 가진 응답입니다.

**표 읽기:** 응답 DTO 표는 `data` 내부에서 사용하는 데이터 구조를 정의하며, 각 DTO의 모든 필드는 필수입니다. `null` 허용 여부는 타입에 따로 표시하며, `null`인 필드를 생략하지 않습니다. 요청은 각 표에 필수 여부를 표시합니다. 선언하지 않은 요청 필드는 422입니다. 일반 텍스트의 정책상 글자 수와 Unicode 계수 단위의 미정 사항은 [공통 계약](conventions.md)을 따릅니다.

<a id="endpoints"></a>

## API 목록

아래 모든 작업에 입력 형식 오류 **422**, 일시 장애 **503**, 내부 오류 **500**이 공통 적용됩니다. 로그인 또는 관계 권한이 필요한 작업에는 **401**, 상태 변경 요청에는 [공통 CSRF 검사 실패의 403](conventions.md#session-auth)도 적용됩니다. 표의 실패 열은 그 밖의 응답을 나타냅니다. 실패 본문 형식은 [공통 오류 계약](conventions.md)에 있습니다.

| 메서드·경로 | 권한·입력 | 성공 응답 | 추가 실패 |
| --- | --- | --- | --- |
| `POST /teams/{teamId}/applications` | 로그인, 팀 UUID·`ApplicationCreate` | 첫 접수 201 `Success<Application>`, 동일 요청 재전송 200 `Success<Application>` | 404 팀 없음, 409 프로필·모집·중복·재지원·소속·코드·요청 ID 충돌 |
| `GET /me/applications` | 본인, 페이지 조건·선택 `status` | 200 `Page<MyApplication>` | — |
| `GET /applications/{applicationId}` | 지원 본인 또는 받은 팀장, 지원 UUID | 200 `Success<Application>` | 404 없음 또는 관계 밖 |
| `PUT /applications/{applicationId}/cancellation` | 지원 본인, 지원 UUID·`VersionedAction` | 200 `Success<CancellationResult>` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `GET /teams/{teamId}/applicants` | 해당 팀장, 팀 UUID·페이지 조건·선택 `status` | 200 `Page<Applicant>` | 403 권한, 404 팀 없음 |
| `GET /applications/{applicationId}/applicant` | 받은 팀장, 지원 UUID | 200 `Success<Applicant>` | 403 행동 권한, 404 없음 또는 관계 밖 |
| `PUT /applications/{applicationId}/review-start` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `Success<Application>` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `PUT /applications/{applicationId}/rejection` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `Success<Application>` | 403 행동 권한, 404 없음 또는 관계 밖, 409 상태·버전 충돌 |
| `PUT /applications/{applicationId}/selection` | 받은 팀장, 지원 UUID·`VersionedAction` | 200 `Success<SelectionResult>` | 403 행동 권한, 404 없음 또는 관계 밖, 409 공고 기한·상태·정원·소속·버전 충돌 |

다른 팀·일반 팀원·일반 사용자는 지원서 존재를 확인할 수 없도록 404로 처리합니다. 존재를 확인할 수 있는 관계라도 해당 행동을 수행할 권한이 없으면 403입니다. 목록·상세·AI 결과 조회만으로 지원 상태를 `reviewing`으로 변경하지 않으며, 팀장이 검토 시작 API를 명시적으로 실행해야 합니다. 검토 시작은 선발·미선발의 필수 선행 작업이 아닙니다.

팀 생성·모집·현재 소속 조회는 [팀 API](teams.md#endpoints), 지원자 AI 검토는 [AI API](ai.md#applicant-endpoints)에 정의합니다.

<a id="queries"></a>

## 검색 조건과 정렬

경로 변수 `teamId`, `applicationId`는 해당 경로에서 모두 필수 `Id`입니다. 목록의 아래 query는 모두 선택 입력입니다.

| query | 타입·기본값 | 적용 범위·의미 |
| --- | --- | --- |
| `page`, `pageSize` | 정수, 기본 1·20, 페이지 크기 최대 100 | 모든 페이지 목록. 범위·마지막 페이지 보정은 [공통 계약](conventions.md) |
| `status` | `ApplicationStatus`, 생략 시 모든 상태 | 내 지원·팀장 지원자 목록 |

| 목록 | 검색 대상 | 안정 정렬 |
| --- | --- | --- |
| 내 지원·팀장 지원자 | 검색어 없음, 지원 시도별 목록 | 지원의 `submittedAt DESC, id DESC` |

<a id="values"></a>

## 지원 상태값

| 타입 | 값과 의미 |
| --- | --- |
| `ApplicationStatus` | `submitted` 지원 완료, `reviewing` 검토 중, `selected` 선발, `rejected` 미선발, `canceled` 취소, `discarded` 폐기 |

실제 전이는 [지원 상태 정책](../specs/team-recruitment.md#application-transitions)을 따릅니다. 팀의 모집 상태는 [팀 API](teams.md#values)에 정의합니다.

<a id="requests"></a>

## 요청 본문

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

검토 시작·미선발·선발·취소에는 **지원의 버전**을 [VersionedAction](conventions.md#versioned-action)의 필수 `expectedVersion`으로 보냅니다. 구현한 취소 본문은 [VersionedAction DTO](../../backend/app/schemas/applications.py)가 정의합니다. 모집 종료·재개는 [팀 API](teams.md#requests)의 버전을 사용합니다.

```json
{ "expectedVersion": "3" }
```

<a id="application"></a>

## 지원과 처리 결과 응답

### Application — 지원서

필드·타입·필수 여부는 [ApplicationResponse](../../backend/app/schemas/applications.py)와 생성 OpenAPI를 따릅니다. `id`는 접수 시도마다 새로 발급하고 `updatedAt`은 마지막 상태 변경 시각입니다. 폐기 사유는 `selected_elsewhere`·`team_created_elsewhere`이며 폐기 외 상태에서는 null입니다.

`Application`에는 프로필을 포함하지 않습니다. 지원서 열람 권한만으로 모든 조회자에게 팀장 검토용 최신 전체 프로필을 제공하지 않습니다. 폐기 원인 ID 두 필드는 동시에 값을 갖지 않습니다. 받은 팀장에게도 폐기 사유는 제공하지만 다른 팀·지원의 원인 ID는 제공하지 않습니다. 팀 생성 폐기의 원인 팀은 DB에 기록한 팀장 소속에서 조회하며 가상의 선발 지원 ID를 만들지 않습니다.

<a id="my-application"></a>

### MyApplication — 내 지원 목록 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `application` | `Application` | 본인 지원 시도 |
| `team` | [TeamSummary](teams.md#team-summary) | 지원한 팀 요약 |
| `isCurrentMember` | boolean | 현재 해당 팀 소속인지 여부 |

취소·폐기된 이전 시도와 신규 지원을 구분합니다. 과거 지원의 보존 기간은 별도 미정입니다.

<a id="applicant"></a>

### Applicant — 팀장 검토 항목

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `application` | `Application` | 받은 지원서 |
| `profile` | [Profile](profiles.md#profile) | 해당 지원자의 최신 전체 프로필. `version`과 시연 데이터 여부인 `isDemo` 포함 |
| `isSelectionCandidate` | boolean | 현재 지원이 `submitted`·`reviewing`이고 같은 공모전의 확정 소속이 없는지. 마감·정원까지 검증한 실제 선발 실행 허가는 아님 |

지원 후 비공개 전환, 취소·미선발·폐기 이후에도 받은 팀장의 [최신 프로필 열람 관계](../specs/profile.md#application-profile)를 유지합니다. 새 후보 여부와 기존 AI 검토 가능 여부는 다르며, 이 관계를 일반 사람 검색에 확대하지 않습니다.

<a id="action-results"></a>

### 처리 결과

| 응답 타입 | 필수 필드 | 의미 |
| --- | --- | --- |
| `SelectionResult` | `application: Application`, `team: TeamSummary`, `membershipId: Id` | 선발한 지원·해당 팀·생성된 현재 소속. 다른 팀 지원 목록·메시지·건수는 포함하지 않음 |
| `CancellationResult` | `application: Application`, `membershipEnded: boolean` | 선발 후 취소로 소속을 종료했다면 true. 이미 취소된 요청은 기존 취소 결과를 유지하며 자리를 다시 반환하지 않음 |

구현된 취소 응답의 필드·타입은 [CancellationResult DTO](../../backend/app/schemas/applications.py)와 생성 OpenAPI를 기준으로 합니다.

`team: TeamSummary`의 데이터 정의는 [팀 요약](teams.md#team-summary)을 따릅니다. 모집 종료·재개의 `RecruitmentResult`는 [팀 API](teams.md#action-results)에 정의합니다.

<a id="transitions"></a>

## 상태 변경·충돌·재시도

### 생성 요청의 재전송

지원 생성에서 서버는 인증 주체·경로·정규화한 최초 입력으로 같은 시도를 판별합니다. 첫 생성은 201, 같은 `requestId`와 같은 입력의 재전송은 기존 리소스를 200으로 반환합니다. 같은 ID의 다른 입력은 409 `REQUEST_ID_REUSED`입니다. 이후 지원의 상태가 바뀌어도 과거 생성 재시도를 새 행동으로 실행하지 않습니다.

취소·폐기 후에는 같은 공모전에 현재 소속이 없고 현재 모집·프로필 조건을 충족하면 새 `requestId`·새 지원 ID로 접수합니다. 미선발 이력이 있는 같은 팀에는 재지원할 수 없고, 다른 팀에는 현재 조건을 충족하면 지원할 수 있습니다. `rejected`·`canceled`·`discarded` 기록은 복원하거나 다른 상태로 바꾸지 않습니다. 이전 시도에 대한 늦은 요청은 새 시도를 변경하지 않습니다. 근거는 [재지원](../specs/team-recruitment.md#reapplication)과 [소속 확정 시 다른 대기 지원 폐기](../specs/team-recruitment.md#parallel-applications)입니다.

팀 생성의 재전송과 다른 대기 지원 폐기는 [팀 API](teams.md#transitions)에 정의합니다.

### 버전이 있는 행동

행동 권한·열람 관계를 확인하고 대상을 잠근 뒤, 대상 버전과 `expectedVersion`을 **상태 전이 판단보다 먼저 비교**합니다. 다르면 현재 상태가 요청 결과와 같아도 409 `VERSION_CONFLICT`입니다. 아래 재요청 성공은 일치하는 현재 버전이 전제입니다.

| 행동 | 허용된 전이·재요청 | 성공 시 함께 처리하는 것 |
| --- | --- | --- |
| 검토 시작 | `submitted` → `reviewing`. 이미 `reviewing`이면 no-op 200 | 해당 지원 버전·사건·본인 알림만 갱신. 팀 모집 상태·정원은 유지 |
| 미선발 | `submitted`·`reviewing` → `rejected`. 이미 `rejected`이면 no-op 200 | 해당 지원 버전·사건·본인 알림 갱신. 소속·정원은 유지 |
| 선발 | `submitted`·`reviewing` → `selected`. 이미 `selected`이며 동일한 현재 소속이면 no-op 200 | 현재 소속 생성, 같은 공모전 다른 대기 지원 폐기, 사건·알림. 정원 충족 시 모집 마감 |
| 본인 취소 | `submitted`·`reviewing`·`selected` → `canceled`. 이미 `canceled`이면 no-op 200 | 선발 후 취소는 소속 종료·자리 반환·사건·알림. 자동 모집 재개·폐기 지원 복원 없음 |

미선발은 팀장의 명시적 요청에서만 실행하며 모집 종료·기한 경과·정원 충족으로 자동 실행하지 않습니다. `rejected`·`canceled`·`discarded`에서 다른 상태로 가는 요청은 `INVALID_APPLICATION_STATE`이며, 표의 동일 상태 no-op은 상태 복원이 아닙니다. no-op은 버전·사건·알림을 추가하지 않습니다.

실제로 `submitted`·`reviewing`을 선발하려면 현재 공고 접수 기간 안이고 여석·무소속·팀장 권한을 충족해야 합니다. 선발 검사는 신규 접수용 `isRecruiting`과 독립적이며, 팀의 저장 상태가 `closed`이거나 팀 모집 기한이 지났어도 기존 유효 지원은 선발할 수 있습니다. `현재 시각 >= 공고 endsAt`이면 실제 선발을 `CONTEST_NOT_OPEN`으로 거부합니다. 이미 선발된 동일 소속에 대한 버전 일치 no-op은 새 선발이 아니므로 이후 공고 마감만으로 실패시키지 않습니다. 정책 원본은 [기존 지원 선발 가능 기간](../specs/team-recruitment.md#selection-window)입니다.

팀 생성에 따른 폐기, 검토 시작·미선발·선발·취소의 지원 상태·소속·사건·알림 변경은 해당 유스케이스의 [동일 트랜잭션](../database/transactions.md)에서 처리합니다. 실패하면 부분 선발·부분 폐기를 성공 결과로 반환하지 않습니다. 응답 유실 후에는 현재 리소스를 다시 조회해 결과와 버전을 확인합니다.

### 409 업무 오류

| 요청 | 정의한 오류 코드 |
| --- | --- |
| 신규 지원 | `PROFILE_REQUIRED`, `PROFILE_PRIVATE`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `RECRUITMENT_CLOSED`, `RECRUITMENT_DEADLINE_PASSED`, `DUPLICATE_APPLICATION`, `REAPPLICATION_NOT_ALLOWED`, `MEMBERSHIP_CONFLICT`, `INVALID_CATALOG_SELECTION`, `REQUEST_ID_REUSED` |
| 검토 시작·미선발 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE` |
| 선발 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE`, `CONTEST_NOT_OPEN`, `TEAM_FULL`, `MEMBERSHIP_CONFLICT` |
| 본인 취소 | `VERSION_CONFLICT`, `INVALID_APPLICATION_STATE` |

공개 전환을 화면에서 확인했더라도 지원 직전 비공개로 바뀌었다면 `PROFILE_PRIVATE`입니다. 현재 유효 지원의 중복은 `DUPLICATE_APPLICATION`, 대상 팀의 미선발 이력에 따른 재지원 거부는 `REAPPLICATION_NOT_ALLOWED`, 같은 공모전의 현재 소속 충돌은 `MEMBERSHIP_CONFLICT`입니다. 다른 팀의 지원 목록이나 건수를 오류 세부사항에 포함하지 않습니다.

<a id="scope-boundaries"></a>

팀장 선발 취소·강퇴·팀장 탈퇴·팀 삭제와 별도 소속 탈퇴 API는 [MVP 범위 밖](../specs/team-recruitment.md#membership-exclusions)입니다. 본인의 선발 후 지원 취소는 위 계약을 유지합니다. [팀 모집 정보](teams.md#requests) 편집과 제출 후 지원 메시지 수정은 [미정 사항](../specs/team-recruitment.md#open-questions)이며 범용 상태 `PATCH`로 정의하지 않은 행동을 허용하지 않습니다.

## DB 연결

- 팀·지원·현재 소속·상태 사건: [팀과 지원 테이블](../database/teams.md)
- 선발·취소·멱등성과 잠금: [트랜잭션 설계](../database/transactions.md)
