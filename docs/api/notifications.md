# 알림 API

**상태: 서버 조회·읽음·업무 알림 생성 구현, 화면 연결은 후속 범위.** 본인 목록·미읽음 수는 [라우터](../../backend/app/routers/notifications.py), [DTO](../../backend/app/schemas/notifications.py), [저장 접근](../../backend/app/repositories/notifications.py)와 [읽음 서비스](../../backend/app/services/notifications.py)에 구현합니다. 개별·선택 집합 읽음도 구현하며 최초 읽음 시각과 전체 실패 원자성을 보장합니다. 서버 앱에 연결했고, 신규 지원·지원 상태 변경·팀 생성에 따른 대기 지원 폐기의 알림을 업무와 함께 저장합니다. 프론트 통합은 후속 범위입니다. 아래 표는 최종 요청·응답 계약을 설명합니다. 모든 경로는 `/api/v1` 기준이며 로그인이 필요합니다. 제품 정책은 [알림 명세](../specs/notifications.md)를 참조합니다.

| 찾는 내용 | 위치 |
| --- | --- |
| 경로·권한·HTTP 상태 | [알림함](#notification-endpoints) |
| 요청·응답 필드 | [알림](#notification-fields) |

## 이 문서의 표기

- `Id`는 UUID 문자열, `Timestamp`는 UTC 시각 문자열입니다. [공통 계약](conventions.md)의 표현·검증·오류 형식을 적용합니다.
- 성공 응답은 [공통 `Success<T>`](conventions.md#success-responses)를 사용하며, 아래 응답 DTO 표는 `data` 내부 값을 정의합니다. `NotificationPage`는 `data`를 포함한 응답 전체이므로 다시 감싸지 않습니다.
- 객체의 **아래에 기재된 필드는 모두 필수**입니다. 생략할 수 있는 요청 필드만 별도로 `선택`이라고 표시합니다. `null` 허용은 생략 허용과 다르며, 목록의 빈 값은 `[]`입니다. 선언하지 않은 필드는 허용하지 않습니다.
- `양의 안전 정수`는 `1~9007199254740991`, `음이 아닌 안전 정수`는 `0~9007199254740991`인 JSON 정수입니다. 집계의 전송 표현 한계이며 서비스 이용 횟수 상한이 아닙니다.
- 모든 API는 공통 실패 `401`, `500`, `503`을 제공합니다. 아래 표의 **추가 실패**는 이 공통 실패에 더하는 HTTP 상태입니다. `422`는 경로·query·본문 검증 실패, `429`는 요청 제한이며 구체 제한 수치는 미정입니다.
- 경로의 `{notificationId}`는 필수 `Id`입니다. 본문을 받는 API는 표의 JSON 객체가 필수이며, `본문 없음`은 요청 DTO가 없다는 뜻입니다.

<a id="notification-endpoints"></a>

## 서비스 알림함 API

| 메서드·경로 | 요청 | 성공 | 추가 실패 |
| --- | --- | --- | --- |
| `GET /me/notifications` | `page`, `pageSize`, `unreadOnly` query | 200 `NotificationPage` | 422 |
| `GET /me/notifications/unread-count` | 없음 | 200 `Success<UnreadCount>` | 없음 |
| `PUT /me/notifications/{notificationId}/read` | 본문 없음 | 200 `Success<Notification>` | 403 CSRF, 404, 422 |
| `PUT /me/notifications/read` | `ReadNotifications` | 200 `Success<ReadNotificationsResult>` | 403 CSRF, 404, 422 |

모든 알림 경로는 인증 주체 **본인**만 대상으로 합니다. query·본문에 다른 수신자 ID를 받지 않습니다. 다른 사람의 알림이나 없는 ID는 404 `RESOURCE_NOT_FOUND`입니다.

| 목록 query | 타입·기본값 | 계약 |
| --- | --- | --- |
| `page` | 양의 정수, 기본 1 | [공통 페이지 규칙](conventions.md) 적용 |
| `pageSize` | 1~100 정수, 기본 20 | `NotificationPage`의 `data`·`pagination`에 적용 |
| `unreadOnly` | 불리언, 기본 `false` | `true`면 미읽음만 반환 |

정렬은 `occurredAt DESC, id DESC`입니다. `total`은 현재 필터와 권한을 적용한 목록 집계이며, `UnreadCount.unreadCount`는 본인의 **전체 미읽음 수**입니다. 목록 열기만으로 읽음 처리하지 않습니다. 구현은 목록·페이지 보정·필터 집계·전체 미읽음 수를 단일 SQL로 읽어 같은 DB 스냅샷을 사용합니다. 제목·본문은 사건 상태와 폐기 원인만으로 구성하며 프로필·실명 등 비공개 데이터를 읽지 않습니다.

<a id="notification-fields"></a>

## 알림 요청·응답 필드

### NotificationPage — 목록과 전체 미읽음 수

`NotificationPage`는 [공통 `Page<Notification>`](conventions.md#pagination)의 전체 필드와 아래 `unreadCount`를 **같은 객체에** 포함합니다. `data`에는 알림 배열을 담고 `pagination`·`unreadCount`는 최상위에 둡니다. 세 필드 모두 필수이며 `null`을 허용하지 않습니다.

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `data` | `Notification[]` | 현재 목록 필터에 맞는 본인 알림. 빈 결과는 `[]` |
| `pagination` | `PageMeta` | 같은 권한·필터·읽기 시점의 목록 집계 |
| `unreadCount` | 음이 아닌 안전 정수 | 목록 필터와 무관한 본인의 **전체 미읽음 수** |

`unreadOnly`·페이지 크기·현재 페이지가 달라져도 `unreadCount`는 전체 미읽음을 기준으로 합니다. 별도의 `UnreadCount` 조회 없이 목록 응답으로 알림 배지를 함께 갱신할 수 있습니다.

### Notification

| 필드 | 타입 | 의미 |
| --- | --- | --- |
| `id` | `Id` | 알림 ID |
| `kind` | `application_status_changed` 또는 `new_application` | 지원 상태 변경 또는 팀장이 받는 신규 지원 |
| `applicationId` | `Id` | 실제 지원 건 |
| `teamId` | `Id` | 해당 팀 |
| `eventStatus` | [ApplicationStatus](applications.md#values) | **사건 발생 당시** 지원 상태. 현재 상태와 구분 |
| `occurredAt` | `Timestamp` | 실제 사건 발생 시각 |
| `readAt` | `Timestamp` 또는 `null` | 최초 읽음 시각. 미읽음은 `null` |
| `title` | 문자열 | 현재 권한으로 구성한 제목 |
| `body` | 문자열 | 현재 권한으로 구성한 본문 |

### UnreadCount · ReadNotifications · ReadNotificationsResult

| 객체 | 필드 | 타입 | 의미·검증 |
| --- | --- | --- | --- |
| `UnreadCount` | `unreadCount` | 음이 아닌 안전 정수 | 본인의 전체 미읽음 수 |
| `ReadNotifications` | `notificationIds` | `Id[]` | **최소 1개, 중복 없음**. 현재 사용자에게 제공되어 읽음 대상으로 선택한 ID |
| `ReadNotificationsResult` | `updatedIds` | `Id[]` | 성공한 본인 ID. 이미 읽은 ID도 포함 |
| `ReadNotificationsResult` | `unreadCount` | 음이 아닌 안전 정수 | 처리 후 본인의 전체 미읽음 수 |

모두 읽음은 현재 사용자에게 **이미 제공된 ID의 합집합**을 전송합니다. 그 사이 도착했지만 아직 제공하지 않은 알림은 변경하지 않습니다. 이미 읽은 항목은 최초 `readAt`을 유지하고, 하나라도 타인·없는 ID가 있으면 404로 **전체 변경 없이 실패**합니다. 구현은 본인 ID들을 UUID 오름차순으로 잠근 뒤 전체 소유권을 확인하고, 미읽음 항목만 갱신한 트랜잭션의 커밋 성공 후 응답합니다. 동시 읽음도 먼저 저장한 시각을 유지하며, 성공한 `updatedIds`는 요청 순서와 같습니다.

상태 변경과 알림 생성은 [알림 생성 정책](../specs/notifications.md#generation-policy), 저장·중복 방지는 [알림 테이블](../database/notifications.md)을 참조합니다. 명시적 검토 시작·미선발과 본인 팀 생성에 따른 폐기는 기존 `application_status_changed` 계열로 전달하며 새 `kind`를 추가하지 않습니다. 실제 변경이 없는 조회·재요청이나 모집 종료·기한 경과만으로 상태 변경 알림을 만들지 않습니다. 읽음 성공 후 목적지로 이동하며, 목적지에서 현재 권한·존재 여부를 다시 확인합니다. 알림의 제목·본문도 비공개 프로필을 우회 노출하지 않습니다.

## 정합성 확인 기준

구현 시 다음 조건을 요청·응답 검증과 계약 테스트에서 확인합니다. 제품 정책의 세부 완료 조건은 각 기능 명세가 원본입니다.

- 이 문서의 4개 API에 선언한 요청·응답·성공/실패 상태를 제공하고, 별도 수동 YAML을 병행 관리하지 않습니다.
- 알림 ID 집합의 읽음은 전부 성공하거나 전부 실패하며, 이미 읽은 시각과 아직 제공하지 않은 알림을 변경하지 않습니다.

## 미정·범위 밖 항목

마감 알림·푸시·이메일은 추가하지 않습니다. 알림 보존·실시간 전달은 [알림 명세](../specs/notifications.md)의 미정 범위를 유지합니다. 인증에는 [서버 세션·쿠키 계약](conventions.md#session-auth)을 적용하며, 쓰기 경로는 현재 인증 의존성의 세션 결합 CSRF 쿠키·헤더와 HTTPS 출처 검증을 적용합니다. 전송 세부는 [인증 API](auth.md)를 따릅니다.
