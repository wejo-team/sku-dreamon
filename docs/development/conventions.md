# 작성·Git 컨벤션

## 이름과 포맷

| 대상 | 기준 | 예시 |
| --- | --- | --- |
| React 컴포넌트와 파일 | PascalCase | `RecruitmentForm.tsx` |
| TS 함수·변수·커스텀 훅 | camelCase, 훅은 use 접두사 | `submitApplication`, `useRecruitments` |
| 일반 TS 파일·폴더 | kebab-case, 단순 역할 이름 허용 | `query-client.ts`, `api.ts`, `queries.ts` |
| 기능 폴더 | 리소스 중심 복수형 | `features/recruitments/` |
| Python 모듈·함수·변수 | snake_case | `create_recruitment`, `session.py` |
| Python 클래스 | PascalCase | `RecruitmentCreate` |
| 환경변수 | UPPER_SNAKE_CASE | `DATABASE_URL` |
| DB 테이블·컬럼 | snake_case, 테이블은 복수형 | `recruitments`, `created_at` |
| API JSON 필드 | snake_case | `created_at` |

shadcn/ui가 생성하는 `components/ui/button.tsx` 같은 파일은 도구의 기본 파일명을 유지합니다. 위 PascalCase 파일명 규칙은 직접 작성하는 컴포넌트에 적용합니다.

API 응답 타입은 서버 필드명을 유지합니다. 화면에서 camelCase 모델이 필요하면 기능 경계에서 명시적으로 변환합니다. 모든 응답에 재귀적인 키 변환을 자동 적용하지 않습니다.

- 파일은 UTF-8, LF, 마지막 개행을 사용합니다.
- TypeScript·JSON은 2칸, Python은 4칸 들여쓰기를 기본으로 합니다.
- 프론트 포맷은 Prettier, Python 포맷은 Ruff에 맡깁니다. Python 줄 길이는 88로 설정합니다.
- TypeScript strict 모드를 사용합니다. `any`, 타입 무시, 린트 비활성화는 필요한 범위로 제한하고 이유를 적습니다.
- Python의 외부에서 사용하는 함수와 서비스 경계에는 타입을 명시합니다.
- 주석은 코드가 하는 일을 반복하기보다 이유·제약을 설명합니다. TODO에는 남은 작업을 구체적으로 적습니다.
- 테스트는 TS의 경우 대상 옆 `*.test.ts(x)`, Python은 `tests/**/test_*.py`에 둡니다.

## Git과 PR

- 기본 브랜치는 `main`입니다. 일반 개발은 작업 브랜치와 PR로 진행합니다.
- 사람과 에이전트 모두 `<type>/<작업-내용>` 형식을 사용합니다. type은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci` 중 작업 목적에 맞게 고르고, 작업 내용은 소문자 영문·숫자·하이픈으로 적습니다. 예: `feat/recruitment-form`, `fix/login-redirect`, `docs/branch-naming`.
- 에이전트·도구 이름을 나타내는 접두사(`codex/`, `claude/`, `agent/` 등)는 붙이지 않습니다. 도구가 브랜치 이름을 자동 제안해도 같은 규칙을 적용합니다.
- 커밋과 PR 제목은 `type(scope): 설명`을 기본으로 합니다. 예: `feat(frontend): 모집글 작성 폼 추가`, `docs: 개발 가이드 정리`.
- 타입은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`를 사용합니다. 별도 강제 도구는 필요가 생길 때 추가합니다.
- 하나의 PR은 설명할 수 있는 한 목적을 갖습니다. PR에는 문제·변경 결과·검증 방법을 적습니다.
- PR 병합은 Squash merge만 사용합니다. 작업 브랜치의 작은 커밋은 유지하되 `main`에는 PR 하나를 커밋 하나로 남깁니다. PR 제목과 설명이 병합 커밋의 기본 제목·본문이므로 최종 결과에 맞게 정리합니다.
- 변경 요청이 남은 PR은 일반 팀원이 병합할 수 없고, 프로젝트 리더는 예외 권한을 사용할 수 있습니다. 적용 범위와 재검토 절차는 [팀 작업 흐름](workflow.md)을 따릅니다.
- 의존성을 변경하면 해당 lockfile도 함께 변경합니다. 같은 프론트에 npm·pnpm·Yarn lockfile을 섞지 않습니다.
- 승인된 기능 범위의 변경과 관련 문서를 함께 갱신합니다. 이 문서 자체는 사용자에게 매번 추가 승인을 요구하는 규정이 아닙니다.
- 실행 결과와 제한을 정확하게 적습니다. 검사 설정이 있다는 이유로 검사가 통과했다고 쓰지 않습니다.

## 설정과 데이터

- `.env.example`에는 실행에 필요한 키와 예시만 둡니다. 실제 비밀값·개인정보·운영 DB 덤프를 커밋하지 않습니다.
- `VITE_*`는 브라우저에 포함되는 공개 설정으로 취급합니다. DB 접속 정보와 AI 비밀키는 백엔드에서 관리합니다.
- 날짜·시간 API는 시간대가 포함된 ISO 8601을 사용하고 저장·전송 기준은 UTC로 맞춥니다. 사용자 화면에서 표시 시간대로 변환합니다.
- 생성 파일과 사람이 수정하는 파일의 역할을 명확히 합니다. 코드 생성 도입 시 생성 파일 경로와 재생성 명령을 문서화합니다.
