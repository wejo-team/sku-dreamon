# 공모전과 팀 API

**상태: 설계 제안.** 경로는 `/api/v1` 기준입니다. [OpenAPI 원본](README.md#openapi-source)에 각 요청·응답 schema가 있고, [공통 계약](conventions.md)에 페이지·오류·재시도 규칙이 있습니다.

## 공개 공고와 팀 탐색

| 메서드·경로 | 조건 | 성공 응답 | 정렬·범위 |
| --- | --- | --- | --- |
| `GET /contests` | `q`, `fieldCode`, `sort`, `registrationStatus`, 페이지 | 200 `ContestPage` | 등록순 `createdAt DESC, id DESC`; 마감순 `endsAt ASC, id ASC` |
| `GET /contests/{contestId}` | 공고 UUID | 200 `Contest` | 마감 공고도 상세 조회 가능 |
| `GET /contests/{contestId}/teams` | `q`, `roleCode`, `recruitingOnly`, 페이지 | 200 `TeamPage` | 해당 공고만, `createdAt DESC, id DESC` |
| `GET /teams` | 위 조건·선택 `contestId` | 200 `TeamPage` | 전체 공개 팀의 같은 생성순 |
| `GET /teams/{teamId}` | 팀 UUID | 200 `Team` | 공개 모집글. 지원자·팀 공간 데이터 제외 |

공고·팀 검색 대상과 목록·상세의 정보 구분은 [공고 탐색 명세](../specs/contests.md#exploration-ui), [팀 모집 명세](../specs/team-recruitment.md)를 참조합니다. 존재하지 않는 상세는 404, 잘못된 필터 형식은 422입니다.

`Contest.teamCount`는 연결된 팀 전체 수이고 `TeamPage.pagination.total`은 현재 필터 결과 수입니다. `TeamSummary.isRecruiting`은 서버가 계산한 공통 모집 표시이며, 특정 회원의 신규 지원 성공을 보장하는 값이 아닙니다. 팀의 `fieldCodes`는 연결된 공고에서 조회합니다.

등록된 공고의 기본 목록에서 마감 공고를 어디에 포함·배치할지는 [CONTEST-05](../specs/contests.md#open-questions)가 선행 결정입니다. `registrationStatus`를 명시한 요청의 필터는 정의하지만, 생략했을 때의 제품 기본 포함 범위를 이 설계에서 임의로 확정하지 않습니다.

## 팀 생성과 워크스페이스

| 메서드·경로 | 요청·권한 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `POST /teams` | `TeamCreate`, 로그인 | 첫 생성 201 `Team`, 같은 생성 재전송 200 | 409 공고·정원·소속·코드 충돌, 422 입력 |
| `GET /me/teams` | 본인·페이지 | 200 `WorkspacePage` | 401 인증 |
| `GET /teams/{teamId}/space` | 현재 팀장·확정 팀원 | 200 `TeamSpace` | 403 현재 소속 아님, 404 없음 |
| `PUT /teams/{teamId}/recruitment/closure` | 팀장, `expectedVersion` | 200 `RecruitmentResult` | 403 권한, 409 상태·버전 충돌 |
| `PUT /teams/{teamId}/recruitment/reopening` | 팀장, `expectedVersion` | 200 `RecruitmentResult` | 403 권한, 409 기한·정원·상태·버전 충돌 |

`TeamCreate`는 다음 **전송 항목만** 받습니다. 필수 여부와 조합의 근거는 [팀 생성·공식 정원 정책](../specs/team-recruitment.md#official-capacity)에 있습니다.

| 항목 | 역할 |
| --- | --- |
| `requestId` | 응답 유실 후 같은 생성 요청을 식별하는 UUID |
| `contestId` | 공고 UUID |
| `name`, `introduction` | 팀명·소개/목표 |
| `capacity` | 팀장 포함 목표 정원의 십진 문자열 |
| `roleCodes` | 공통 모집 역할 코드 배열 |
| `recruitmentDeadline` | 입력 날짜 `date`·선택 시각 `time`·선택 시간대 `timeZone` |

서버가 입력 날짜·시각·시간대로 UTC 마감 경계를 계산하고 보완 여부를 함께 저장합니다. 응답의 `recruitmentEndsAt`과 `recruitmentDeadline`은 실제 마감과 서비스 보완 안내에 사용합니다.

공고 분야·개인/팀 유형·주당 시간·팀장 ID는 생성 입력에 없습니다. 소유자는 인증 주체에서 결정합니다. 서버가 정규화한 최초 입력의 지문을 저장하므로 이후 상태가 바뀌어도 같은 `requestId`의 생성 재시도를 신규 행동으로 실행하지 않습니다.

`TeamSpace.members`에는 소속 정보와 권한에 따라 읽을 수 있는 `profile`이 있습니다. 일반 팀원이 비공개 팀원을 보는 경우 `profile=null`로 응답합니다. 지원자 프로필을 볼 수 있는 팀장 관계를 모든 팀원에게 확장하지 않습니다. 권한의 원본은 [팀 공간 접근](../specs/team-recruitment.md#team-workspace-access), [프로필 공개](../specs/profile.md#visibility)입니다.

모집 종료·재개는 명시적인 행동 endpoint입니다. 범용 `PATCH recruitmentState`로 아직 정의하지 않은 `reviewing`·`finalized` 전이를 허용하지 않습니다. 확정된 재개 조건과 후속 미정 상태는 [모집 재개](../specs/team-recruitment.md#recruitment-reopening), [TEAM-02](../specs/team-recruitment.md#open-questions)에 연결합니다.

## 지원과 검토

| 메서드·경로 | 권한·요청 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `POST /teams/{teamId}/applications` | 로그인, `requestId`, `roleCode`, 선택 `message` | 첫 접수 201 `Application`, 같은 요청 재전송 200 | 409 필수 프로필·공개·모집·중복 조건 |
| `GET /me/applications` | 본인, 선택 `status`·페이지 | 200 `MyApplicationPage` | 401 인증 |
| `GET /applications/{applicationId}` | 본인 또는 받은 팀장 | 200 `Application` | 관계 밖·미존재는 404 |
| `PUT /applications/{applicationId}/cancellation` | 본인, `expectedVersion` | 200 `CancellationResult` | 403 권한, 409 지원 상태·버전 충돌 |
| `GET /teams/{teamId}/applicants` | 해당 팀장, 선택 `status`·페이지 | 200 `ApplicantPage` | 403 권한, 404 팀 없음 |
| `GET /applications/{applicationId}/applicant` | 받은 팀장 | 200 `Applicant` | 403 행동 권한, 404 없거나 관계 밖 |
| `PUT /applications/{applicationId}/selection` | 받은 팀장, `expectedVersion` | 200 `SelectionResult` | 409 지원 상태·정원·소속·버전 충돌 |

지원·지원자 목록은 `submittedAt DESC, id DESC`입니다. 조회만으로 지원 상태를 `reviewing`으로 변경하지 않습니다. `Application`과 `Applicant`를 분리해, 지원서를 볼 수 있다는 이유로 모든 요청자가 팀장 검토용 최신 프로필을 받지 않게 합니다.

### 신규 지원

API는 [지원 직전 확인](../specs/profile.md#before-application)과 [현재 모집 조건](../specs/team-recruitment.md#recruitment-conditions)을 서버에서 다시 확인합니다. 공개 전환·프로필 보완 저장은 지원 접수와 별도 요청입니다. 클라이언트가 프로필 공개를 확인했다고 하더라도 그 사이 비공개로 바뀌었으면 409 `PROFILE_PRIVATE`이며 자동 공개하지 않습니다.

취소 후 재지원은 새 `requestId`와 새 지원 ID로 접수합니다. 이전 취소를 취소하거나 이전 소속을 복원하는 요청이 아닙니다. 다른 팀에 이미 소속된 사람의 신규 지원, 미선발·폐기 뒤 재지원, 팀 생성 시 대기 지원의 처리는 [TEAM-04](../specs/team-recruitment.md#open-questions)를 결정한 뒤 해당 분기의 계약을 완성합니다.

### 선발과 취소

선발 요청은 지원 상태 변경·현재 소속 생성·같은 공모전 다른 대기 지원 폐기·각 사건과 알림을 함께 완료합니다. 정확한 처리 경계는 [트랜잭션 설계](../database/transactions.md)에 둡니다. 실패하면 부분 선발이나 부분 폐기를 성공 결과로 반환하지 않습니다.

`SelectionResult`에는 선발한 지원·해당 팀·생성된 소속 ID만 담습니다. 다른 팀 지원의 목록·메시지·건수를 선발 팀장에게 노출하지 않습니다. 폐기 원인 지원의 ID도 그 원인 지원에 대한 열람 권한이 없는 팀장에게는 `null`로 제공합니다.

본인 취소가 성공하면 응답의 `membershipEnded`로 현재 소속 종료 여부를 알 수 있습니다. 응답 유실 시 먼저 현재 지원을 다시 조회합니다. 이미 취소된 지원을 일치하는 현재 버전으로 재요청하면 추가 자리 반환 없이 성공합니다. 이전 버전은 409입니다. 취소와 선발의 충돌은 [취소 정책](../specs/team-recruitment.md#application-cancellation)을 만족하도록 DB에서 조정합니다.

모집 종료 뒤 선발, 미선발 처리, 팀장의 선발 취소, 지원 메시지 수정은 **별도 미정 분기**입니다. 이 API의 `selected`·`rejected` 같은 조회 enum이 그 상태를 만드는 모든 행동을 허용한다는 뜻은 아닙니다.

## DB 연결

- 공고의 물리 항목·일정·분류: [공모전 테이블](../database/contests.md)
- 팀·지원·현재 소속·상태 사건: [팀과 지원 테이블](../database/teams.md)
- 선발·취소·멱등성과 잠금: [트랜잭션 설계](../database/transactions.md)
