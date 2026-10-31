# Health·readiness API

**상태: 기존 liveness 유지 · [DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211) readiness 구현 · 인프라 미구현·미배포.** 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. 제품 성공 응답의 `data`로 감싸지 않는 최소 상태 응답입니다. 원본은 [라우터](../../backend/app/routers/health.py), [응답 모델](../../backend/app/schemas/readiness.py), [검사 서비스](../../backend/app/services/health.py), [DB 검사](../../backend/app/repositories/health.py)입니다.

| 경로 | 응답 | 의미 |
| --- | --- | --- |
| `GET /api/v1/health` | 200 `{"status":"ok"}` | 프로세스의 HTTP liveness. DB·AI 준비 상태를 확인하지 않음 |
| `GET /api/v1/ready` | 200 `{"status":"ready"}` 또는 503 `{"status":"unavailable"}` | 아래 자원·설정의 현재 준비 상태. 항상 `Cache-Control: no-store` |

ready는 현재 Settings의 유효성·CSRF 키·정확한 origin, 앱 수명에 실제 로드된 비어 있지 않은 차단 목록·일치하는 버전을 검사합니다. DB는 `SELECT 1`과 `alembic_version`을 읽고 단일 revision이 코드 소유 [COMPATIBLE_SCHEMA_REVISIONS](../../backend/app/core/db/revisions.py)에 있어야 합니다. 현재 브리지 앱의 호환 revision은 `20261026_09`, `20261031_10`이며 Alembic head는 `20261026_09`에 유지합니다. 환경변수로 임의 확장하지 않습니다. `SELECT 1`은 업무 테이블·sequence의 쓰기 권한 검증이 아닙니다.

AI 키가 있거나 `AI_REQUIRED=true`면 초기화된 로컬 AI client가 열려 있어야 합니다. AI 제공 배포는 `AI_REQUIRED=true`를 명시하여 키 누락을 설정 오류로 처리합니다. ready는 외부 LLM 요청을 하지 않으며 키 유효성·모델 제공자 가용성·할당량을 증명하지 않습니다. 응답에는 내부 오류·DB 주소·설정값·비밀값·릴리스 식별자를 추가하지 않습니다.

DB probe는 `READINESS_TIMEOUT_SECONDS` 기본 3초 안에 완료되지 않으면 503을 반환하고 취소합니다. 앱은 진행 중이거나 취소 후 정리 중인 probe 하나만 소유하며 그동안 추가 요청은 새 task 없이 즉시 503입니다. 정상 DB라도 동시 probe의 200은 보장하지 않으므로 rollout·monitor 검사를 직렬화합니다. 앱 종료는 해당 task 회수를 시도합니다.

HTTP 경로는 세션 인증 없이 호출하지만 [운영 HTTP 경계](../development/backend.md#deployment-runtime)는 동일하게 적용됩니다. production에서는 trusted Nginx 컨테이너의 고정 peer에서 후보 Docker 서비스 이름으로 요청하고 예상 API Host·실제 client IP 하나의 `X-Forwarded-For`·`X-Forwarded-Proto: https`를 전달해야 합니다. API 컨테이너 안·호스트 localhost의 직접 probe는 의도적으로 거부합니다. Host·peer·헤더 거부는 ready의 503 판정보다 먼저 처리됩니다. 실제 Nginx 경로·외부 공개 제한·배포 전환은 [DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212)의 후속 범위입니다.

DB revision 변경 전 구 앱의 구/신 revision 호환 릴리스를 먼저 배포한 뒤 safe expand·새 앱 전환을 진행합니다. ready 성공과 새 이미지 SHA·digest 확인은 별개이며, 릴리스 식별 endpoint는 아직 없습니다. 전체 순서는 [배포 기반 계획](../development-plans/deployment-foundation.md)을 따릅니다.
