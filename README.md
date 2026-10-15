# WEJO App

WEJO 팀의 웹 서비스 개발 저장소입니다. `wejo-app`은 임시 저장소 이름이며, 서비스 이름은 아직 정하지 않았습니다.

현재 단계는 **개발 기준 정리**입니다. 프론트엔드·백엔드 애플리케이션과 CI는 아직 생성하지 않았습니다.

## 시작할 문서

- [개발 가이드](docs/development/README.md): 확정한 기술 선택과 문서별 책임
- [폴더 구조와 스캐폴딩 계획](docs/development/architecture.md)
- [작성·Git 컨벤션](docs/development/conventions.md)
- [에이전트 작업 안내](AGENTS.md)

## 선택한 기술

| 영역 | 구성 |
| --- | --- |
| 프론트엔드 | React, TypeScript, Vite, React Router, npm |
| UI·입력 | Tailwind CSS, shadcn/ui, React Hook Form, Zod |
| 서버 데이터 | TanStack Query, fetch |
| 백엔드 | FastAPI, Pydantic, pydantic-settings, Uvicorn, uv |
| 데이터베이스 | PostgreSQL, SQLAlchemy 2 비동기 API, asyncpg, Alembic |
| 품질 검사 | ESLint, Prettier, TypeScript, Ruff, mypy |
| 테스트 | Vitest, React Testing Library, pytest, pytest-asyncio, HTTPX; 핵심 흐름 완성 후 Playwright |
| CI | GitHub Actions |

설치·실행·검사 명령은 실제 스캐폴딩을 완료하고 검증한 뒤 이 README에 추가합니다.
