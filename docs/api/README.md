# API 설계

**검토 상태: 설계 초안 · 제품 API 미구현.** 화면과 서버가 주고받을 요청·응답, 실패, 권한 경계를 정의합니다. 현재 구현된 health API를 제외한 제품 경로는 이 문서의 설계 대상이며, 문서 검증 성공이 서버 동작을 뜻하지 않습니다.

## 읽는 순서

| 확인할 내용 | 문서 |
| --- | --- |
| 공통 이름·인증 경계·페이지 이동·오류 | [공통 계약](conventions.md) |
| 가입·로그인·프로필·선택지·사람 탐색 | [계정과 프로필 API](accounts-profiles.md) |
| 공모전·팀·지원·선발·워크스페이스 | [공모전과 팀 API](contests-teams.md) |
| 현재 AI 대화·지원자 검토·알림 | [AI와 알림 API](ai-notifications.md) |
| 필드 단위 타입·필수값·응답 코드 | [OpenAPI 3.1 원본 위치](#openapi-source) |

## 문서별 책임

- **기능의 이유와 정책**은 [기능 명세](../specs/README.md)가 원본입니다. 이 폴더에서는 관련 절을 연결하고 같은 정책을 다시 서술하지 않습니다.
- **테이블·컬럼·제약·처리 범위**는 [DB 설계](../database/README.md)가 원본입니다. API는 테이블의 직접 노출이 아니라 화면별 공개 범위를 반영한 DTO입니다.
- **전송 필드와 HTTP 상태**는 `openapi.yaml`이 원본입니다. Markdown은 endpoint 찾기와 중요한 실패 흐름을 설명합니다. 계약을 수정할 때 둘의 연결을 함께 확인합니다.

## 구현 전에 남은 결정

인증 전달 방식·세션 수명, 일부 지원 상태 전이, 공고 변경 영향, LLM 내부 구조와 데이터 보존은 여전히 미정입니다. [공통 계약의 보류 목록](conventions.md#deferred)에서 각 기능 명세로 이동할 수 있습니다.

OpenAPI의 모든 operation에는 `x-contract-status: proposed`와 `x-auth-policy`를 표시합니다. 아직 선택하지 않은 인증 방식을 임의의 Bearer나 쿠키로 채우지 않았습니다. **이 원본은 구조 검토용이며 현재 상태로 인증 없는 서버·클라이언트·모의 서버를 생성해서 배포하는 계약이 아닙니다.**

JSON 이름과 접두사의 근거는 [저장소 API 작성 규칙](../development/conventions.md), 문법 기준은 [OpenAPI 3.1.0](https://spec.openapis.org/oas/v3.1.0.html)입니다. 구현 코드·ORM·SQL·마이그레이션은 포함하지 않습니다.

<a id="openapi-source"></a>

## OpenAPI 원본 열기

원본 파일은 **`docs/api/openapi.yaml`**입니다. GitHub에서는 이 문서와 같은 폴더의 `openapi.yaml`을 열어 **Raw**로 내려받고, 로컬에서는 해당 파일을 편집기나 OpenAPI 뷰어로 엽니다. PR 검토 시에는 PR의 브랜치에 있는 파일을 사용합니다.

YAML 하나에서 전송 필드를 관리하며, 이 문서 사이트의 영역별 표는 경로·권한·주요 실패를 찾는 안내입니다. 명세 변경 시 YAML과 설명의 대응을 함께 확인합니다.
