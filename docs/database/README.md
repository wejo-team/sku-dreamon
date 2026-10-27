# DB 설계

**상태: 비AI 구현 및 AI 실행·대화 저장 구현.** PostgreSQL 17.11을 기준으로 테이블·타입·키·인덱스·트랜잭션 경계를 설명합니다. 계정·서버 세션·인증 시도 제한, 학사, 공고, 프로필, 팀·지원·소속·발생 건·알림과 AI 실행 메타데이터·대화·메시지의 21개 테이블을 ORM과 9개 Alembic revision으로 구현했습니다. [Alembic 모델 등록](../../backend/alembic/env.py), [시작 revision](../../backend/alembic/versions/20261024_03_auth.py), [현재 head](../../backend/alembic/versions/20261026_09_contest_sources.py)에서 실제 적용 대상을 확인합니다.

마이그레이션은 계정 → 학사 → 공고 → 프로필 → 팀·지원·알림 → 인증 시도 제한 → AI 실행 메타데이터 → AI 대화·메시지 순서로 연결되며, 적용 명령은 [로컬 실행](../development/local-development.md)을 따릅니다. 저장 구조의 존재는 모든 생성·상태 변경 API의 구현이나 운영 DB 적용을 뜻하지 않습니다. 실제 기능 범위는 [API 인덱스](../api/README.md)에서 구분합니다. 개발용 가상 사용자·학사·팀·지원·알림은 [개발 시드 명령](../development/local-development.md)으로 별도 적재하며, 운영 학사 원장과 공고는 시드 명령에 포함하지 않습니다.

기능이 어떻게 동작해야 하는지는 [기능 명세](../specs/README.md), 클라이언트와 주고받는 데이터는 [API 명세](../api/README.md)에서 관리합니다. 별도의 논리 모델 문서를 병행하지 않고, 관계와 설계 이유를 이 폴더에 함께 둡니다.

## 읽는 순서

| 문서 | 확인할 내용 |
| --- | --- |
| [전체 ERD](overview.md) | 전체 테이블과 도메인 간 FK 관계 |
| [공통 기준](conventions.md) | 타입·NULL·이름·버전·제약의 표기 |
| [계정·프로필](identity.md) | 계정·자체 로그인 정보, 서버 세션, 프로필과 선택 항목, 포트폴리오 |
| [선택지·학사 구조](catalogs.md) | 애플리케이션 공통 enum, 선택 코드 저장, 단일 학사 계층·기존 소속 보존 |
| [공모전](contests.md) | 공고·분야·참가 대상·인원·시각 |
| [팀·지원·소속](teams.md) | 팀원 관계, 지원 시도, 상태 발생 건 |
| [AI 대화·실행 저장](ai.md) | 계정 소유 대화·입력/답변·실행 소유권·검증·보존 |
| [알림](notifications.md) | 수신자·발생 건·읽음 기록 |
| [트랜잭션](transactions.md) | 동시 선발·정원·재시도·조회 일관성 |
| [설계 결정과 검토](decisions.md) | 구현 전 남은 결정과 검증 사례 |

단일 PK의 `<단수형 테이블명>_id` 규칙은 [PK 컬럼 이름과 참조](conventions.md#primary-key-names), 대리키·공유 PK·복합 PK의 선택 이유는 [기본 키 선택 기준](decisions.md#primary-keys)에서 확인합니다.

먼저 [전체 ERD](overview.md)로 계정·학사·공고·팀·알림의 연결을 확인한 뒤 도메인별 상세를 읽습니다. 각 도메인의 ERD는 실제 테이블 이름과 키를 사용합니다. 전체 컬럼·복합 키·조건부 인덱스의 원본은 바로 아래 테이블 정의이며, 그림 아래에서 수정 가능한 Mermaid 원본을 펼칠 수 있습니다.

## 기능별 진입점

| 작업 | DB 설계 | API 계약 | 정책 원본 |
| --- | --- | --- | --- |
| 회원가입·로그인·프로필·사람 탐색 | [계정·프로필](identity.md), [서버 세션](identity.md#auth-sessions) | [계정·인증 API](../api/auth.md), [프로필 API](../api/profiles.md) | [인증](../specs/authentication.md), [프로필](../specs/profile.md) |
| 공통 선택지·학사 목록 | [선택지·학사 구조](catalogs.md) | [선택지 API](../api/catalogs.md) | [선택지](../specs/profile-options.md), [학사 구조](../specs/academic-structure.md) |
| 공고 목록·상세 | [공모전](contests.md) | [공모전 API](../api/contests.md) | [공고](../specs/contests.md) |
| 팀 생성·지원·선발·취소 | [팀·지원·소속](teams.md) | [팀 API](../api/teams.md), [지원 API](../api/applications.md) | [팀 모집](../specs/team-recruitment.md) |
| AI 대화·지원자 검토 | [대화·실행 저장](ai.md) | [AI API](../api/ai.md) | [추천](../specs/matching.md) |
| 알림함 | [알림](notifications.md) | [알림 API](../api/notifications.md) | [서비스 알림](../specs/notifications.md) |

PR의 설계 승인과 기능의 구현 완료는 별개입니다. 완료 조건의 체크는 해당 기능 명세에서 실제 구현·검증 후 갱신합니다.
