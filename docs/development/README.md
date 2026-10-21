# 개발 가이드

이 문서는 서경드림온의 초기 개발 기준입니다. 스캐폴딩과 이후 기능 구현에 적용하며, 실제 요구가 달라지면 변경 이유와 함께 갱신합니다.

## 용어와 적용

- **컨벤션**: 이름, 포맷, 커밋 메시지처럼 함께 맞추는 작성 방식입니다.
- **규칙**: 코드 책임, 비동기 DB 처리, 검증처럼 구현에서 지킬 기준입니다.
- **가이드**: 규칙·컨벤션과 그 이유, 작업 방법을 함께 설명합니다.

문서의 `한다/하지 않는다`는 기본 규칙이고, `권장/필요하면`은 상황에 따라 선택하는 가이드입니다. 실제 formatter와 linter 설정을 추가하면 세부 포맷의 실행 기준은 그 설정입니다. 문서와 설정이 다르면 같은 변경에서 정리합니다. 문서만으로 CI나 GitHub 병합 제한이 활성화되지는 않습니다.

## 작업별 선택

모든 문서를 순서대로 읽지 않습니다. 현재 변경에 해당하는 행만 선택하고, 관련 기능 명세가 있으면 함께 확인합니다.

| 문서 | 다루는 내용 |
| --- | --- |
| [local-development.md](local-development.md) | 처음 설치·실행하거나 검사 명령이 필요할 때 |
| [workflow.md](workflow.md) | 팀 공통 명세·개발 계획·구현·리뷰 절차와 병합 기준 |
| [architecture.md](architecture.md) | 폴더 책임·의존 방향·실행 기반을 변경할 때 |
| [conventions.md](conventions.md) | 이름·포맷·주석·브랜치·커밋·PR |
| [frontend.md](frontend.md) | 모바일 UI, API 호출, 캐시, 폼·상태 관리 |
| [공식 디자인](../design/README.md) | 저장소의 모바일 화면·상태·컴포넌트를 참조해 제품 프론트에 구현할 때 |
| [backend.md](backend.md) | 비동기 DB, 트랜잭션, API·설정·마이그레이션 |
| [DB 설계](../database/README.md) · [API 명세](../api/README.md) | 물리 ERD·테이블·요청/응답 계약을 검토하거나 구현할 때 |
| [testing.md](testing.md) | 테스트 범위, CI 단계, 완료 기준 |
| [documentation.md](documentation.md) | 문서 원본·인덱스 관리 규칙과 VitePress 자동 게시 운영 |

## 현재 결정

- 서비스명: **서경드림온**. 약칭은 **드림온**, 영문 표기는 **SKU DreamOn**, 기술 식별자의 기본형은 `sku-dreamon`입니다. 의미와 사용 기준은 [이름과 표기](../branding.md)를 따릅니다.
- 저장소: `wejo-team/sku-dreamon`. 공개 저장소이며 이름은 서비스의 기술 식별자에 맞춥니다.
- 구조: 제품의 `frontend/`, `backend/`와 독립적인 공식 UI 참고 앱 `design-reference/`가 있는 모노레포. 공통 패키지나 별도 모노레포 실행 도구는 필요가 생길 때 추가합니다.
- 프론트: React + TypeScript + Vite + React Router, Tailwind + shadcn/ui, TanStack Query + fetch, React Hook Form + Zod. 패키지 관리자는 npm입니다.
- 백엔드: FastAPI + uv + Pydantic + SQLAlchemy 2 비동기 API + asyncpg + PostgreSQL + Alembic입니다. 앞서 검토했던 동기 DB 접근안은 이 결정으로 대체합니다.
- CI: GitHub Actions. 프론트는 ESLint·Prettier·TypeScript, 백엔드는 Ruff·mypy를 사용합니다. 공식 디자인은 필요할 때 로컬에서 수동 확인합니다.
- 문서: `docs/`를 원본으로 VitePress + GitHub Pages에서 읽습니다. 명세·계획·구현의 사람 검토 절차는 그대로 유지합니다.
- 스프린트 1 로그인: [자체 아이디·비밀번호 방식](../specs/authentication.md#login-decision). 학교·이메일 인증과 소셜 로그인은 후속 범위이며, [내부 사용자 ID와 로그인 수단의 분리](../specs/authentication.md#account-linking)를 적용합니다.
- 로그인 유지: [PostgreSQL 서버 세션과 보안 쿠키](../specs/authentication.md#session-policy). 저장 필드와 요청 인증 흐름은 [DB](../database/identity.md#auth-sessions)·[API](../api/conventions.md#access) 설계에서 관리합니다.
- 처음에는 한국어 개발 문서와 영어 코드 식별자를 사용합니다.

## 아직 결정하지 않은 것

상세 도메인·테이블과 외부 API 계약은 [DB 설계](../database/README.md)와 [API 명세](../api/README.md)에 검토안으로 정리합니다. 구현 완료를 뜻하지 않습니다. CSRF 전달 세부·로그인 시도 제한 수치·세션 정리·데이터 보존·운영 배포 플랫폼은 미정입니다. 기본 로그인 유지·가입 후 자동 로그인·세션 만료·독립 동시 로그인은 [확정 정책](../specs/authentication.md#session-policy)을 적용하고 [계정 복구는 MVP에서 제외](../specs/authentication.md#account-recovery)합니다. 추천은 LLM 기반이며 모델·제공자·검색·실행·저장 등 내부 아키텍처는 [추천 명세](../specs/matching.md)의 TBD를 유지합니다. 기능 구현에 필요한 선행 결정은 [설계 검토 목록](../database/decisions.md#open-decisions)에서 확인합니다.

현재 런타임·패키지 버전은 버전 파일과 lockfile에 고정합니다. [로컬 실행](local-development.md)에서 설치 명령을 확인합니다. 버전을 변경할 때 호환성을 검사하고 파일과 문서를 함께 갱신합니다.

## 변경 방법

작은 표현·작성 방식 변경은 관련 문서를 직접 수정합니다. 스택·폴더 책임·API 계약·트랜잭션 정책을 바꾸는 경우 PR에 이유와 영향을 적고 코드와 문서를 함께 변경합니다. 이 기준은 구현 전에 모든 미래 상황을 결정하기 위한 문서가 아닙니다.
