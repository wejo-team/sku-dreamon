# DB 설계

**상태: 검토할 물리 설계안.** PostgreSQL 17.11을 기준으로 테이블·타입·키·인덱스·트랜잭션 경계를 정의합니다. 이 문서의 테이블은 아직 생성하지 않았습니다. SQL, ORM 모델, 마이그레이션 구현은 포함하지 않습니다.

기능이 어떻게 동작해야 하는지는 [기능 명세](../specs/README.md), 클라이언트와 주고받는 데이터는 [API 명세](../api/README.md)에서 관리합니다. 별도의 논리 모델 문서를 병행하지 않고, 관계와 설계 이유를 이 폴더에 함께 둡니다.

## 읽는 순서

| 문서 | 확인할 내용 |
| --- | --- |
| [공통 기준](conventions.md) | 타입·NULL·이름·버전·제약의 표기 |
| [계정·프로필](identity.md) | 로그인 수단 분리, 서버 세션, 프로필과 선택 항목, 포트폴리오 |
| [선택지·학사 구조](catalogs.md) | 공통 코드, 학사 경로, 사용 중인 항목의 보존 |
| [공모전](contests.md) | 공고·분야·참가 대상·인원·시각 |
| [팀·지원·소속](teams.md) | 팀원 관계, 지원 시도, 상태 발생 건 |
| [알림](notifications.md) | 수신자·발생 건·읽음 기록 |
| [트랜잭션](transactions.md) | 동시 선발·정원·재시도·조회 일관성 |
| [설계 결정과 검토](decisions.md) | 구현 전 남은 결정과 검증 사례 |

각 도메인의 ERD는 실제 테이블 이름과 키를 사용합니다. 전체 컬럼·복합 키·조건부 인덱스의 원본은 바로 아래 테이블 정의이며, 그림 아래에서 수정 가능한 Mermaid 원본을 펼칠 수 있습니다.

## 기능별 진입점

| 작업 | DB 설계 | API 계약 | 정책 원본 |
| --- | --- | --- | --- |
| 회원가입·로그인·프로필·사람 탐색 | [계정·프로필](identity.md), [서버 세션](identity.md#auth-sessions) | [계정·프로필 API](../api/accounts-profiles.md) | [인증](../specs/authentication.md), [프로필](../specs/profile.md) |
| 공고 목록·상세 | [공모전](contests.md) | [공모전·팀 API](../api/contests-teams.md) | [공고](../specs/contests.md) |
| 팀 생성·지원·선발·취소 | [팀·지원·소속](teams.md) | [공모전·팀 API](../api/contests-teams.md) | [팀 모집](../specs/team-recruitment.md) |
| AI 대화·지원자 검토 | [영속화 경계](decisions.md#ai-storage) | [AI·알림 API](../api/ai-notifications.md) | [추천](../specs/matching.md) |
| 알림함 | [알림](notifications.md) | [AI·알림 API](../api/ai-notifications.md) | [서비스 알림](../specs/notifications.md) |

PR의 설계 승인과 기능의 구현 완료는 별개입니다. 완료 조건의 체크는 해당 기능 명세에서 실제 구현·검증 후 갱신합니다.
