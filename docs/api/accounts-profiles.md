# 계정과 프로필 API

**상태: 설계 제안.** 아래 경로에는 `/api/v1` 접두사가 붙습니다. 필드 타입·필수 여부는 [OpenAPI 원본](README.md#openapi-source), 공통 오류·인증 전송의 미정 범위는 [공통 계약](conventions.md)을 참조합니다.

## 계정과 로그인

| 메서드·경로 | 요청 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `POST /accounts` | `Credentials`: `loginId`, `password` | 201 `SignupResult.account` | 409 아이디 중복, 422 입력, 429 제한 |
| `GET /auth/login-id-availability` | query `loginId` | 200 정규화된 아이디·`available` | 422 형식, 429 제한 |
| `POST /auth/login` | `Credentials` | 200 `LoginResult.account` + **미정인 인증 전달 계약** | 401 잘못된 인증정보, 422 입력, 429 제한 |
| `POST /auth/logout` | 본문 없음, 현재 인증 | 204 본문 없음 | 401 인증·만료 |
| `GET /me` | 현재 인증 | 200 `Account` | 401 인증·만료 |

중복 확인은 가입 예약이 아닙니다. 가입 쓰기에서 유일성을 다시 확인하고 계정과 자체 인증 정보를 함께 저장합니다. 아이디 정규화와 비밀번호 처리는 [인증 입력 정책](../specs/authentication.md#login-identifier)에 연결합니다. 로그인 실패는 아이디 존재와 비밀번호 오입력을 구분하지 않는 응답을 제안합니다.

`Account`는 본인 계정 조회 DTO입니다. 다른 사람의 `Profile`과 분리하므로 로그인 아이디가 사람 목록·팀원·AI 카드에 섞이지 않습니다. 가입 성공은 계정 생성 성공만 의미하며 자동 로그인 여부는 [AUTH 미정 사항](../specs/authentication.md#open-questions)의 결정이 필요합니다.

## 본인 프로필 저장

| 메서드·경로 | 요청 | 성공 | 주요 실패 |
| --- | --- | --- | --- |
| `GET /me/profile` | 현재 인증 | 200 `Profile` | 404 아직 저장된 프로필 없음 |
| `PUT /me/profile` | `ProfileWrite`: 전체 편집값·`expectedVersion` | 최초·수정 모두 200 `Profile` | 409 버전·선택지·학사 경로 충돌, 422 입력 |
| `PUT /me/profile/visibility` | `isPublic`, `expectedVersion` | 200 `Profile` | 404 프로필 없음, 409 버전 충돌 |

프로필 편집은 기본 항목·분야·역할·역량·포트폴리오를 한 번에 저장합니다. 공개 전환은 확인 팝업과 연결된 별도 요청으로 분리하여 일반 필드 저장이나 지원 버튼이 공개 상태를 바꾸지 않게 합니다. 입력 가능 항목과 개수의 원본은 [프로필 입력 계약](../specs/profile.md#input-validation), 전환 절차는 [공개 변경 정책](../specs/profile.md#visibility-changes)입니다.

저장 흐름은 다음과 같습니다.

1. 최초 조회가 404이면 편집 폼을 만들고 `expectedVersion="0"`으로 전체 값을 제출합니다. 최초 저장된 프로필의 `version`은 `"1"`, 공개 상태는 비공개입니다.
2. 기존 프로필은 조회한 버전과 편집값을 전송합니다. 서버는 원래 공개 상태를 보존하고 모든 항목을 함께 저장합니다.
3. 성공한 응답의 `Profile`로 화면을 갱신합니다. 409이면 저장되지 않았음을 알리고 최신 프로필을 다시 확인합니다. 클라이언트가 조용히 최신 버전으로 덮어써 재시도하지 않습니다.
4. 공개 전환은 저장된 프로필의 현재 버전으로 별도 요청합니다. 확인 팝업 취소는 요청을 보내지 않습니다.

선택 입력은 `null`, 역량 해제는 `[]`로 보냅니다. 경험 `none` 저장은 이전 본문을 지우고, 작성 본문이 앞뒤 공백 제거 후 비어 있으면 `unspecified`로 저장합니다. `provided` 응답에는 비어 있지 않은 본문이 있어야 합니다. 경험 본문과 학사 선택의 연관 검증은 각각 [경험 입력](../specs/profile.md#experience), [학사 종속값](../specs/academic-structure.md#dependent-selection)을 참조합니다. 비활성화된 기존 학사 경로를 그대로 유지하는 수정과 새 경로를 선택하는 수정을 구분합니다.

## 선택지와 공개 사람 탐색

| 메서드·경로 | 조회 조건 | 성공 | 접근·실패 |
| --- | --- | --- | --- |
| `GET /catalogs` | 없음 | 200 `Catalogs` | 공개 조회. 분류별 `sortOrder`, `code` 순 |
| `GET /catalogs/academic-placements` | 없음 | 200 `AcademicCatalog` | 공개 조회. 부모 경로를 가진 평탄한 목록 |
| `GET /people` | `q`, `fieldCode`, `roleCode`, `page`, `pageSize` | 200 `PersonPage` | 로그인 필요. 현재 공개 범위의 목록·집계 |
| `GET /people/{accountId}` | UUID | 200 `Profile` | 로그인 필요. 비공개·미존재는 동일하게 404 |

카탈로그는 현재 선택값과 기존 데이터의 표시를 같은 코드로 연결합니다. 응답에 비활성 항목도 포함하되 새 선택에는 `isSelectable=true`만 사용합니다. 실제 초기 코드는 [공통 선택지](../specs/profile-options.md#catalog-management)와 [학사 검증](../specs/academic-structure.md#open-questions)을 완료한 뒤 채웁니다.

사람 목록은 `updatedAt DESC, accountId ASC` 정렬을 제안합니다. 검색 대상은 이름·자기소개·분야·역할·역량 표시명이며 필터는 코드로 전달합니다. 공개·미공개 처리의 원본은 [사람 탐색 정책](../specs/profile.md#people-directory)입니다.

지원받은 팀장의 비공개 프로필 열람은 `/people`의 예외 필터가 아닙니다. [지원자 상세 API](contests-teams.md)의 `/applications/{applicationId}/applicant`에서 해당 관계를 확인합니다. 공개 미리보기는 본인의 현재 프로필을 화면에 표시하는 기능이며 실제 공개 전환을 실행하지 않습니다.

## DB 연결

| API 정보 | DB 원본 |
| --- | --- |
| `Account`·로그인 | [계정과 프로필 테이블](../database/identity.md) |
| `Profile`·버전·연결 목록·포트폴리오 | [계정과 프로필 테이블](../database/identity.md) |
| 코드·학사 경로 | [공통 카탈로그](../database/catalogs.md) |

각 API에 세션 토큰·DB 해시·역할 부여 이력을 복제하지 않습니다. 계정 탈퇴·복구·파일 업로드·학교 인증 API는 이 설계에 추가하지 않습니다.
