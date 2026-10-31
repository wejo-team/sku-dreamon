# 통합테스트와 bug bash

실제 제품 프론트 → HTTPS 프록시 → FastAPI → PostgreSQL을 연결해 확인하는 실행 안내입니다. 검사 원칙·CI는 [테스트·CI](testing.md), 일반 개발 실행은 [로컬 실행](local-development.md)을 따릅니다. [초기 통합 검증 #162](https://github.com/wejo-team/sku-dreamon/issues/162)의 실행 안내를 바탕으로, 반복 점검의 최종 실행 커밋·결과·후속 조치는 [#169](https://github.com/wejo-team/sku-dreamon/issues/169)에서 추적합니다.

## 무엇을 검증하는가

| 검사 | 실행 대상 | 보장하지 않는 것 |
| --- | --- | --- |
| 프론트 `npm test` | Vitest·컴포넌트·목업 HTTP 계약 | 실제 쿠키·서버·DB 연동 |
| 백엔드 `uv run pytest` | 순수 로직·ASGI·격리 PostgreSQL | 실제 브라우저 UI·프록시 |
| 프론트 `npm run test:e2e` | 실제 HTTPS 브라우저와 서버, 계정별 쿠키, DB 저장 | 실제 LLM·운영 배포·실기기 Safari |
| 팀 bug bash | 아래 수동 시나리오와 실제 기기 | 미실행 시나리오·운영 배포 |

`VITE_API_MOCK=false`는 AI를 포함한 제품 화면을 실제 서버에 연결합니다. `VITE_API_MOCK=true`의 모의 대화와 구분합니다. 기본 E2E는 모델 키 없이 비AI 흐름을 검사하고, 아래 AI 전용 E2E는 모델 드라이버만 결정적인 시험 구현으로 대체합니다. 실제 제공자 응답·품질·비용·보존 검증은 [#164](https://github.com/wejo-team/sku-dreamon/issues/164)의 별도 범위입니다.

<a id="isolated-environment"></a>

## 격리 환경

개발 DB는 준비된 데이터셋과 직접 편집한 자료를 유지합니다. 자동테스트는 [테스트 전용 Compose](../../compose.test.yaml)의 별도 컨테이너·포트를 사용하며 개발 DB에 쓰지 않습니다. PostgreSQL 데이터 디렉터리는 `tmpfs`라 영구 볼륨을 만들지 않고 컨테이너 중지·재시작 시 사라집니다. 테스트 대상 커밋을 고정한 작업 폴더에서 실행합니다.

PostgreSQL 17 이미지는 볼륨 설정을 생략해도 익명 볼륨을 만들 수 있으므로 `tmpfs`를 명시합니다. [이미지 저장소 안내](https://hub.docker.com/_/postgres)와 [Docker tmpfs](https://docs.docker.com/engine/storage/tmpfs/)를 참고합니다. 메모리 최대 크기는 1GiB이며 중지 전에 필요한 로그·보고서를 `.bugbash/`에 보관합니다. 개발용 [compose.yaml](../../compose.yaml)의 영구 볼륨은 유지합니다. 두 Compose 파일을 `-f`로 함께 병합하지 않습니다.

| 대상 | 주소·이름 |
| --- | --- |
| Compose 프로젝트 | `sku-dreamon-tests` |
| PostgreSQL | `127.0.0.1:55433`, 사용자/개발 암호 `wejo` |
| 수동·브라우저 검증 DB | 별도 컨테이너의 `wejo_e2e` |
| pytest 전용 DB | 같은 컨테이너의 `wejo_test` |
| 백엔드 | `http://127.0.0.1:8013` |
| 프론트·인증 Origin | `https://localhost:5185` |
| 실행 파일·로그·설정 | Git 제외 경로 `.bugbash/`, `frontend/.env.bugbash` |

Node·npm·Python·uv는 [저장소 고정 버전](local-development.md)을 사용합니다. Docker Compose와 OpenSSL도 필요합니다. 셸에 다른 DB 주소나 모델 키를 export했다면 이 전용 셸에서 먼저 해제합니다. `uv --env-file`보다 기존 셸 변수가 우선하기 때문입니다.

```bash
# 저장소 루트, 전용 셸
unset DATABASE_URL TEST_DATABASE_URL OPENAI_API_KEY
python3 scripts/prepare_bugbash.py --database-name wejo_e2e
docker compose -f compose.test.yaml up -d --wait
# wejo_e2e는 컨테이너가 만듭니다. pytest DB는 새 컨테이너를 준비할 때 생성합니다.
docker compose -f compose.test.yaml exec -T postgres createdb -U wejo wejo_test
```

[준비 스크립트](../../scripts/prepare_bugbash.py)는 설정·난수 CSRF 키·30일 로컬 인증서와 별도 입력 CLI용 공고 JSON을 만듭니다. 기본 E2E는 아래 전용 13개 공고 시드를 사용합니다. DB에는 쓰지 않고 기존 `backend/.env`도 수정하지 않습니다. 재실행해도 기존 bug bash CSRF 키·인증서를 유지합니다. 인증서가 만료되면 이 환경을 종료하고 `.bugbash/localhost.pem`과 `localhost-key.pem`을 함께 제거한 뒤 다시 준비합니다.

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
# 비어 있는 *_e2e 환경에 한 번만 전체 fixture를 적재합니다.
uv run --env-file ../.bugbash/backend.env python -m scripts.seed_e2e_data --apply
```

전용 E2E 시드는 준비 시점 기준 접수 중 11개·마감 1개·예정 1개 공고와 계정·팀을 한 트랜잭션으로 준비합니다. 비어 있지 않은 DB에 재실행하면 거부하며, 테스트 자료를 최신 날짜로 준비하려면 테스트 컨테이너를 새로 준비하거나 별도의 빈 `*_e2e` DB를 사용합니다. 기존 개발 자료의 `seed_dev_data --apply`는 [로컬 실행](local-development.md)의 `wejo_dev` 전용 명령이며 기존 시드 계정·팀을 덮어쓰지 않습니다.

E2E 시드는 학사 94개, 사용자 300명, 팀 66개와 지원·알림을 준비합니다. 팀 수는 개발 데이터의 분산 계획을 따르며, 현재 접수 중 11개 공고에 공고당 최대 6팀을 배정합니다. 13개 공고의 페이지 경계와 팀·사람 탐색, 역할·지원 상태 사례를 함께 유지합니다. 이 학사 목록은 문서 기반 개발 자료이며 공식 운영 원장 검증 완료를 뜻하지 않습니다. 가상 계정은 `devuser001`~`devuser300`, 공개된 개발 비밀번호는 `WejoDev2026!Demo`입니다. 수동 시나리오의 새 팀장·지원자는 기존 소속이 없는 새 계정으로 만들면 기존 시드 활동과 충돌하지 않습니다.

`TEST_DATABASE_URL`이 없으면 pytest의 DB 검사가 생략됩니다. 위 `test.env`를 사용하고 출력의 skip 여부를 확인합니다. pytest는 명시적 localhost `*_test`, 브라우저 검증은 `*_e2e`만 허용합니다. 개발 DB나 원격 주소는 연결 전에 거부합니다.

## 서버 실행

백엔드 터미널:

```bash
cd backend
uv run --env-file ../.bugbash/backend.env uvicorn app.main:app --host 127.0.0.1 --port 8013
```

프론트 터미널:

```bash
cd frontend
npm ci
npm run dev -- --mode bugbash --host 127.0.0.1 --port 5185
```

브라우저에서 `https://localhost:5185`를 엽니다. `/api`는 Vite가 백엔드로 전달합니다. `__Host-`·Secure·HttpOnly 쿠키와 HTTPS Origin 검사를 그대로 사용합니다. 인증서 예외는 전용 로컬 검증 주소에만 적용합니다. 팀원·실기기 공동 검증에는 신뢰된 인증서와 별도 HTTPS 주소가 필요하며 [#165](https://github.com/wejo-team/sku-dreamon/issues/165)에서 준비합니다. `127.0.0.1` 바인딩을 공용 운영 배포로 취급하지 않습니다.

`/api/v1/health`는 서버 프로세스 확인일 뿐 DB·로그인 정상의 증거가 아닙니다. Network와 서버 로그에서 `/api/v1/catalogs`, `/auth/csrf`, `/auth/login`, `/me`가 실제로 요청되는지도 확인합니다.

## 브라우저 통합테스트

준비된 DB·환경 파일·인증서가 있으면 아래 실행기로 서버 시작·준비 확인·E2E·종료를 한 번에 수행합니다. 최초 실행 전에는 프론트 의존성과 브라우저도 설치합니다. Linux/macOS/WSL용이며 이미 사용 중인 IPv4/IPv6 포트는 거부합니다. 위의 수동 서버가 실행 중이면 종료하거나 자동 실행기에 다른 포트를 지정합니다. 실행기가 시작한 서버만 종료하며 테스트 컨테이너는 다음 명시적 초기화까지 유지합니다.

```bash
# 최초 준비: 저장소 루트에서 시작
cd frontend
npm ci
npx playwright install --with-deps chromium
cd ..

python3 scripts/run_bugbash.py
# 별도 *_e2e 복제 DB와 추가 포트로 실행할 때
python3 scripts/run_bugbash.py --backend-env .bugbash/copy-e2e/backend.env --backend-port 8014 --frontend-port 5186
# 한 프로젝트나 시나리오만 실행할 때
python3 scripts/run_bugbash.py -- --project=chromium
```

`--backend-env`에는 명시적 localhost `*_e2e`의 `DATABASE_URL`, CSRF 키, 비밀번호 차단 목록 등 가입 준비 설정을 넣습니다. 실행기는 셸의 DB·모델 키·검증 플래그를 제거하고 실제 앱 설정과 대상 DB가 같은지 확인합니다. 개발 DB는 모든 모드에서 거부합니다. 인증 Origin과 프록시는 선택한 포트로 고정하며, health·카탈로그·공고 목록·CSRF가 준비된 뒤 검증 정보를 자식 Playwright에만 전달합니다. `.bugbash/runs/<실행 시각>/`에 서버 로그·HTML·JSON·생성 자원 manifest를 남깁니다.

검증 정보를 받지 않은 `npm run test:e2e` 직접 실행은 브라우저 요청 전에 실패합니다. 재현에도 위 실행기를 사용합니다. 실행이 끝난 보고서는 별도 서버 없이 볼 수 있습니다.

```bash
cd frontend
# 결과 HTML 보기
npx playwright show-report
```

Linux의 브라우저 시스템 패키지 설치에는 관리자 권한이 필요할 수 있습니다. 이미 패키지가 준비된 환경은 `npx playwright install chromium`만 실행합니다. 저장소에 고정한 Playwright와 브라우저 버전을 맞추며 다른 버전의 실행 파일을 임의로 섞지 않습니다.

[설정](../../frontend/playwright.config.ts)과 [시나리오](../../frontend/e2e/service.spec.ts)는 데스크톱 Chromium과 320px 모바일 Chromium에서 실행합니다. 테스트는 고유 아이디로 가상 사용자를 만들고 팀장·지원자의 브라우저 컨텍스트를 분리합니다. 실행기가 `E2E_BASE_URL`과 `E2E_ARTIFACT_DIR`을 설정합니다. 테스트 DB의 기존 fixture를 읽고 실행별 임시 자원을 만들며, 생성 직후 종류·UUID·실행 ID를 manifest에 기록합니다. 실패 재시도는 0회입니다. 임시 자료는 테스트 DB에만 남고 개발 화면에는 나타나지 않습니다.

테스트 데이터를 초기화할 때는 아래 명령으로 **테스트 컨테이너만** 없애고 이 문서의 DB 준비·migration·시드를 다시 실행합니다. `tmpfs`는 단순 `stop`·`restart`에도 비워지므로 재시작 후 같은 준비가 필요합니다. 개발 Compose의 `down -v`나 원본 DB 복원은 사용하지 않습니다.

```bash
docker compose -f compose.test.yaml down
docker compose -f compose.test.yaml up -d --wait
```

### 과거 개발 DB 테스트 잔여물 정리

[정리 도구](../../backend/scripts/cleanup_e2e_data.py)는 과거 생성 기록이 남은 로컬 `wejo_dev`에만 사용하는 일회성 보조 명령입니다. 일반 시드 실행·E2E 종료가 이 도구를 자동 호출하지 않습니다. 새 테스트 자료는 테스트 컨테이너를 초기화해 정리합니다.

먼저 개발 DB의 custom-format `pg_dump` 백업을 만들고 별도 DB에 복원되는지 확인합니다. 대상은 `resources.json`의 `created: true` UUID와 생성 기록으로 확인합니다. 오래된 실행은 전후 기록·실행 시각·전체 행 해시 등을 개별 대조한 근거가 필요하며 이름 접두사만으로 선택하지 않습니다. `Manifest`에는 계정·팀의 정확한 UUID, 현재 로그인 ID·팀명, 근거 파일의 SHA-256·JSON pointer를 기록합니다. 실제 자료·백업·계획은 `.bugbash/`에만 저장하고 커밋하지 않습니다.

```bash
# 명시적 개발 DB DATABASE_URL을 설정한 백엔드 전용 셸
uv run python -m scripts.cleanup_e2e_data \
  --manifest ../.bugbash/cleanup/manifest.json \
  --backup ../.bugbash/cleanup/wejo_dev.dump \
  --output ../.bugbash/cleanup/plan.json
# dry-run 결과와 복원 DB 검증이 끝난 정확한 계획만 적용
uv run python -m scripts.cleanup_e2e_data --apply ../.bugbash/cleanup/plan.json
```

기본 명령은 계획만 저장하고 DB를 바꾸지 않습니다. apply는 시드 ID, 사용자와 연결된 범위 밖 지원·소속·알림·AI 실행, 계획 이후 수정, 변경된 근거·백업을 거부합니다. FK를 끄거나 개발 DB 전체를 초기화하지 않고 승인된 계정·팀에 속한 행만 한 트랜잭션에서 제거합니다. `transaction_ready` 영수증은 커밋 완료 증거가 아니며 성공 출력과 적용 후 보존 검사를 함께 확인합니다.

직접 사용한 지원이 연결됐다면 기본적으로 중단합니다. 사용자가 그 지원의 삭제를 개별 승인한 경우에만 manifest의 `retainedAccountApplications`에 지원·계정·팀 UUID를 정확히 기록할 수 있습니다. 최초 `submitted` 상태의 해당 지원과 발생 이벤트·알림만 포함하며 계정·프로필은 보존합니다. 선발·소속·AI 참조 또는 승인하지 않은 추가 지원이 있으면 계속 거부합니다.

기본 시나리오는 [서비스 흐름](../../frontend/e2e/service.spec.ts) 3개, [탐색·공고](../../frontend/e2e/browse.spec.ts) 3개, [생명주기·오류 회복](../../frontend/e2e/lifecycle.spec.ts) 4개를 두 브라우저 프로젝트에서 실행하는 **20개 구성**입니다([#188](https://github.com/wejo-team/sku-dreamon/pull/188) 반영). 복제 DB의 혼합 검사는 명시적으로 선택한 별도 8개이며 기본 20개에 포함되지 않습니다. 아래 과거 실행 기록의 6·10·16개는 당시 커밋의 구성입니다. 구성 개수가 실행 성공을 뜻하지 않으며, 실제 수집·통과·실패·생략·재시도는 실행별 JSON 결과를 확인합니다.

| 시나리오 | 확인 내용 | 관련 제품 AC |
| --- | --- | --- |
| 가입·프로필·세션 | UI 가입·초기 프로필·수정·공개·새로고침·쿠키 속성·로그아웃·재로그인 | sprint-1 AC-02·11 |
| 팀 활동 | UI 팀 생성·지원·선발·팀 공간·알림 모두 읽음·취소·자리 반환·접근 종료·명시적 모집 재개 | AC-04·05·07·08 |
| 탐색·공고 계약 | API 목록 대조·검색·필터 취소·페이지 경계·상세 복귀·공식/수집 출처·미확인·시각 보완·마감 공고 | sprint-1 AC-14, contests AC-04·09·11·13 |
| 지원 생명주기·알림 | 취소 후 새 지원·검토·미선발·재지원 제한·다른 팀 선발 시 대기 지원 폐기·읽음 처리와 현재 권한 | team AC-16·36·37·40·42·44, notifications AC-01·02·05·08 |
| 권한·실제 HTTP | CSRF 누락 거부·비공개 신규 지원 거부·공개 후 접수·동일 ID 재전송·타인 404·지원 팀장 예외·버전 충돌 | AC-05·08·11 |
| 세션 회수·알림 조회 실패 | 실제 로그아웃으로 세션 회수 후 401·개인 화면 숨김·재로그인 안내. 브라우저에서 알림 GET 503을 주입한 뒤 필터·개수·재시도·실제 서버 복구 확인 | [인증 실패](../specs/authentication.md#auth-failures), [알림](../specs/notifications.md) |

`test-results/`에 실패 trace·스크린샷 및 성공 시 주요 화면을, `playwright-report/`에 HTML 결과를 남깁니다. 모두 Git에서 제외합니다. trace에는 가상 계정의 인증 요청이 포함될 수 있으므로 원본을 공개 이슈에 첨부하지 않고, 필요한 오류·요청 ID·화면만 확인해 공유합니다. 운영 계정으로 이 스크립트를 실행하지 않습니다.


<a id="ai-e2e"></a>

## AI 화면의 브라우저 통합

AI 전용 검사는 [브라우저 시나리오](../../frontend/e2e/ai.spec.ts)와 [시험 서버 factory](../../backend/tests/e2e_ai_app.py)를 사용합니다. 실제 HTTPS·인증 쿠키·CSRF·AI 라우터·SSE·DB 조회 도구·결과 검증·대화 저장을 통과하고, 모델의 계획·답변 생성만 가상 구현으로 대체합니다. 실제 제공자 요청은 0회이며 결과 품질·지연·비용 평가는 포함하지 않습니다.

```bash
# 앞 절에서 준비한 로컬 *_e2e DB와 빈 OPENAI_API_KEY 설정
python3 scripts/run_bugbash.py --ai-fixture
# 다른 격리 DB/포트를 사용할 때
python3 scripts/run_bugbash.py --ai-fixture --backend-env .bugbash/mixed-e2e/backend.env --backend-port 8023 --frontend-port 5195
```

`--ai-fixture`는 별도 `tests.e2e_ai_app:create_app`을 실행하고 AI 시나리오만 선택합니다. localhost의 이름이 `_e2e`로 끝나는 DB, 명시적 시험 플래그, 비어 있는 모델 키를 모두 요구합니다. 원본 `wejo_dev`에는 이 시험 드라이버를 사용하지 않습니다. 제품 서버의 설정이나 AI 라우트에는 시험 모드를 추가하지 않았습니다.

대화·공개 철회 뒤 전체 결과 폐기, 실패 후 원입력 재시도·중단, 팀장 개별 검토·실제 지원자 추천을 데스크톱과 320px Chromium에서 검사합니다. 기존 기본 E2E와 AI E2E는 별도 실행·보고서로 보관합니다. 결과 파일과 생성 자원은 실행기 manifest에 남습니다.

## 기존 개발 DB와 CI 자료의 구분

공고는 고정 UUID나 제목으로 선택하지 않습니다. API에서 접수 중·2명 팀 허용·검사 종료까지 충분한 시간이 남은 공고를 선택하고, 모집 마감은 공고 마감 이내로 계산합니다. 탐색 검증에는 2페이지 이상 공고, 공개 사람·팀 목록과 미확인/수집 출처/시작 시각 보완/마감 공고 사례가 필요합니다. 필요한 자료가 없으면 사전 조건 실패로 기록하며 임의 공고 생성이나 skip으로 대체하지 않습니다.

CI는 매번 빈 `wejo_e2e`를 만들고 [E2E 시드](../../backend/scripts/seed_e2e_data.py)로 공고 계약 사례 8개와 페이지 이동용 5개, 총 13개 공고 및 기존 개발 시드의 계정·팀을 준비합니다. 공모전 12개 페이지와 마지막 1개 페이지를 함께 검증합니다. 이 도구는 명시적 `--apply`, localhost의 `*_e2e` DB, 비어 있는 업무 테이블을 요구합니다. 공고·계정·팀·지원·알림은 한 트랜잭션으로 적재하며 중간 실패 시 모두 롤백합니다. 원본 개발 공고 490개를 넣는 도구가 아니며 개발 DB 복제본의 회귀 검증을 대체하지 않습니다. CI에서 생성한 가상 자료만 사용하고 모델 키·원본 개발 DB 자료는 가져오지 않습니다. CI HTML/JSON·스크린샷·trace는 `integration-e2e` artifact에 1일 보관하며 환경 파일·키·DB 덤프는 업로드하지 않습니다.

```bash
# 새로운 격리 E2E DB를 준비할 때만 사용
python3 scripts/prepare_bugbash.py --database-name wejo_e2e
cd backend
uv run --env-file ../.bugbash/backend.env alembic upgrade head
uv run --env-file ../.bugbash/backend.env python -m scripts.seed_e2e_data --apply
```

이미 `.bugbash/backend.env`가 있으면 준비 스크립트는 다른 DB 설정으로 덮어쓰지 않습니다. 과거 `wejo_dev` 설정은 자동테스트에 사용할 수 없으므로 별도로 보관하고 새 `*_e2e` 설정을 준비합니다. 다른 테스트 DB 포트가 필요하면 Compose의 `TEST_POSTGRES_PORT`와 준비 스크립트의 `--database-port`를 같은 값으로 지정합니다.

## 실제·시연 네 조합

기본 검사는 새 자원끼리 쓰고 기존 자료는 읽습니다. 기존 시연 계정·팀에 지원·선발하는 네 조합 검사는 개발 DB의 **별도 복제본**에서만 추가 실행합니다. 복제본은 localhost의 `*_e2e` 이름을 사용하고, 원본 DB를 지우거나 복원하지 않습니다.

```bash
# 복제 DB를 가리키는 환경 파일과 기존 인증서가 준비된 상태
E2E_MIXED_DATA=1 \
E2E_MIXED_DATABASE_URL=postgresql+asyncpg://wejo:wejo@127.0.0.1:55433/wejo_quality_e2e \
python3 scripts/run_bugbash.py --backend-env .bugbash/mixed-e2e/backend.env --backend-port 8014 --frontend-port 5186 -- mixed-data.spec.ts
```

실행기는 후보 조회 DB와 서버 DB가 같은지 검사합니다. [후보 선택기](../../backend/scripts/prepare_mixed_e2e.py)는 읽기 전용으로 고정 시연 UUID 목록과 현재 모집·소속·지원 상태를 확인하며, 이름 접두사로 `isDemo`를 추정하지 않습니다. 실제→실제, 실제→시연, 시연→실제, 시연→시연 각각 지원·선발·결과·팀 공간·취소 후 권한 회수를 검증합니다. 기존 시연 자료가 변경되므로 원본 DB에서 이 모드를 실행하지 않습니다. 시연 공고 UUID 목록은 현재 비어 있어 이 네 조합은 계정×팀 기준입니다.

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
| AI 화면 | 실제 API 연결·시험 모델 E2E·실제 제공자 검증을 구분. 자동 E2E 결과를 추천 품질의 근거로 사용하지 않음 |

이슈에는 **커밋·주소 / 역할·브라우저 / 재현 순서 / 기대·실제 결과 / HTTP 상태·오류 코드·requestId / 화면 / 심각도**를 적습니다. 인증 쿠키·키·실제 사용자 정보는 제외합니다. P0는 데이터 유실·권한 누출 등 즉시 중단 대상, P1은 핵심 흐름 차단, P2는 우회 가능한 기능 오류, P3는 경미한 표시 문제로 분류합니다.

종료 기준은 합의한 핵심 흐름 통과, P0/P1 미해결 0건, 나머지 발견 항목의 담당·재현 근거 기록입니다. 로컬 일부 시나리오 통과를 전체 제품 AC나 실제 배포 완료로 확대하지 않습니다. 학교 인증·사용자 채팅·과거 AI 대화 복원·팀장 위임 등 MVP 제외 사항은 필수 결함으로 등록하지 않습니다.

## 자주 막히는 부분

| 증상 | 확인할 것 |
| --- | --- |
| 서버 로그에 요청이 없는데 화면은 동작 | `--mode bugbash`, `VITE_API_MOCK=false`, 이전 Vite 프로세스 여부 |
| 로그인/쓰기 403 | HTTPS 주소·Origin 일치·CSRF 쿠키/헤더·세션 전환 후 토큰 갱신 |
| 가입 503 | CSRF 키, 비어 있지 않은 차단 목록 파일·버전. 기존 계정 로그인 성공만으로 가입 준비 완료 아님 |
| 환경 파일에서 Origin JSON 오류 | `AUTH_ALLOWED_ORIGINS='["https://localhost:5185"]'`처럼 JSON 전체를 작은따옴표로 감쌈 |
| 공고/팀 목록이 비어 있음 | migration은 자료 적재가 아님. 공고 등록 뒤 시드 실행, 실제 시각의 접수 기간 확인 |
| DB 테스트가 skipped | `test.env`의 `TEST_DATABASE_URL`과 DB 접근 확인 |
| Chromium 시작 실패 | 고정 버전 브라우저와 Linux 시스템 라이브러리 설치 여부 |

## 과거 실행 기록의 해석

아래 기록에는 당시 허용했던 개발 DB 직접 실행이 포함됩니다. [#197](https://github.com/wejo-team/sku-dreamon/issues/197) 이후 자동테스트는 격리 DB에서만 실행합니다. 기록의 이전 명령·데이터 유지 방식은 현재 실행 지침이 아닙니다.

## 2026-10-26 실행 기록

대상 제품 코드는 리모트 `main` **`53c0003`**입니다. 별도 `test/integration-bugbash` 작업 폴더에서 테스트 도구·문서를 추가했으며 제품 구현은 변경하지 않았습니다. 기존 개발 컨테이너의 55432 포트와 별도로 PostgreSQL 17.11의 55433 포트를 사용했습니다.

- 빈 `wejo_test`: 8개 migration 적용, `alembic check`, 백엔드 **681개 통과**, DB 검사 생략 없음.
- 별도 `wejo_dev`: 가상 공고 1개, 학사 94개, 사용자 300명, 팀 100개, 지원 1,200건을 적재했습니다. 브라우저 검사가 추가한 계정·팀은 별도입니다.
- 실제 HTTPS E2E: 데스크톱 Chromium·320px 모바일 Chromium에서 각각 3개, **총 6개 통과**. 가입·프로필·쿠키·계정별 팀 활동·알림 UI·모집 재개·권한 종료와 HTTP 오류 경계를 확인했습니다. 두 주요 화면의 가로 넘침도 검사했습니다.
- 개발 시드 재실행은 새 사용자·팀 각각 0건으로 기존 시드를 보존했습니다.
- 프론트 Vitest **22개 파일·345개 통과**, ESLint·Prettier·TypeScript·production build 통과. 백엔드 Ruff·format·mypy도 통과했습니다. 제품 bundle 크기 경고는 남아 있으며 빌드 실패는 아닙니다.
- 실제 모델 호출·운영 배포·실기기·WebKit·모든 실제/시연 데이터 조합은 이번 검증의 완료 범위가 아닙니다. 동시성·롤백 경계는 기존 PostgreSQL 테스트에서 확인합니다.

이번 Linux 호스트에서는 관리자 권한 설치 대신 이미 준비된 로컬 브라우저 라이브러리 경로를 프로세스의 `LD_LIBRARY_PATH`에 지정했습니다. 제품의 인증·API를 우회하지 않았으며 일반 재현 환경은 위 `install --with-deps` 절차를 따릅니다.

## 2026-10-28 개발 DB 회귀 기록

기존 개발 DB의 공고 490개를 사용한 검사에서 공고 상세 DTO 불일치를 재현했습니다. [#170](https://github.com/wejo-team/sku-dreamon/pull/170)으로 수정한 main `63ba9a6`에서 기존 데스크톱/320px 모바일 10개 검사가 병합 전·후 모두 통과했습니다. 해당 main의 앱·문서 CI도 통과했습니다.

후속 자동화는 기존 DB 탐색 경계·출처 표시·지원 생명주기·알림을 포함한 기본 16개로 확장했습니다. 기존 개발 DB에서는 12개 통과 후 테스트 선택자 두 곳을 수정해 나머지 4개를 재검증했습니다. CI와 같은 새 DB의 공고 8개·계정 300개·팀 100개에서는 16개를 한 번에 통과했습니다. 개발 DB 복제본의 실제/시연 계정×팀 네 조합도 두 화면 크기에서 8개 모두 통과했습니다. 재시도 설정은 0회이며 생략한 검사는 없습니다.

- 기존 개발 공고·계정·팀·지원 등 도메인 행의 해시가 보존됐습니다. 새 테스트 자원은 실행별 manifest로 식별하며 DB에 남겨 둡니다.
- 새 CI 시드에서 공고 8개와 계정 300개를 쓴 뒤 강제 실패를 주입해 관련 16개 테이블이 모두 비어 있는 상태로 롤백됨을 확인했습니다. 정상 적재 후 재실행은 거부됐고 22개 public 테이블의 행 수·해시가 유지됐습니다.
- 실제 AI는 별도 HTTPS 요청 한 건으로 `gpt-6-luna` 응답·SSE 순서·DTO·상태 조회·결과 유효성만 검사했습니다. 제공자 요청은 총 3회, 모두 200이며 재시도는 없었습니다. 요청 전송 제한기는 별도 모의 검증에서 네 번째 전송을 막았습니다. 응답 품질 평가·전체 AI 화면 연동의 완료 근거는 아닙니다.
- 팀장 지원자 상세에 검토 시작·미선발 조작을 연결했습니다([#172](https://github.com/wejo-team/sku-dreamon/issues/172)). 생명주기 검사는 실제 버튼과 미선발 확인창을 조작하고 서버의 상태·알림·재지원 제한을 확인합니다. 같은 상태의 API 재요청이 알림을 중복 생성하지 않는지도 별도로 검사합니다. 시연 계정·팀·공고는 API의 `isDemo`에 따라 화면과 접근 가능한 이름에 표시합니다([#171](https://github.com/wejo-team/sku-dreamon/issues/171)). 실제·시연 네 조합 검사는 API 값과 배지의 일치·부재, 320px 화면의 가로 넘침도 확인합니다.

전체 반복 점검과 후속 결과는 [#169](https://github.com/wejo-team/sku-dreamon/issues/169)에서 관리합니다. 원본 DB 자료·모델 키·로컬 원본 trace는 저장소에 포함하지 않았습니다.

## 2026-10-28 후속 수정과 검증 기록

[#175](https://github.com/wejo-team/sku-dreamon/pull/175)의 지원자 검토 조작과 [#177](https://github.com/wejo-team/sku-dreamon/pull/177)의 시연 표시를 병합한 main `3b751aa`에서 **원본 개발 DB 기본 16개가 한 번에 통과**했습니다. 실패·생략·flaky·재시도는 모두 0건입니다. 별도 보존 검사에서 기존 작업 파일 14개와 기존 행을 비교한 도메인 테이블 20개의 보존을 확인했습니다. 새 테스트 행은 남겨 두며 인증 세션·시도 제한 상태는 불변성 대상에서 제외합니다. 여기서 20은 테이블 수이며 아래 최종 E2E 구성 개수와 구분합니다.

별도 UI 작업 브랜치에서는 생명주기 집중 검사 **8개를 두 차례 각각 8/8 통과**했습니다. 같은 시나리오를 반복한 결과로, 고유 시나리오 16개가 아닙니다. 실제 세션 회수는 로그아웃으로 검사했고 시간 경과에 따른 TTL 만료를 검증한 것은 아닙니다. 알림 503은 브라우저의 응답 오류 주입이며 복구 요청은 실제 서버를 사용했습니다. 101명 지원자·100개 초과 팀의 목록 경계는 컴포넌트 테스트로 검증했으며 그 대규모 자료를 실제 DB 브라우저에서 시험했다고 확대하지 않습니다. 복제 DB의 실제/시연 네 조합 **8/8**은 별도 실행 기록입니다.

[#183](https://github.com/wejo-team/sku-dreamon/pull/183)의 취약 의존성, [#186](https://github.com/wejo-team/sku-dreamon/pull/186)의 AI 발행 DB 연결, [#187](https://github.com/wejo-team/sku-dreamon/pull/187)의 개인 응답 캐시 방지, [#188](https://github.com/wejo-team/sku-dreamon/pull/188)의 화면 경계 복구, [#189](https://github.com/wejo-team/sku-dreamon/pull/189)의 시드 회귀와 [#190](https://github.com/wejo-team/sku-dreamon/pull/190)의 문서 검색 갱신을 병합한 제품 기준은 main `329b9b9`입니다.

- [#188 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40572857540): 프론트 26개 파일·413개 테스트와 lint·format·typecheck·build, 격리 CI DB의 기본 E2E 20개 통과. 병합 후 main의 [앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40573547260)와 [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40573547246)도 통과했습니다.
- [#189 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40573652554): 백엔드 759개 통과·생략 0개, 기본 CI E2E 20개 통과. 병합 후 main의 [앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574351836)와 [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574351821)도 통과했습니다.
- [#190 앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574400031): 프론트 413개·백엔드 759개·기본 CI E2E 20개 통과. [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40574400021)는 검색 회귀 2개·기존 도구 44개·원본 문서 64개 검사와 빌드·생성 사이트 검사를 통과했습니다.

위 CI는 격리된 가상 자료를 사용하며 원본 개발 DB·실제 AI를 사용한 검사로 간주하지 않습니다.

### CI 설치 지연과 재검증

#177의 [main CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40567862079)는 APT 내려받기에 703초가 걸려 16개 중 14개 검사가 끝난 상태에서 15분 작업 제한으로 종료됐습니다. 이 실행을 전체 통과로 기록하지 않습니다. [#183 main 앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40569535308)와 [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40569535154)는 이후 통과했습니다.

[#185](https://github.com/wejo-team/sku-dreamon/pull/185)는 Integration 환경을 Ubuntu 24.04로 고정하고 공식 Ubuntu 미러를 사용하도록 조정했습니다. 서로 다른 실행의 실측값은 다음과 같으며 항상 같은 소요 시간을 보장하는 수치는 아닙니다.

| 측정 항목 | #177 PR 실행 | #185 PR 실행 |
| --- | --- | --- |
| APT 내려받기 | 609초 | 5초 |
| 브라우저·시스템 의존성 설치 단계 | 626.65초 | 68초 |

[#185 검증 실행](https://github.com/wejo-team/sku-dreamon/actions/runs/40570503393)은 Integration 작업 전체 278초, E2E 16개 통과·생략 0개였습니다. 병합 후 main의 [앱 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40571490806)와 [문서 CI](https://github.com/wejo-team/sku-dreamon/actions/runs/40571490711)도 통과했습니다. 설치 지연과 제품 검사 실패를 구분하고, timeout은 실행 완료로 취급하지 않습니다.

### 최종 반복 실행의 범위

최종 반복 검증의 범위는 원본 개발 DB 기본 **20개**와 복제 DB 혼합 **8개**입니다. 실행 커밋·대상·성공/실패·생략·재시도·기존 작업 파일 및 도메인 행의 보존 판정은 [#169](https://github.com/wejo-team/sku-dreamon/issues/169)를 기준 기록으로 확인합니다. 시나리오 구성 개수나 다른 커밋의 CI 통과를 해당 실행의 성공으로 대체하지 않습니다. 실제 AI 제공자 호출은 위의 3회 검증 범위로 한정하며 후속 회귀는 가짜 모델을 사용합니다. 운영 배포·실기기 Safari·전체 AI 품질 평가와 미정 정책은 이 검증의 완료 범위가 아닙니다.

## 종료와 데이터 유지

프론트·백엔드는 실행 터미널에서 Ctrl+C로 종료합니다. DB는 아래 명령으로 멈추며 테스트 볼륨을 유지합니다. 기존 개발 컨테이너에는 영향을 주지 않습니다.

```bash
POSTGRES_PORT=55433 docker compose -p sku-dreamon-bugbash stop
```

## 참고

- [Playwright 브라우저 컨텍스트 격리](https://playwright.dev/docs/browser-contexts)
- [Playwright 브라우저·시스템 의존성 설치](https://playwright.dev/docs/browsers)
- [Playwright trace 확인](https://playwright.dev/docs/trace-viewer)
