# 작성·Git 컨벤션

## 이름과 포맷

| 대상 | 기준 | 예시 |
| --- | --- | --- |
| React 컴포넌트와 파일 | PascalCase | `RecruitmentForm.tsx` |
| TS 함수·변수·커스텀 훅 | camelCase, 훅은 use 접두사 | `submitApplication`, `useRecruitments` |
| 일반 TS 파일·폴더 | kebab-case, 단순 역할 이름 허용 | `query-client.ts`, `api.ts`, `queries.ts` |
| 기능 폴더 | 리소스 중심 복수형 | `features/recruitments/` |
| Python 모듈·함수·변수·모델 필드 | snake_case | `create_recruitment`, `created_at`, `session.py` |
| Python 클래스 | PascalCase | `RecruitmentCreate` |
| 환경변수 | UPPER_SNAKE_CASE | `DATABASE_URL` |
| DB 테이블·컬럼 | snake_case, 테이블은 복수형 | `recruitments`, `created_at` |
| API JSON 요청·응답 필드 | camelCase | `createdAt` |

shadcn/ui가 생성하는 `components/ui/button.tsx` 같은 파일은 도구의 기본 파일명을 유지합니다. 위 PascalCase 파일명 규칙은 직접 작성하는 컴포넌트에 적용합니다.

백엔드 내부와 전송 JSON의 이름을 연결하는 범위와 적용 상태는 아래 「API JSON 필드명」 절을 따릅니다.

- 파일은 UTF-8, LF, 마지막 개행을 사용합니다.
- TypeScript·JSON은 2칸, Python은 4칸 들여쓰기를 기본으로 합니다.
- 프론트 포맷은 Prettier, Python 포맷은 Ruff에 맡깁니다. Python 줄 길이는 88로 설정합니다.
- TypeScript strict 모드를 사용합니다.
- Python의 외부에서 사용하는 함수와 서비스 경계에는 타입을 명시합니다.
- 테스트는 TS의 경우 대상 옆 `*.test.ts(x)`, Python은 `tests/**/test_*.py`에 둡니다.

## API JSON 필드명

Python 모델 필드·ORM 속성·DB 컬럼은 snake_case, API JSON의 요청·응답 필드는 camelCase로 통일합니다. 예를 들어 내부의 `created_at`은 JSON에서 `createdAt`으로 전송합니다. 프론트의 API 타입·전송용 Zod schema·UI는 전송 이름인 `createdAt`을 그대로 사용합니다.

- 이름의 연결은 백엔드 API DTO의 Pydantic alias로 처리합니다. 요청은 camelCase로 검증한 뒤 내부에서 snake_case 속성으로 접근하고, 응답은 내부 snake_case 데이터를 camelCase로 직렬화합니다. Python 내부 속성명을 두 형태로 작성하지 않습니다.
- 외부 요청에서 DTO 필드의 snake_case 이름과 camelCase·snake_case 혼용은 거부합니다. 선택 필드의 잘못된 이름을 조용히 무시하지 않으며, 중첩 DTO와 목록 안의 DTO에도 같은 규칙을 적용합니다.
- 변환 대상은 DTO에 선언한 필드 이름입니다. 임의 dictionary·map의 키, 사용자가 정한 키, enum·문자열 값, 외부 서비스 payload를 재귀적으로 바꾸지 않습니다. 외부 payload를 서비스 DTO로 옮길 때는 해당 연동 경계에서 명시적으로 매핑합니다.
- URL 경로·path parameter·query parameter·header는 JSON 필드와 별도로 명세에 이름을 정합니다. JSON alias가 이 이름까지 자동 변환한다고 가정하지 않습니다. 환경변수는 기존 UPPER_SNAKE_CASE를 유지합니다.
- 프론트 공통 HTTP 클라이언트에는 자동 키 변환기를 넣지 않습니다. 날짜 문자열을 화면용 Date로 바꾸는 등 값의 의미가 달라지는 변환은 응답 검증 뒤 명시적으로 수행합니다.
- 이미 공개한 JSON 필드명을 바꿀 때는 기존 소비자에 대한 영향을 확인하고 명세·관련 테스트·배포 순서를 함께 검토합니다.

**적용 상태:** [공통 DTO](../../backend/app/core/http/schemas.py)에 요청 alias 검증과 응답 직렬화를 구현했습니다. [HTTP 계약 테스트](../../backend/tests/integration/test_api_contract.py)에서 다단어·중첩·선택 필드의 snake_case·혼용 거부와 map 키 보존을 확인합니다. 제품 API는 각 도메인에서 이 기반을 적용하고 실제 계약을 검증합니다. health 응답의 `status`와 본문 모양은 유지합니다.

## 주석과 검사 예외

- 설명 주석과 docstring은 한글로 작성합니다. 코드 식별자·표준 용어·도구 지시문은 원래 표기를 유지합니다.
- 직접 작성하는 소스 파일 상단에는 역할을 설명하는 짧은 주석을 둡니다. Python은 모듈 docstring으로 작성하며, 파일명만 반복하거나 변경 이력을 나열하지 않습니다. 생성 파일과 외부 원본은 해당 관리 규칙을 따릅니다.
- 주석은 코드만으로 알기 어려운 이유·제약·호환성 조건을 설명합니다. 이름과 구현으로 충분히 드러나는 동작은 반복해서 설명하지 않습니다.
- 외부에서 호출하는 함수나 서비스 경계에 설명이 필요하면 입력·반환값의 의미, 발생 가능한 오류, 부수 효과를 적습니다. TypeScript는 JSDoc, Python은 docstring을 사용하며 타입 선언을 그대로 반복하는 양식은 채우지 않습니다.
- TODO에는 남은 작업과 완료 조건을 적고, 관련 Issue가 있으면 연결합니다. 구현이 바뀌면 관련 주석과 TODO도 함께 갱신합니다.

주석에서 제약을 설명하는 예시입니다. 실제 모집 기능의 명세가 아닙니다.

```typescript
// 요청이 끝날 때까지 버튼을 잠가 느린 네트워크에서 같은 신청이 반복 전송되는 것을 막는다.
```

- `any`, 타입 무시, 린트 비활성화는 타입 선언·입력 검증·구현 수정으로 해결할 수 없는 경우에만 사용합니다. 예외에는 이유와 영향을 받는 최소 범위를 적습니다.
- TypeScript 오류를 무시해야 한다면 해당 줄에 설명을 붙인 `@ts-expect-error`를 사용합니다. 파일 전체의 타입 검사를 끄거나 오류가 사라져도 남는 `@ts-ignore`를 추가하지 않습니다.
- ESLint는 해당 줄의 규칙 이름, Ruff는 `noqa: <코드>`, mypy는 `type: ignore[<오류 코드>]`처럼 대상 검사를 명시합니다. 파일 전체 예외가 필요한 생성 코드 등은 도구 설정에서 해당 파일만 지정하고 근거를 남깁니다.
- 임시 우회에는 제거할 조건을 적고 관련 Issue가 있으면 연결합니다. 변경한 예외가 필요한지 해당 타입·린트 검사를 실행해 확인합니다.

## Git과 PR

- 기본 브랜치는 `main`입니다. 일반 개발은 작업 브랜치와 PR로 진행합니다.
- 사람과 에이전트 모두 `<type>/<작업-내용>` 형식을 사용합니다. type은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci` 중 작업 목적에 맞게 고르고, 작업 내용은 소문자 영문·숫자·하이픈으로 적습니다. 예: `feat/recruitment-form`, `fix/login-redirect`, `docs/branch-naming`.
- 에이전트·도구 이름을 나타내는 접두사(`codex/`, `claude/`, `agent/` 등)는 붙이지 않습니다. 도구가 브랜치 이름을 자동 제안해도 같은 규칙을 적용합니다.
- 커밋과 PR 제목은 `type(scope): 설명`을 기본으로 합니다. 예: `feat(frontend): 모집글 작성 폼 추가`, `docs: 개발 가이드 정리`.
- 타입은 `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`를 사용합니다. PR 제목 형식은 `PR conventions` 검사로 확인합니다.
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
