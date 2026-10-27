# 통합테스트와 bug bash

실제 제품 프론트 → HTTPS 프록시 → FastAPI → PostgreSQL을 연결해 확인하는 실행 안내입니다. 검사 원칙·CI는 [테스트·CI](testing.md), 일반 개발 실행은 [로컬 실행](local-development.md)을 따릅니다. [진행 이슈 #162](https://github.com/wejo-team/sku-dreamon/issues/162)에서 실행 결과와 후속 자동화를 추적합니다.

## 무엇을 검증하는가

| 검사 | 실행 대상 | 보장하지 않는 것 |
| --- | --- | --- |
| 프론트 `npm test` | Vitest·컴포넌트·목업 HTTP 계약 | 실제 쿠키·서버·DB 연동 |
| 백엔드 `uv run pytest` | 순수 로직·ASGI·격리 PostgreSQL | 실제 브라우저 UI·프록시 |
| 프론트 `npm run test:e2e` | 실제 HTTPS 브라우저와 서버, 계정별 쿠키, DB 저장 | 실제 LLM·운영 배포·실기기 Safari |
| 팀 bug bash | 아래 수동 시나리오와 실제 기기 | 미실행 시나리오·미구현 AI 연결 |

`VITE_API_MOCK=false`는 비AI 화면을 실제 서버에 연결합니다. 현재 AI 대화와 지원자 AI 검토 UI는 이 설정에서도 모의 응답입니다. 실제 AI 연결은 [#163](https://github.com/wejo-team/sku-dreamon/issues/163), 품질·비용·보존 검증은 [#164](https://github.com/wejo-team/sku-dreamon/issues/164)에서 추적합니다.

## 격리 환경

기존 개발 DB와 함께 사용할 수 있도록 별도 Compose 프로젝트·볼륨·포트를 씁니다. 테스트 대상 커밋을 고정한 작업 폴더에서 실행합니다. 기존 작업 중인 폴더를 강제로 초기화하지 않습니다.

| 대상 | 주소·이름 |
| --- | --- |
| Compose 프로젝트 | `sku-dreamon-bugbash` |
| PostgreSQL | `127.0.0.1:55433`, 사용자/개발 암호 `wejo` |
| 수동·브라우저 검증 DB | 별도 컨테이너의 `wejo_dev` |
| pytest 전용 DB | 같은 컨테이너의 `wejo_test` |
| 백엔드 | `http://127.0.0.1:8011` |
| 프론트·인증 Origin | `https://localhost:5183` |
| 실행 파일·로그·설정 | Git 제외 경로 `.bugbash/`, `frontend/.env.bugbash` |

Node·npm·Python·uv는 [저장소 고정 버전](local-development.md)을 사용합니다. Docker Compose와 OpenSSL도 필요합니다. 셸에 다른 DB 주소나 모델 키를 export했다면 이 전용 셸에서 먼저 해제합니다. `uv --env-file`보다 기존 셸 변수가 우선하기 때문입니다.

```bash
# 저장소 루트, 전용 셸
unset DATABASE_URL TEST_DATABASE_URL OPENAI_API_KEY
python3 scripts/prepare_bugbash.py
POSTGRES_PORT=55433 docker compose -p sku-dreamon-bugbash up -d --wait
# 최초 한 번만. 이미 존재하면 다시 만들지 않습니다.
POSTGRES_PORT=55433 docker compose -p sku-dreamon-bugbash exec -T postgres createdb -U wejo wejo_test
```

[준비 스크립트](../../scripts/prepare_bugbash.py)는 설정·난수 CSRF 키·30일 로컬 인증서·가상 공고 JSON을 만듭니다. DB에는 쓰지 않고 기존 `backend/.env`도 수정하지 않습니다. 재실행해도 기존 bug bash CSRF 키·인증서를 유지합니다. 인증서가 만료되면 이 환경을 종료하고 `.bugbash/localhost.pem`과 `localhost-key.pem`을 함께 제거한 뒤 다시 준비합니다.

가입 시험용 차단 목록은 가상 비밀번호 한 줄이며 운영 차단 목록이 아닙니다. 반복 실행을 위해 이 격리 환경의 가입·로그인 IP·아이디 확인 제한만 1,000으로 설정합니다. 실제 제한 경계는 기본 설정을 사용하는 백엔드 테스트로 검증하며, 이 값을 운영에 복사하지 않습니다. 외부 AI 키는 비워 둡니다.

## 빈 DB 준비와 기본 검사

```bash
cd backend
uv sync --locked

# 자동 테스트용 DB: 현재 head까지 migration을 적용하고 모델과 대조
uv run --env-file ../.bugbash/test.env alembic upgrade head
uv run --env-file ../.bugbash/test.env alembic check
uv run --env-file ../.bugbash/test.env python -m app.core.db.check
uv run --env-file ../.bugbash/test.env pytest

# 브라우저 검증용 DB
uv run --env-file ../.bugbash/backend.env alembic upgrade head
# 빈 환경에서 한 번만 신규 공고를 등록합니다. CLI 재실행은 새 공고를 만듭니다.
uv run --env-file ../.bugbash/backend.env python -m app.cli.contests ../.bugbash/contest.json --apply
uv run --env-file ../.bugbash/backend.env python -m scripts.seed_dev_data --apply
```

준비 시점부터 약 30일간 접수 중인 가상 공고를 사용합니다. 시드 스크립트는 공고를 만들지 않으므로 **공고 등록 → 시드** 순서를 지킵니다. 공고가 만료되면 새 가상 공고 입력을 준비해 신규 등록해야 합니다. `seed_dev_data --apply`는 재실행 시 기존 시드 계정·팀을 덮어쓰지 않습니다.

시드는 학사 94개, 사용자 300명, 조건에 맞는 공고가 있으면 최대 100개 팀과 지원·알림을 준비합니다. 이 학사 목록은 문서 기반 개발 자료이며 공식 운영 원장 검증 완료를 뜻하지 않습니다. 가상 계정은 `devuser001`~`devuser300`, 공개된 개발 비밀번호는 `WejoDev2026!Demo`입니다. 수동 시나리오의 새 팀장·지원자는 기존 소속이 없는 새 계정으로 만들면 기존 시드 활동과 충돌하지 않습니다.

`TEST_DATABASE_URL`이 없으면 pytest의 DB 검사가 생략됩니다. 위 `test.env`를 사용하고 출력의 skip 여부를 확인합니다. 자동 테스트 DB와 브라우저 검증 DB를 바꾸어 사용하지 않습니다.

## 서버 실행

백엔드 터미널:

```bash
cd backend
uv run --env-file ../.bugbash/backend.env uvicorn app.main:app --host 127.0.0.1 --port 8011
```

프론트 터미널:

```bash
cd frontend
npm ci
npm run dev -- --mode bugbash --host 127.0.0.1 --port 5183
```

브라우저에서 `https://localhost:5183`을 엽니다. `/api`는 Vite가 백엔드로 전달합니다. `__Host-`·Secure·HttpOnly 쿠키와 HTTPS Origin 검사를 그대로 사용합니다. 인증서 예외는 전용 로컬 검증 주소에만 적용합니다. 팀원·실기기 공동 검증에는 신뢰된 인증서와 별도 HTTPS 주소가 필요하며 [#165](https://github.com/wejo-team/sku-dreamon/issues/165)에서 준비합니다. `127.0.0.1` 바인딩을 공용 운영 배포로 취급하지 않습니다.

`/health`는 서버 프로세스 확인일 뿐 DB·로그인 정상의 증거가 아닙니다. Network와 서버 로그에서 `/api/v1/catalogs`, `/auth/csrf`, `/auth/login`, `/me`가 실제로 요청되는지도 확인합니다.

## 브라우저 통합테스트

서버 두 개를 위 상태로 실행한 다음 별도 터미널에서 검사합니다. 현재 자동 서버 시작·종료와 CI E2E job은 제공하지 않습니다.

```bash
cd frontend
npx playwright install --with-deps chromium
npm run test:e2e
# 한 프로젝트만 재현할 때
npm run test:e2e -- --project=chromium
npm run test:e2e -- --project=mobile-chromium
# 결과 HTML 보기
npx playwright show-report
```

Linux의 브라우저 시스템 패키지 설치에는 관리자 권한이 필요할 수 있습니다. 이미 패키지가 준비된 환경은 `npx playwright install chromium`만 실행합니다. 저장소에 고정한 Playwright와 브라우저 버전을 맞추며 다른 버전의 실행 파일을 임의로 섞지 않습니다.

[설정](../../frontend/playwright.config.ts)과 [시나리오](../../frontend/e2e/service.spec.ts)는 데스크톱 Chromium과 320px 모바일 Chromium에서 실행합니다. 테스트는 고유 아이디로 가상 사용자를 만들고 팀장·지원자의 브라우저 컨텍스트를 분리합니다. 실패 재시도는 0회로 두어 최초 실패를 숨기지 않습니다. 정상 데이터도 이 격리 DB에 남기므로 다음 실행은 다른 계정을 사용합니다.

| 시나리오 | 확인 내용 | 관련 제품 AC |
| --- | --- | --- |
| 가입·프로필·세션 | UI 가입·초기 프로필·수정·공개·새로고침·쿠키 속성·로그아웃·재로그인 | sprint-1 AC-02·11 |
| 팀 활동 | UI 팀 생성·지원·선발·팀 공간·알림 모두 읽음·취소·자리 반환·접근 종료·명시적 모집 재개 | AC-04·05·07·08 |
| 권한·실제 HTTP | CSRF 누락 거부·비공개 신규 지원 거부·공개 후 접수·동일 ID 재전송·타인 404·지원 팀장 예외·버전 충돌 | AC-05·08·11 |

`test-results/`에 실패 trace·스크린샷 및 성공 시 주요 화면을, `playwright-report/`에 HTML 결과를 남깁니다. 모두 Git에서 제외합니다. trace에는 가상 계정의 인증 요청이 포함될 수 있으므로 원본을 공개 이슈에 첨부하지 않고, 필요한 오류·요청 ID·화면만 확인해 공유합니다. 운영 계정으로 이 스크립트를 실행하지 않습니다.

## 팀 bug bash 진행

1. 대상 커밋·주소·시간·데이터 상태를 고정하고, 팀장 A·지원자 B·관계없는 C의 독립 세션을 준비합니다. 같은 프로필의 일반 탭은 쿠키를 공유합니다.
2. 처음에는 정상 흐름을 따라 가입 → 프로필 → 탐색 → 팀 생성 → 지원 → 선발 → 알림 → 취소를 실행합니다. 각 변경 뒤 새로고침·상대 계정 조회로 서버 저장까지 확인합니다.
3. 아래 경계 사례와 실제 기기를 나누어 확인합니다. 테스트하지 않은 항목은 미확인으로 남깁니다.
4. 재현 가능한 문제는 이슈로 등록하고, 환경 설정 오류·이미 추적 중인 미구현 기능·정책 대기를 구분합니다.

| 수동 확인 | 기대 결과 |
| --- | --- |
| 목록 검색·필터·페이지·상세 복귀 | 조건·총원·현재 페이지가 맞고 상세 복귀 시 유지 |
| 프로필 비공개 전환 | 일반 사람 탐색에서는 숨김, 기존 지원·소속과 지원 팀장의 최신 프로필 조회는 유지 |
| 마감·정원 충족·모집 종료/재개 | 신규 지원 제한, 여석 반환만으로 자동 재개하지 않음 |
| 다른 팀의 지원자·팀 공간 URL | 관계에 맞는 403/404, 비공개 정보 미노출 |
| 두 탭 수정·연타·느린 응답·응답 유실 | 버전 충돌 안내, 같은 생성 시도 중복 저장 없음 |
| 새로고침·만료·계정 전환 | 현재 세션과 캐시 일치, 다른 계정 정보 잔류 없음 |
| 모바일 실제 기기 | 키보드·스크롤·뒤로가기·하단 버튼·외부 링크·알림 닫기 |
| AI 화면 | 모의/실제 구분. #163 완료 전 실제 AI 통합 성공으로 기록하지 않음 |

이슈에는 **커밋·주소 / 역할·브라우저 / 재현 순서 / 기대·실제 결과 / HTTP 상태·오류 코드·requestId / 화면 / 심각도**를 적습니다. 인증 쿠키·키·실제 사용자 정보는 제외합니다. P0는 데이터 유실·권한 누출 등 즉시 중단 대상, P1은 핵심 흐름 차단, P2는 우회 가능한 기능 오류, P3는 경미한 표시 문제로 분류합니다.

종료 기준은 합의한 핵심 흐름 통과, P0/P1 미해결 0건, 나머지 발견 항목의 담당·재현 근거 기록입니다. 로컬 일부 시나리오 통과를 전체 제품 AC나 실제 배포 완료로 확대하지 않습니다. 학교 인증·사용자 채팅·과거 AI 대화 복원·팀장 위임 등 MVP 제외 사항은 필수 결함으로 등록하지 않습니다.

## 자주 막히는 부분

| 증상 | 확인할 것 |
| --- | --- |
| 서버 로그에 요청이 없는데 화면은 동작 | `--mode bugbash`, `VITE_API_MOCK=false`, 이전 Vite 프로세스 여부 |
| 로그인/쓰기 403 | HTTPS 주소·Origin 일치·CSRF 쿠키/헤더·세션 전환 후 토큰 갱신 |
| 가입 503 | CSRF 키, 비어 있지 않은 차단 목록 파일·버전. 기존 계정 로그인 성공만으로 가입 준비 완료 아님 |
| 환경 파일에서 Origin JSON 오류 | `AUTH_ALLOWED_ORIGINS='["https://localhost:5183"]'`처럼 JSON 전체를 작은따옴표로 감쌈 |
| 공고/팀 목록이 비어 있음 | migration은 자료 적재가 아님. 공고 등록 뒤 시드 실행, 실제 시각의 접수 기간 확인 |
| DB 테스트가 skipped | `test.env`의 `TEST_DATABASE_URL`과 DB 접근 확인 |
| Chromium 시작 실패 | 고정 버전 브라우저와 Linux 시스템 라이브러리 설치 여부 |

## 2026-10-26 실행 기록

대상 제품 코드는 리모트 `main` **`53c0003`**입니다. 별도 `test/integration-bugbash` 작업 폴더에서 테스트 도구·문서를 추가했으며 제품 구현은 변경하지 않았습니다. 기존 개발 컨테이너의 55432 포트와 별도로 PostgreSQL 17.11의 55433 포트를 사용했습니다.

- 빈 `wejo_test`: 8개 migration 적용, `alembic check`, 백엔드 **681개 통과**, DB 검사 생략 없음.
- 별도 `wejo_dev`: 가상 공고 1개, 학사 94개, 사용자 300명, 팀 100개, 지원 1,200건을 적재했습니다. 브라우저 검사가 추가한 계정·팀은 별도입니다.
- 실제 HTTPS E2E: 데스크톱 Chromium·320px 모바일 Chromium에서 각각 3개, **총 6개 통과**. 가입·프로필·쿠키·계정별 팀 활동·알림 UI·모집 재개·권한 종료와 HTTP 오류 경계를 확인했습니다. 두 주요 화면의 가로 넘침도 검사했습니다.
- 개발 시드 재실행은 새 사용자·팀 각각 0건으로 기존 시드를 보존했습니다.
- 프론트 Vitest **22개 파일·345개 통과**, ESLint·Prettier·TypeScript·production build 통과. 백엔드 Ruff·format·mypy도 통과했습니다. 제품 bundle 크기 경고는 남아 있으며 빌드 실패는 아닙니다.
- 실제 모델 호출·운영 배포·실기기·WebKit·모든 실제/시연 데이터 조합은 이번 검증의 완료 범위가 아닙니다. 동시성·롤백 경계는 기존 PostgreSQL 테스트에서 확인합니다.

이번 Linux 호스트에서는 관리자 권한 설치 대신 이미 준비된 로컬 브라우저 라이브러리 경로를 프로세스의 `LD_LIBRARY_PATH`에 지정했습니다. 제품의 인증·API를 우회하지 않았으며 일반 재현 환경은 위 `install --with-deps` 절차를 따릅니다.

## 종료와 데이터 유지

프론트·백엔드는 실행 터미널에서 Ctrl+C로 종료합니다. DB는 아래 명령으로 멈추며 테스트 볼륨을 유지합니다. 기존 개발 컨테이너에는 영향을 주지 않습니다.

```bash
POSTGRES_PORT=55433 docker compose -p sku-dreamon-bugbash stop
```

## 참고

- [Playwright 브라우저 컨텍스트 격리](https://playwright.dev/docs/browser-contexts)
- [Playwright 브라우저·시스템 의존성 설치](https://playwright.dev/docs/browsers)
- [Playwright trace 확인](https://playwright.dev/docs/trace-viewer)
