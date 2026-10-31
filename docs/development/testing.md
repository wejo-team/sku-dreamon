# 테스트·CI 기준

문서 검사는 `docs.yml`의 `Validate docs`, 프론트·백엔드 검사는 `ci.yml`에서 실행합니다. PR에서는 변경 영향 범위를 선택하고, `develop`과 `main`에 병합된 뒤에는 전체를 검사합니다. `develop`은 CI만 실행하며, 운영 CD는 `main`의 같은 SHA에서 필요한 CI가 성공한 뒤 실행합니다. unit·HTTP·PostgreSQL 검사와 제품 Playwright E2E를 실행합니다. 실제 프론트·서버·DB 실행은 [통합테스트와 bug bash](bug-bash.md), 일반 앱 실행은 [로컬 실행](local-development.md), 문서 명령은 [문서 관리](documentation.md)에서 확인합니다. 제품 화면 검증은 `frontend/`에서 수행합니다. 삭제한 레퍼런스 앱의 [과거 실행 기록](#design-reference)은 제품 변경의 필수 검사가 아닙니다.

## 의미 있는 테스트

- 사용자가 관찰할 동작, 권한·검증 규칙, 오류 처리, 데이터 무결성을 검증합니다. 구현 코드를 그대로 반복하는 테스트나 빈 성공 테스트를 만들지 않습니다.
- 프론트는 Vitest + React Testing Library로 폼 제출·오류 표시·핵심 상태 변화를 검증합니다. 컴포넌트 옆에 테스트를 둡니다.
- 백엔드는 pytest로 순수 로직·API 계약·DB 연동을 구분해 검사합니다. `tests/` 전체를 수집하며 일부 하위 폴더를 의도 없이 누락하지 않습니다.
- 백엔드 테스트는 `tests/unit/`과 `tests/integration/`으로 나눕니다. 유닛 테스트는 DTO·값 검증·순수 규칙을, 통합 테스트는 실제 ASGI 요청/응답 또는 PostgreSQL 경계를 검증합니다. HTTP 통합에는 DB가 필요하지 않을 수 있으며, DB가 필요한 테스트만 `database` marker를 함께 붙입니다.
- 새 동작은 기대 결과를 테스트로 먼저 작성하고 실패를 확인한 뒤 최소 구현으로 통과시킵니다. PR에 실패 원인과 통과 결과를 남기되, 구현 세부사항을 그대로 복사하는 테스트나 실패를 만들기 위한 불필요한 코드는 추가하지 않습니다.
- 값 조합·경계값은 유닛 테스트에서 검사하고 통합 테스트에는 실제 연결에서 달라질 수 있는 대표 성공·실패 경로만 남깁니다. 같은 검증 조합을 모든 HTTP·DB 계층에서 반복하거나 전체 OpenAPI snapshot으로 고정하지 않습니다. DB 변경이 없는 공통 API 작업에는 새 DB 통합 테스트를 추가하지 않습니다.
- ORM 기반의 제약 이름·컬럼 조합은 DB 없이 metadata와 PostgreSQL DDL로 검사합니다. UUID·시각 기본값처럼 실제 INSERT/조회/UPDATE 경계가 필요한 부분만 격리된 PostgreSQL의 대표 통합 테스트로 확인합니다. 테스트 모델은 별도 metadata를 사용하여 앱·Alembic에 섞이지 않게 합니다.
- 비동기 테스트는 pytest-asyncio를 기본 runner로 통일합니다. 실제 DB session·engine의 수명은 event loop 범위와 맞춥니다.
- 비동기 API 테스트에는 HTTPX AsyncClient와 ASGITransport를 사용합니다. ASGITransport만으로 앱 lifespan이 실행된다고 가정하지 않습니다. lifespan에 의존하는 테스트는 앱 시작·종료를 명시적으로 수행합니다.
- 다단어 필드를 가진 API DTO를 처음 구현할 때 [컨벤션](conventions.md)의 「API JSON 필드명」 규칙을 실제 HTTP 요청·응답으로 검사합니다. camelCase 요청 허용·응답 이름, snake_case·혼용 요청 거부, 선택 필드의 잘못된 이름, 중첩 DTO·목록에 대한 규칙 적용과 임의 map 키 보존을 확인합니다. 이 검사는 해당 DTO 구현과 함께 추가합니다.
- DB 통합 테스트는 전용 PostgreSQL을 사용하고 테스트 사이의 데이터 오염을 막습니다. 서비스 내부 commit이 있는 경우에도 격리되는 전략을 구현하고 검증합니다.
- 일반 PR 테스트에서 AI·유료 외부 API는 mock으로 대체합니다. 실 API 테스트는 필요할 때 수동·정기 workflow로 분리합니다.
- 제품 Playwright는 `frontend/e2e/`에서 실제 HTTPS·쿠키·CSRF·서버·DB를 검사합니다. `python3 scripts/run_bugbash.py`가 localhost `*_e2e` DB 검증·서버 준비·E2E·종료를 담당합니다. 검증 정보를 받지 않은 `npm run test:e2e` 직접 실행은 요청 전에 실패하며 개발 DB에는 연결하지 않습니다. CI의 `Integration E2E`도 같은 실행기를 사용하며, 기본 비AI 시나리오 뒤 `--ai-fixture`로 AI 화면 시나리오를 별도 실행합니다. 모델 드라이버만 대체하고 HTTPS·SSE·인증·DB는 실제 경로를 사용하며 유료 제공자는 호출하지 않습니다. [시험 환경과 명령](bug-bash.md#ai-e2e)을 따릅니다. Vitest의 `npm test`와 별도 검사입니다. 모바일 viewport 검사는 실제 기기의 키보드·스크롤 확인을 보완합니다.

## 개발 시드 통합 회귀

[개발 시드 검사](../../backend/tests/integration/test_dev_seed.py)는 기존 `TEST_DATABASE_URL`의 PostgreSQL에 실행별 임시 스키마를 만들고 검사 후 제거합니다. Docker 실행 권한이나 별도 DB 생성 권한을 추가로 요구하지 않습니다. 명령은 백엔드 폴더에서 실행합니다.

```bash
# TEST_DATABASE_URL은 기존 wejo_test 같은 격리 테스트 DB로 지정합니다.
uv run pytest tests/integration/test_dev_seed.py tests/integration/test_dev_dataset.py \
  tests/integration/test_reset_dev_passwords.py
```

실제 `seed_users`·`seed_teams`·제품 서비스를 사용해 계정·팀·지원·알림의 부분 저장 후 전체 롤백, 300개 계정·후보 한 공고의 상한인 6개 팀 생성, 재실행 시 추가 생성 없음과 편집된 프로필을 포함한 기존 행 보존을 검사합니다. 외부 transaction과 `create_savepoint`는 원래 시드와 같은 방식으로 구성합니다. 암호 해시는 해당 테스트 안에서만 저장용 값으로 대신하며 로그인·암호 검증은 기존 인증 테스트가 담당합니다.

명시적 `refresh_content` 경로는 구시드 콘텐츠와 정확히 같은 프로필·팀만 갱신하는지, 사용자 편집·계정 식별자 충돌·동시 저장을 보존하는지 검사합니다. dry-run과 중간 실패의 전체 롤백, version 갱신, 반복 실행 시 추가 변경 없음도 같은 격리 스키마에서 확인합니다.

공고가 없거나 마감·예정 상태일 때, 접수 시작 시각과 정확히 같을 때, 마감까지 남은 시간이 7일 미만·정확히 7일·7일 초과일 때의 DB 조회와 분배 계획 선별을 고정 시각으로 검사합니다. 경계마다 팀 100개를 만들지 않도록 팀 생성 진입 지점만 관찰하며, 실제 전체 생성은 별도 사례에서 검증합니다. 로컬 `wejo_dev`만 허용하는 원래 `run()`의 보호 조건은 우회하지 않으므로 이 CI 검사는 하위 시드 함수와 트랜잭션 경계의 회귀입니다. `run()` 직접 실행 검증이 필요하면 별도 임시 `wejo_dev` 컨테이너를 준비하고 AI는 호출하지 않습니다.

[분산 데이터셋 검사](../../backend/tests/integration/test_dev_dataset.py)는 공고·일반 계정·프로필·수강 과목·AI 대화 보존, 재구성 롤백, 일반 계정 활동과 미만료 AI 메타데이터의 삭제 거부를 검증합니다. 현재 AI의 구조화 역할 검색 결과도 진단 보고서와 대조합니다. [비밀번호 갱신 검사](../../backend/tests/integration/test_reset_dev_passwords.py)는 UUID·로그인 ID 충돌, 재실행, 기존 세션 보존, 느린 해시 처리 중 연결 유지와 전체 롤백을 다룹니다. 실제 개발 DB나 외부 모델을 사용하지 않습니다.

## 단계별 CI

`ci.yml`에서 선택된 프론트·백엔드 검사 job을 병렬 실행합니다. 백엔드 검사와 브라우저 통합 검사는 서로 다른 전용 PostgreSQL 17.11 서비스를 사용합니다. 백엔드 검사에서는 `DATABASE_URL`과 `TEST_DATABASE_URL`을 같은 테스트 DB로 지정해 DB 검사가 생략되지 않도록 합니다.

`Integration E2E`는 Ubuntu 24.04를 사용합니다. [Azure APT 미러의 저속 전송 문제](https://github.com/actions/runner-images/issues/14823)를 피하기 위해 공식 runner의 미러 구성을 확인한 뒤 Azure 항목만 제거하고, 기존 HTTPS Ubuntu archive·security 미러를 사용합니다. `playwright install --with-deps chromium`의 패키지·서명 검사와 15분 job 제한은 유지합니다. 설치 시간은 GitHub 실행 로그에서 비교하며, upstream 문제가 해결되면 [CI 설치 안정화 이슈](https://github.com/wejo-team/sku-dreamon/issues/184)에 따라 미러 선택을 재검토합니다.

| 단계 | 검사 |
| --- | --- |
| 프론트 실행 기반 | `npm ci`, ESLint, Prettier check, TypeScript check, production build |
| 프론트 기능·클라이언트 로직 | 현재 HTTP 성공·오류·취소와 연결 화면의 상태·재시도를 Vitest로 검증 |
| 백엔드 실행 기반 | `uv sync --locked`, Ruff lint·format check, mypy, pytest |
| 비동기 DB 기반 | PostgreSQL에서 `alembic upgrade head`, `alembic check`, 연결 검사, 세션 분리·commit·rollback·종료 정리 통합 테스트 |
| 배포 정적 계약 | `Deployment static checks`: 표준 라이브러리 `deploy/tests/test_*.py` 단위 검사와 daemon 없이 Compose 설정 해석. 별도 의존성 설치 없음 |
| DB 모델 도입 | 위 검사에 실제 모델의 migration 적용·조회 테스트 추가 |
| 제품 브라우저 통합 | 앱 변경 PR과 `develop`·`main` push에서 `Integration E2E`: HTTPS·실제 API·격리 DB, 데스크톱/320px Chromium. 로컬도 별도 fixture 또는 개발 DB의 `*_e2e` 복제본에서만 실행 |

운영 컨테이너의 이미지·TLS·앱 교체·DB 보존·짧은 SSE는 [별도 수동 스크립트](container-deployment.md#verification)로 검사합니다. 배포 기반 PR은 기존 앱 CI를 유지하며 새 필수 컨테이너 job을 추가하지 않습니다. CI 변경은 별도 PR로 다룹니다.

- 프론트 검사 명령은 package.json scripts, Python 도구 설정은 pyproject.toml에 모읍니다. README·로컬 실행·CI가 같은 명령을 사용하도록 맞춥니다.
- DB 통합 테스트의 데이터베이스는 운영 환경과 분리합니다. Alembic 적용 후 모델을 실제로 조회할 수 있는지 확인합니다.
- 런타임·도구 버전을 고정하고 lockfile 기반으로 설치합니다. CI에서 의존성을 임의 갱신하지 않습니다.
- workflow는 모든 PR에서 시작하고 아래 영향 범위에 따라 검사 job·step을 선택합니다. workflow 전체에 경로 필터를 걸어 필수 검사가 영구 대기하는 구성을 피합니다.
- 핵심 검사를 `continue-on-error`나 테스트 없음 허용 설정으로 숨기지 않습니다. 필수 검사와 선택 검사를 구분합니다.
- 문서만 변경했다면 링크·내용·차이 검증으로 충분합니다. 관련 없는 전체 앱 테스트를 무조건 반복하지 않습니다.
- 브랜치 보호와 배포는 별도 설정입니다. 적용하지 않은 보호 정책이나 배포를 완료했다고 보고하지 않습니다.

<a id="ci-scope"></a>

## PR 변경 영향 범위

분류 규칙의 실행 원본은 [ci_scope.py](../../scripts/ci_scope.py)입니다. PR 이벤트의 base·head 커밋 공통 조상 이후 **PR 전체 diff**를 확인하고, 파일이 속한 폴더를 기준으로 검사 영역을 선택합니다. 마지막 커밋만 보지 않으며 파일 추가·수정·삭제와 이동 전후 경로를 모두 반영합니다. 여러 영역이 바뀌면 필요한 검사의 합집합을 실행합니다.

| 변경 경로 | PR 검사 범위 |
| --- | --- |
| `frontend/` 내부 코드·설정·의존성 | 프론트 + 브라우저 통합 |
| `backend/` 내부 코드·설정·의존성 | 백엔드 + 브라우저 통합 |
| `backend/Dockerfile` | 백엔드 + 브라우저 통합 + 배포 정적 검사 |
| `deploy/`, `.dockerignore` | 기존 공통 경로의 전체 검사 + 배포 정적 검사 |
| `docs/`, 루트 `README.md`·`AGENTS.md`, 문서 검사 스크립트와 해당 테스트 | 문서 전체 검사 |
| 루트 `package.json`·`package-lock.json`·`.nvmrc` | 문서 전체 검사; 현재 이 파일들은 문서 도구 전용 |
| CI workflow·분류기·공통 설정 등 위 규칙에 없는 경로 | 전체 검사 |

- `PR conventions`의 제목·브랜치 방향 검사와 Python CI·문서 도구 테스트, 문서 원본 링크 검사는 모든 PR에서 실행합니다. 코드 파일 삭제·이동으로도 문서 링크가 깨질 수 있기 때문입니다. [브랜치 검사](../../scripts/check_pr_branch.py)는 작업 PR의 `develop` 대상, 같은 저장소의 `develop` → `main` 릴리스와 `main` → `develop` 동기화를 허용하고 다른 방향은 거부합니다.
- 문서 전체 검사가 선택된 경우에만 Node 의존성 설치·VitePress 빌드·생성 HTML의 링크·앵커·자산 검사를 추가합니다.
- API·스키마 등의 이름에 따른 예외는 두지 않습니다. `backend/` 아래 파일은 백엔드, `frontend/` 아래 파일은 프론트 검사 대상으로 처리합니다. 앱 한쪽만 바뀌어도 브라우저 통합 검사를 실행해 주요 API 계약을 함께 검증합니다. 공통 코드·도구 의존성이 생겨 분류 기준을 바꾸면 규칙과 테스트도 함께 갱신합니다.
- 빈 diff는 보수적으로 전체 검사합니다. 이벤트·커밋·공통 조상을 확인할 수 없는 경우에는 판별을 실패시킵니다. 외부 PR의 파일명·본문을 셸 명령으로 실행하지 않습니다.
- 배포 정적 검사는 배포·공통 설정 변경 PR과 `develop`·`main` push에서 실행합니다. 일반 프론트·백엔드 업무 코드나 문서만 바뀐 PR에서는 생략합니다. 이미지 build·loopback mount·실제 컨테이너 교체·ACME·긴 SSE의 수동 검사 범위는 [컨테이너 검증](container-deployment.md#verification), 운영 이미지 build·배포 경로는 [운영 CD](continuous-deployment.md)에서 구분합니다.

## 필수 검사와 develop·main 검증

- 병합 필수 검사 이름 `Frontend`, `Backend`, `Validate docs`를 유지합니다. `Frontend tests`·`Backend tests`·`Integration E2E`가 실제 검사를 수행하고, 기존 이름의 job은 해당 영역과 브라우저 통합의 최종 결과를 확인합니다. 통합 실패·취소·예상 밖 생략은 두 필수 앱 검사 모두 실패로 처리합니다.
- 앱 필수 검사는 항상 실행해 [check_ci_job.py](../../scripts/check_ci_job.py)로 **범위 판별 성공 + 필요한 검사 성공** 또는 **범위 판별 성공 + 영향 없음에 따른 명시적 생략**만 허용합니다. 판별 실패·취소·출력 누락·필요한 검사의 예상 밖 생략은 성공으로 취급하지 않습니다.
- `Backend`는 선택된 `Deployment static checks` 결과도 확인합니다. 실패·취소·예상 밖 생략·범위 출력 누락은 차단합니다. 배포 테스트 디렉터리 누락이나 테스트 0개를 성공으로 처리하지 않습니다.
- `Validate docs`는 같은 분류기를 job 안에서 실행하므로 판별 실패도 필수 검사 실패가 됩니다. 보호 규칙을 해제하거나 이름을 변경할 필요가 없습니다.
- `PR conventions`도 두 보호 브랜치의 필수 검사입니다. 기존 제목 형식과 함께 PR 이벤트의 base·head 이름 및 저장소 ID를 검사합니다. fork의 `develop`으로 `main`에 보내거나, 작업 브랜치를 `main`에 직접 보내는 PR은 실패합니다. 이 검사에는 AWS 권한이나 운영 비밀값이 필요하지 않습니다.
- `develop`과 `main`의 push는 변경 경로와 관계없이 프론트·백엔드·문서·배포 정적 검사를 모두 실행합니다. 수동 문서 workflow도 전체 문서 검사를 실행합니다. Pages 게시와 운영 CD는 `main`만 허용합니다.
- PR의 새 실행은 오래된 실행을 취소합니다. 두 장기 브랜치의 push 검사는 커밋별 concurrency 그룹을 사용해 다른 커밋의 검사와 취소·대기 슬롯을 공유하지 않습니다. PR의 대상 브랜치 변경도 다시 판별하도록 `edited` 이벤트를 처리하므로 제목·본문 수정 시에도 재검사합니다.
- 두 브랜치의 push 검사는 병합 **후** 검증입니다. 최신 대상 브랜치 반영과 PR 필수 검사 조건은 유지하며, 병합 직전 전체 조합 검증을 보장하는 Merge Queue는 이번 범위에 포함하지 않습니다.
- 운영 CD는 `ci.yml`의 `main` push 실행에서 `Frontend`·`Backend` 성공 뒤 재사용 workflow를 호출하며, 배포 도구가 동일 SHA의 `Validate docs` 성공도 확인합니다. AWS OIDC는 `production` environment를 사용하고 이 환경은 `main`만 허용합니다. PR·`develop` 검사에는 운영 배포 권한을 연결하지 않습니다. [운영 CD](continuous-deployment.md)의 실행·검증·복구 범위를 따릅니다.

<a id="design-reference"></a>

<a id="공식-디자인-앱의-수동-확인"></a>

## 삭제한 레퍼런스 앱의 과거 기록

`design-reference/`는 현재 체크아웃에서 삭제했습니다. [삭제 전 소스](https://github.com/wejo-team/sku-dreamon/tree/7f1ac30ddbba4c169582992730fbf51be3de30d7/design-reference)는 초기 디자인 이력으로만 확인합니다. 제품 UI 변경은 `frontend/`의 테스트·빌드·브라우저 검사로 확인하며, 레퍼런스의 수정·동기화·실행은 완료 조건이 아닙니다.

과거 화면을 재현해야 할 때만 삭제 전 커밋을 별도로 체크아웃한 뒤 [이전 인계 기록의 확인 명령](../design/handoff.md#verification-commands)을 사용합니다. 현재 체크아웃에서 해당 앱의 실행 명령을 사용할 수 없습니다. 모의 UI 확인을 제품 인증·API·LLM·동시성 검증의 완료 근거로 사용하지 않습니다.

## PR 완료 확인

변경한 기능의 정상·실패 경로를 확인하고, 필요한 테스트·타입 검사·빌드를 수행합니다. DB/API/UI 계약이 바뀌면 관련 코드와 문서를 함께 갱신합니다. PR에 수행한 검사와 수행하지 못한 검사, 남은 제한을 적습니다.

## 근거

- [uv GitHub Actions 통합](https://docs.astral.sh/uv/guides/integration/github/)
- [FastAPI 비동기 테스트](https://fastapi.tiangolo.com/advanced/async-tests/)
- [Playwright 모바일 에뮬레이션](https://playwright.dev/docs/emulation)
- [GitHub workflow 트리거](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)
