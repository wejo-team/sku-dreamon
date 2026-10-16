# 개발 가이드

이 문서는 WEJO의 초기 개발 기준입니다. 스캐폴딩과 이후 기능 구현에 적용하며, 실제 요구가 달라지면 변경 이유와 함께 갱신합니다.

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
| [workflow.md](workflow.md) | 명세·개발 계획·구현·리뷰를 진행할 때 |
| [architecture.md](architecture.md) | 폴더 책임·의존 방향·실행 기반을 변경할 때 |
| [conventions.md](conventions.md) | 이름·포맷·주석·브랜치·커밋·PR |
| [frontend.md](frontend.md) | 모바일 UI, API 호출, 캐시, 폼·상태 관리 |
| [backend.md](backend.md) | 비동기 DB, 트랜잭션, API·설정·마이그레이션 |
| [testing.md](testing.md) | 테스트 범위, CI 단계, 완료 기준 |
| [documentation.md](documentation.md) | 문서·인덱스·Wiki 게시를 변경할 때 |

## 현재 결정

- 저장소: `wejo-team/wejo-app`. 임시 이름이며 공개 저장소입니다.
- 구조: `frontend/`, `backend/`가 있는 모노레포. 공통 패키지나 별도 모노레포 실행 도구는 필요가 생길 때 추가합니다.
- 프론트: React + TypeScript + Vite + React Router, Tailwind + shadcn/ui, TanStack Query + fetch, React Hook Form + Zod. 패키지 관리자는 npm입니다.
- 백엔드: FastAPI + uv + Pydantic + SQLAlchemy 2 비동기 API + asyncpg + PostgreSQL + Alembic입니다. 앞서 검토했던 동기 DB 접근안은 이 결정으로 대체합니다.
- CI: GitHub Actions. 프론트는 ESLint·Prettier·TypeScript, 백엔드는 Ruff·mypy를 사용합니다.
- 처음에는 한국어 개발 문서와 영어 코드 식별자를 사용합니다.

## 아직 결정하지 않은 것

서비스명, 로그인 제공자와 세션 방식, 상세 도메인·테이블, 운영 배포 플랫폼, AI 모델·제공자는 미정입니다. 초기 문서와 실행 기반을 만드는 데 이 결정을 먼저 할 필요는 없습니다. 필요한 기능을 구현하기 전에 확정하고 관련 문서를 갱신합니다.

현재 런타임·패키지 버전은 버전 파일과 lockfile에 고정합니다. [로컬 실행](local-development.md)에서 설치 명령을 확인합니다. 버전을 변경할 때 호환성을 검사하고 파일과 문서를 함께 갱신합니다.

## 변경 방법

작은 표현·작성 방식 변경은 관련 문서를 직접 수정합니다. 스택·폴더 책임·API 계약·트랜잭션 정책을 바꾸는 경우 PR에 이유와 영향을 적고 코드와 문서를 함께 변경합니다. 이 기준은 구현 전에 모든 미래 상황을 결정하기 위한 문서가 아닙니다.
