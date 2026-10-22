# 선택지 API

**상태: 설계 제안 · 미구현.** 공통 선택지와 학사 목록을 조회하는 2개 공개 API를 정의합니다. 경로에는 `/api/v1` 접두사가 붙습니다. JSON 표기와 타입은 [공통 타입](conventions.md#types), 실패 응답은 [오류 계약](conventions.md#errors)을 따릅니다.

| 확인할 내용 | 위치 |
| --- | --- |
| 공통 선택지·학사 목록 조회 | [API 목록](#catalog-endpoints) |
| 공통 선택지 필드 | [CatalogItem·AvatarPreset](#catalog-item), [Catalogs](#catalogs) |
| 학사 계층·프로필 연결 | [AcademicUnit](#academic-unit) |

모든 객체는 아래에 정의된 필드만 사용합니다. **본문의 필드는 별도 표시가 없으면 모두 필수**이며, `null` 허용과 필드 생략 허용은 다릅니다. 읽기 전용 필드·선언하지 않은 필드·snake_case를 쓰기 본문으로 보내면 422입니다. 아래 오류 표 외에 모든 API는 공통 `500 INTERNAL_ERROR`, `503 TEMPORARY_UNAVAILABLE`를 사용하며, 상태 변경 요청에는 [공통 CSRF 보호와 실패 응답](conventions.md#session-auth)이 적용됩니다.

성공 응답의 본문은 [공통 성공 응답](conventions.md#success-responses)을 따르며, 아래 응답 DTO 표는 `data` 안의 값과 하위 객체를 정의합니다.

<a id="catalog-endpoints"></a>

## 선택지와 학사 목록

| 메서드·경로 | 접근 | 입력 | 성공 | 오류 |
| --- | --- | --- | --- | --- |
| `GET /catalogs` | 공개 | 없음 | 200 [Success&lt;Catalogs&gt;](#catalogs) | 공통 500·503 |
| `GET /catalogs/academic-units` | 공개 | 없음 | 200 [Success&lt;AcademicUnit[]&gt;](#academic-unit) | 공통 500·503 |

<a id="catalog-item"></a>

## 선택지 응답 필드

### CatalogItem과 AvatarPreset

| 필드 | 타입 | null | 의미 |
| --- | --- | --- | --- |
| `code` | CatalogCode | 불가 | 목록 내 불변 코드 |
| `displayName` | string | 불가 | 화면 표시명 |
| `isSelectable` | boolean | 불가 | 현재 새 선택 가능 여부 |
| `sortOrder` | integer (int32) | 불가 | 목록 정렬값 |

`CatalogItem`은 위 네 필드입니다. `AvatarPreset`은 위 네 필드와 **필수 `assetUrl: HttpUrl`**을 포함하며 `assetUrl`은 `null`을 허용하지 않습니다. 프로필 이미지 코드는 서버의 `ProfileImageCode` enum으로, 제공 이미지 경로는 같은 [공통 정의](../database/catalogs.md#code-enums)의 메타데이터로 관리합니다. 별도 파일 업로드 요청은 추가하지 않습니다.

<a id="catalogs"></a>

### Catalogs — 전체 공통 선택지

| 필드 | 타입 | 제공 목록 |
| --- | --- | --- |
| `fields` | CatalogItem[] | 관심·공모전 분야 |
| `roles` | CatalogItem[] | 희망·모집 역할 |
| `skills` | CatalogItem[] | 보유 역량 |
| `academicStatuses` | CatalogItem[] | 학적 상태 |
| `grades` | CatalogItem[] | 학년 |
| `weeklyAvailabilityRanges` | CatalogItem[] | 주당 참여 가능 시간 |
| `avatarPresets` | AvatarPreset[] | 프로필 이미지 선택지 |

`GET /catalogs`는 DB 코드 테이블 조회 없이 서버의 [공통 enum과 메타데이터](../database/catalogs.md#code-enums)에서 위 일곱 목록을 구성합니다. 프로필·공고·팀·지원의 코드 검증도 같은 정의를 사용하며, 클라이언트는 별도 선택지 목록을 하드코딩하지 않습니다.

일곱 목록은 모두 필수이며 `null`을 허용하지 않습니다. 각 목록은 `sortOrder ASC, code ASC`로 정렬합니다. 현재 선택 가능 항목과 기존 데이터의 표시를 위한 비활성 항목을 함께 제공합니다. 새 선택에는 `isSelectable=true`만 사용합니다. 코드·표시명·정렬·선택 가능 여부 변경은 서버 코드 수정·배포로 반영하고 실제 코드 사전은 [카탈로그 관리](../specs/profile-options.md#catalog-management)에서 검토합니다. 학사 경로 목록은 별도 DB 조회를 유지합니다.

<a id="academic-placement"></a>
<a id="academic-unit"></a>

### AcademicUnit — 학사 계층

`GET /catalogs/academic-units` 응답의 **필수 `data: AcademicUnit[]`**는 `null`을 허용하지 않으며, 빈 목록은 `[]`입니다. 현행·비활성 항목을 부모와 함께 모두 반환합니다. 서버는 DB의 숫자 ID인 `academic_units.academic_unit_id ASC`로 정렬하고 응답의 `id`에 십진 문자열로 매핑합니다. 이 순서는 학교의 공식 표시 순서를 뜻하지 않습니다.

| AcademicUnit 필드 | 타입 | null | 의미·허용값 |
| --- | --- | --- | --- |
| `id` | PositiveBigInt | 불가 | DB가 발급한 증가형 학사 ID. JSON에서는 예: `"3"` |
| `name` | string | 불가 | 비어 있지 않은 이름, 최대 100자. 항목 식별에 사용하지 않음 |
| `parentId` | PositiveBigInt | 허용 | 부모 항목 ID. 단과대학 루트는 `null` |
| `isSelectable` | boolean | 불가 | 해당 항목의 신규 선택 가능 여부. 상위 항목도 함께 확인 |

`id`·`parentId`는 UUID나 JSON 숫자가 아닙니다. 클라이언트는 ID를 문자열로 유지하고 `parentId`로 트리를 구성합니다. 루트는 단과대학, 그 아래는 학부·학과, 다음은 전공이며 종류·별도 코드·중복 경로 ID를 응답하지 않습니다. 비활성 항목은 기존 프로필 표시용으로 유지하고 새 선택에서 제외합니다.

#### 선택과 프로필 저장 흐름

1. 클라이언트가 학사 목록과 본인 프로필을 조회하고, `parentId=null`인 대학부터 하위 항목을 표시합니다. 선택한 항목과 조상이 모두 선택 가능한 경우에만 신규 선택으로 제공합니다.
2. 사용자가 상위 항목을 바꾸면 새 부모 관계에서 유효하지 않은 하위 선택만 편집 초안에서 비웁니다. 학부·학과까지만 선택하면 해당 ID를 사용하고, 세부전공을 선택하면 전공 ID를 사용합니다.
3. 저장 버튼을 누르면 `PUT /me/profile`의 **[전체 편집 객체](profiles.md#profile-write)**에 최종 `academicUnitId`와 `expectedVersion`을 보냅니다. 최초 저장 버전은 `"0"`이며, 이름·부모 ID를 별도 저장값으로 전송하지 않습니다.
4. 서버는 세션의 본인 계정과 프로필 버전을 확인하고 선택 항목의 존재·부모 경로·선택 가능 여부를 [같은 트랜잭션에서 검증](../database/catalogs.md#academic-write-contract)합니다. 기존 비활성 소속을 그대로 유지한 다른 필드 수정은 허용합니다.
5. 서버가 `profiles.academic_unit_id`와 다른 프로필 항목을 저장하고 버전을 증가시킨 뒤 커밋한 결과를 반환합니다. 기존 학사 항목을 참조하므로 학사 행이나 새 학사 ID는 생성하지 않습니다.
6. 실패하면 전체 프로필 저장을 취소하고 편집값을 유지합니다. 버전 충돌이나 유효하지 않은 선택은 위 [프로필 오류 계약](profiles.md#profile-endpoints)에 따라 최신 값을 확인합니다.

프로필 화면은 `academicUnitId`에서 부모를 따라 선택한 항목까지의 소속 경로를 표시합니다. 학부·학과만 선택한 이유나 전공 배정 상태는 별도 필드로 전달하거나 추정하지 않으며, 학사 정보 전체가 미입력이면 `academicUnitId=null`입니다. 실제 초기 목록·부모 관계·기존 데이터의 ID 대응은 [학사 미정 사항](../specs/academic-structure.md#open-questions)을 검토한 뒤 등록합니다.

## DB 연결과 남은 범위

| API 정보 | 저장·정의 원본 |
| --- | --- |
| 공통 선택지 코드·표시 정보 | [애플리케이션 공통 enum](../database/catalogs.md#code-enums) |
| 학사 경로 | [학사 테이블](../database/catalogs.md#academic-tables) |

선택값을 저장하는 요청과 프로필 응답은 [프로필 API](profiles.md)가 원본입니다.
