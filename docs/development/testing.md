# 테스트·CI 기준

문서 링크·Wiki 변환·VitePress 빌드·생성 HTML의 링크와 자산 검사는 `docs-wiki.yml`의 `Validate docs`, 프론트·백엔드 검사는 `ci.yml`에서 실행합니다. 현재 실행 기반에 대한 검사가 있으며 도메인 기능과 E2E 검사는 기능이 생길 때 추가합니다. 앱 실행 명령은 [로컬 실행](local-development.md), 문서 명령은 [문서 관리](documentation.md)에서 확인합니다.

## 의미 있는 테스트

- 사용자가 관찰할 동작, 권한·검증 규칙, 오류 처리, 데이터 무결성을 검증합니다. 구현 코드를 그대로 반복하는 테스트나 빈 성공 테스트를 만들지 않습니다.
- 프론트는 Vitest + React Testing Library로 폼 제출·오류 표시·핵심 상태 변화를 검증합니다. 컴포넌트 옆에 테스트를 둡니다.
- 백엔드는 pytest로 순수 로직·API 계약·DB 연동을 구분해 검사합니다. `tests/` 전체를 수집하며 일부 하위 폴더를 의도 없이 누락하지 않습니다.
- 비동기 테스트는 pytest-asyncio를 기본 runner로 통일합니다. 실제 DB session·engine의 수명은 event loop 범위와 맞춥니다.
- 비동기 API 테스트에는 HTTPX AsyncClient와 ASGITransport를 사용합니다. ASGITransport만으로 앱 lifespan이 실행된다고 가정하지 않습니다. lifespan에 의존하는 테스트는 앱 시작·종료를 명시적으로 수행합니다.
- DB 통합 테스트는 전용 PostgreSQL을 사용하고 테스트 사이의 데이터 오염을 막습니다. 서비스 내부 commit이 있는 경우에도 격리되는 전략을 구현하고 검증합니다.
- 일반 PR 테스트에서 AI·유료 외부 API는 mock으로 대체합니다. 실 API 테스트는 필요할 때 수동·정기 workflow로 분리합니다.
- Playwright는 로그인·모집·지원 같은 실제 핵심 흐름이 생길 때 추가합니다. 모바일 viewport 검사는 실제 기기의 키보드·스크롤 확인을 보완합니다.

## 단계별 CI

`ci.yml`의 프론트·백엔드 job을 병렬 실행합니다. backend job은 전용 PostgreSQL 17.11 서비스에 연결하고, `DATABASE_URL`과 `TEST_DATABASE_URL`을 같은 테스트 DB로 지정해 DB 검사가 생략되지 않도록 합니다.

| 단계 | 검사 |
| --- | --- |
| 프론트 실행 기반 | `npm ci`, ESLint, Prettier check, TypeScript check, production build |
| API 계약 동기화 | Backend의 `uv run python -m scripts.export_openapi --check`, Frontend의 `npm run api:check`; 생성물은 수정하지 않고 최신성 검사 |
| 프론트 기능·클라이언트 로직 | 현재 HTTP 성공·오류·취소와 연결 화면의 상태·재시도를 Vitest로 검증 |
| 백엔드 실행 기반 | `uv sync --locked`, Ruff lint·format check, mypy, pytest |
| 비동기 DB 기반 | PostgreSQL에서 `alembic upgrade head`, `alembic check`, 연결 검사, 세션 분리·commit·rollback·종료 정리 통합 테스트 |
| DB 모델 도입 | 위 검사에 실제 모델의 migration 적용·조회 테스트 추가 |
| 핵심 사용자 흐름 완성 | 선택한 Playwright 흐름을 CI에서 실행 |

- 프론트 검사 명령은 package.json scripts, Python 도구 설정은 pyproject.toml에 모읍니다. README·로컬 실행·CI가 같은 명령을 사용하도록 맞춥니다.
- API 타입 생성은 런타임 응답 검증을 대신하지 않습니다. Zod 출력과 생성 타입의 양방향 비교는 TypeScript 검사로, 실제 잘못된 응답과 exporter·생성기 검사는 pytest·Vitest로 확인합니다. 최신성 검사와 의미상 호환성 리뷰의 차이는 [API 계약](api-contracts.md)을 따릅니다.
- DB 통합 테스트의 데이터베이스는 운영 환경과 분리합니다. Alembic 적용 후 모델을 실제로 조회할 수 있는지 확인합니다.
- 런타임·도구 버전을 고정하고 lockfile 기반으로 설치합니다. CI에서 의존성을 임의 갱신하지 않습니다.
- 초기에는 모든 PR에서 필요한 job을 실행합니다. 경로 필터 때문에 필수 검사가 영구 대기하는 구성을 피합니다.
- 핵심 검사를 `continue-on-error`나 테스트 없음 허용 설정으로 숨기지 않습니다. 필수 검사와 선택 검사를 구분합니다.
- 문서만 변경했다면 링크·내용·차이 검증으로 충분합니다. 관련 없는 전체 앱 테스트를 무조건 반복하지 않습니다.
- 브랜치 보호와 배포는 별도 설정입니다. 적용하지 않은 보호 정책이나 배포를 완료했다고 보고하지 않습니다.

## PR 완료 확인

변경한 기능의 정상·실패 경로를 확인하고, 필요한 테스트·타입 검사·빌드를 수행합니다. DB/API/UI 계약이 바뀌면 관련 코드와 문서를 함께 갱신합니다. PR에 수행한 검사와 수행하지 못한 검사, 남은 제한을 적습니다.

## 근거

- [uv GitHub Actions 통합](https://docs.astral.sh/uv/guides/integration/github/)
- [FastAPI 비동기 테스트](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Playwright 모바일 에뮬레이션](https://playwright.dev/docs/emulation)
- [GitHub workflow 트리거](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
