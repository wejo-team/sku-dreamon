# 제품 배포 기반 설계안

**상태: AWS 배포 방향 합의 · DEP-02 앱 계약 구현 · 인프라 미구현 · 미배포.** 2026-10-29 기준 [DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211)의 운영 설정·CORS·DB TLS·readiness·SSE 종료 계약을 구현했습니다. 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)에서 확인합니다. 인프라 생성·운영 비밀값 설정·제품 배포·실제 모델 호출은 수행하지 않았습니다. 나머지 DEP 작업은 예정입니다.

## 기준과 범위

프론트·백엔드·DB를 AWS에 두는 방향에 따라 **비공개 S3·CloudFront 정적 프론트 + 단일 public EC2의 별도 Nginx·FastAPI 컨테이너 + 비공개 관리형 RDS PostgreSQL**을 계획합니다. 평소에는 FastAPI 컨테이너 하나를 실행하고, 배포 중에만 이전·새 컨테이너 두 개를 함께 유지한 뒤 이전 요청을 드레인하고 종료합니다. 먼저 가상 데이터를 쓰는 공동 검증 환경에서 인증·배포 중 스트리밍·복구를 검증합니다.

| 구분 | 내용 |
| --- | --- |
| 사용자와 합의한 방향 | AWS 전용 호스팅, 프론트는 S3·CloudFront, API는 단일 EC2의 Nginx·FastAPI, DB는 RDS. 소유할 같은 등록 도메인의 `www`·`api` 사용 |
| 이 문서의 세부 제안 | RDS Single-AZ, GitHub Actions·OIDC·SSM 배포, Docker Compose 실행 관리, API의 Let's Encrypt·Certbot TLS, 서울 리전 후보 |
| 사용자 규모·예산 제약 | 초기 사용자 100명 미만, 월 3만 원 미만 목표. 장기 비용과 운영 책임을 [DEP-01 #210](https://github.com/wejo-team/sku-dreamon/issues/210)에서 비교하며 자원 크기·DB 호스팅은 미정 |
| 아직 결정하지 않은 사항 | 실제 도메인·AWS 계정·리전·자원 크기, 자산·인증서 보관과 운영 담당자, 데이터 보존·복구 목표 |
| 현재 구현 | 앱 CI·문서 Pages, 로컬 HTTPS 통합 검사, 서버 세션·CSRF, AI SSE와 중단·복구 UI. DEP-02 운영 앱 계약 구현, 구현·검증 근거 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217) |
| 아직 없는 기반 | 제품 Dockerfile·배포 workflow·운영 Nginx·AWS 리소스·배포 드레인·운영 정리 스케줄 |

초기 구성에는 ALB·Kubernetes를 추가하지 않습니다. **GitHub Actions는 배포 순서를 조정하고, Docker Compose는 컨테이너 실행을 관리하며, 계속 실행되는 별도 Nginx 컨테이너는 TLS와 요청 경로를 담당합니다.** 평소 Compose 기동은 활성 앱 슬롯만 선택하고, 배포 때 비활성 슬롯을 추가로 기동하는 계약으로 두 앱의 상시 실행을 피합니다. Compose 자체가 readiness 확인·트래픽 전환·스트림 드레인을 자동 보장하지 않으므로 배포 절차를 별도로 구현합니다. 호스트 장애 대응이 필요해지면 ECS·ALB·복수 task와 RDS Multi-AZ의 비용·운영 범위를 비교합니다.

기준은 [배포 검증 #165](https://github.com/wejo-team/sku-dreamon/issues/165), [인증 운영 #98](https://github.com/wejo-team/sku-dreamon/issues/98), [AI 품질·운영 #164](https://github.com/wejo-team/sku-dreamon/issues/164), [인증 전송 계약](../api/conventions.md#csrf-transport), [AI API](../api/ai.md), [통합테스트와 bug bash](../development/bug-bash.md)입니다. 작업 분할·리뷰는 [팀 작업 흐름](../development/workflow.md), 구현 규칙은 [백엔드](../development/backend.md)·[테스트](../development/testing.md), 문서 변경은 [문서 관리](../development/documentation.md)를 따릅니다.

서비스 가이드 도구, pgvector·RAG, 신규 AI 모델, SSE 재생·대화 복원, 제품 데이터 정책 변경은 범위 밖입니다. 이 설계는 **애플리케이션 교체 중 연결 유지**를 목표로 하며, 검증 전 무중단을 보장하지 않습니다. EC2 장애·OS 재부팅·Nginx 자체 중단이나 Single-AZ DB 장애에 대응하는 호스트 고가용성은 포함하지 않습니다.

## 요청 경로와 초기 자원

아래 주소는 소유할 도메인의 자리표시자입니다. 실제 DNS 이름은 미정입니다.

| 경로 | 담당 | 배포 경계 |
| --- | --- | --- |
| 브라우저 → `https://www.example.com` | CloudFront → 비공개 S3의 `frontend/dist` | HTML·JS·CSS와 허용된 SPA 경로. CloudFront OAC로 S3 REST origin 접근 |
| 브라우저 → `https://api.example.com/api/v1` | EC2의 Nginx → 활성 FastAPI 컨테이너 | JSON과 POST SSE 모두 브라우저에서 직접 호출. Nginx에서 TLS 종료 |
| FastAPI → RDS endpoint | 같은 VPC의 private DB subnet | EC2 SG에서 DB SG의 5432만 허용, 인증서·호스트명 검증 TLS |
| FastAPI → 모델 제공자 | EC2 outbound HTTPS | 운영 런타임에서만 사용. 기존 `gpt-6-luna` 유지 |
| GitHub Actions → ECR·SSM·S3·CloudFront | OIDC로 얻은 단기 AWS 권한 | 같은 SHA의 이미지·정적 산출물 게시, API 전환, CDN 무효화와 결과 확인 |

EC2는 public subnet의 고정 public IPv4와 Internet Gateway 경로를 사용합니다. Nginx의 443과 HTTP→HTTPS 전환·인증서 발급용 80만 외부에 열고, SSH·FastAPI 포트·DB 포트는 공개하지 않습니다. Nginx와 두 앱 슬롯은 같은 호스트의 전용 Docker 네트워크에서 서비스 이름으로 연결하며, 앱 포트를 호스트에 게시하지 않습니다. Nginx 컨테이너 안의 `localhost`는 Nginx 자신을 가리키므로 앱 주소로 쓰지 않습니다. 새 앱이 준비된 뒤 활성 upstream을 만들고, 컨테이너 재생성으로 바뀐 주소를 설정 검증·reload에서 다시 해석하는지 확인합니다.

EC2는 ECR·SSM·로그·시크릿·모델 API에 필요한 HTTPS egress를 사용하므로 초기 구성에 NAT Gateway를 추가하지 않습니다. public EC2의 방화벽·패치·프록시 운영 책임을 포함합니다. 오픈소스 Nginx 자체의 라이선스료나 EC2의 컨테이너별 별도 요금은 없으며, 같은 EC2 유형·실행시간을 유지하면 컨테이너 추가 자체로 기본 컴퓨트 요금이 바뀌지는 않습니다. 다만 부하 증가에 따른 인스턴스 크기 확대, burstable 인스턴스의 Unlimited CPU credit과 네트워크·로그·스토리지는 별도 비용 항목입니다. [AWS Internet Gateway](https://docs.aws.amazon.com/vpc/latest/userguide/VPC_Internet_Gateway.html), [NGINX Open Source](https://nginx.org/en/), [EC2 온디맨드와 CPU credit 요금](https://aws.amazon.com/ec2/pricing/on-demand/)

현재 기준안은 RDS이며, EC2의 PostgreSQL 동시 실행은 아래 비용 비교 후보입니다. DB 호스팅 전환을 결정하거나 배포한 상태는 아닙니다. RDS는 `PubliclyAccessible=false`, 암호화된 스토리지, EC2 보안 그룹만 허용하는 인바운드 규칙을 사용합니다. Single-AZ 인스턴스라도 DB subnet group에는 서로 다른 AZ의 private subnet 두 개를 준비합니다. subnet 두 개가 DB 이중화를 제공하는 것은 아닙니다. PostgreSQL은 현재 개발·CI의 17 계열과 맞추되, 서울 리전의 지원 마이너 버전과 유지보수 정책을 생성 전에 확인합니다. [RDS VPC 구성](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_VPC.WorkingWithRDSInstanceinaVPC.html)

EC2 크기는 두 앱 슬롯, Nginx, OS·로그 에이전트가 동시에 동작하는 최대 메모리와 CPU를 측정해 정합니다. 가장 작은 인스턴스를 미리 확정하지 않습니다. DB 연결 수도 두 슬롯·각 프로세스의 pool과 migration·정리 작업을 합산해 RDS 한도 안으로 제한합니다. 초기에는 슬롯당 Uvicorn 프로세스 하나를 제안하며, 프로세스 증가는 부하 검사와 함께 재산정합니다.

### 예산과 DB 호스팅 비교 후보

월 3만 원 미만 목표에서는 RDS의 상시 비용이 부담이 될 수 있어 [DEP-01 #210](https://github.com/wejo-team/sku-dreamon/issues/210)에서 공식 요금·계정 혜택·리전·저장량을 대조합니다. 기한이 있는 무료 체험을 장기 무료로 계산하지 않으며, 원화 총액은 보장하지 않습니다. 기존 RDS 기준안은 결정 전까지 유지합니다.

같은 EC2에 PostgreSQL을 두는 후보는 평소 Nginx·API·DB를 실행하고, 앱 배포 때 **API 이전·새 슬롯만 교체**하는 방식입니다. DB의 영속 볼륨을 유지하며 앱 릴리스마다 DB 컨테이너를 교체하지 않습니다. DB 비용을 줄일 수 있지만 백업·복원 시험·패치·모니터링을 직접 맡고 호스트 장애를 앱과 공유합니다. 두 API 슬롯과 DB의 최대 메모리·연결 수·디스크 예산도 함께 측정해야 합니다. 아래 앱의 검증 TLS는 RDS 전용이 아니므로 자체 CA와 PostgreSQL 서비스 호스트명에도 적용할 수 있습니다. 이 비교는 후보 검토이며 DB 호스팅 확정이나 평문 DB 연결 허용을 뜻하지 않습니다.

## S3·CloudFront 프론트와 TLS

S3 버킷은 public access를 차단하고, 해당 CloudFront 배포만 읽을 수 있는 bucket policy와 OAC를 적용합니다. **S3 REST origin을 사용하며 website endpoint를 사용하지 않습니다.** OAC의 항상 서명하는 설정으로 CloudFront→S3도 HTTPS를 사용합니다. 브라우저의 API 요청은 CloudFront를 거치지 않고 `api.example.com`으로 직접 보냅니다. [CloudFront OAC와 S3 origin](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-s3.html)

Actions runner에서 `.nvmrc`·`package.json`의 고정 도구와 잠금 파일로 `frontend`의 `npm ci`·`npm run build`를 실행하고 **`frontend/dist`**를 릴리스 산출물로 보존합니다. 빌드 시 `VITE_API_MOCK=false`, `VITE_API_BASE_URL=https://api.example.com/api/v1`을 명시합니다. `VITE_*`는 공개 번들 값이므로 비밀값을 넣지 않습니다. 실제 변수 사용처는 [API 클라이언트](../../frontend/src/lib/api.ts), 현재 개발 프록시는 [Vite 설정](../../frontend/vite.config.ts)에 있습니다.

| 대상 | 게시·캐시 계약 |
| --- | --- |
| `index.html`과 진입 HTML | `Cache-Control: no-cache`로 재검증. 해당 CloudFront cache policy의 **Minimum TTL은 0**으로 설정하며 헤더보다 긴 강제 캐시를 피함 |
| 내용 해시가 있는 JS·CSS·자산 | 동일 경로의 내용을 덮어쓰지 않고 긴 `max-age`·`immutable` 사용. 새 자산을 먼저 올리고 진입 HTML을 마지막에 게시 |
| 해시가 없는 public 자산 | 구 프론트와 호환되는 내용을 유지하거나 release별 경로 사용. 해시 자산과 같은 불변성·보존을 가정하지 않음 |
| 이전 릴리스 | 이전 HTML·manifest·설정과 연결된 자산을 함께 보관. 열린 탭의 동적 import와 개별 프론트 롤백에 필요한 보존 기간·정리 기준을 결정 |

CloudFront는 Minimum TTL이 0보다 크면 origin의 `no-cache`·`no-store`보다 그 값을 우선할 수 있으므로 HTML 헤더만 설정해서는 안 됩니다. 해시·release별 URL과 S3 bucket versioning은 별개입니다. bucket versioning만으로 열린 탭이 참조하는 이전 URL을 보장하지 않으며, 전체 동기화의 `--delete`로 이전 자산을 지우지 않습니다. HTML을 바꾼 뒤 필요한 경로만 invalidation하고 **완료를 기다린 후** 외부 smoke로 새 릴리스를 확인합니다. [캐시 만료와 Minimum TTL](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Expiration.html), [버전별 파일 게시](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/UpdatingExistingObjects.html), [invalidation](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/Invalidation.html)

SPA 직접 URL·새로고침은 **허용한 navigation route만 단일 `/index.html`로 rewrite**합니다. navigation URL로 요청해도 HTML의 Minimum TTL 0·재검증 정책을 적용하며, `/assets/*`의 긴 immutable 캐시와 분리합니다. 모든 오류를 index로 바꾸거나 모든 경로에 `index.html`을 덧붙이지 않습니다. 없는 JS·CSS·이미지는 실제 오류로 남기고 API 오류도 HTML로 가리지 않습니다. 검증 환경이 필요하면 운영과 격리된 API·DB와 별도 origin을 마련하거나 목업 화면으로 한정하며, 임의 preview origin을 운영 CORS에 추가하지 않습니다.

| TLS 구간 | 인증서와 운영 계약 |
| --- | --- |
| 브라우저 → CloudFront | `www.example.com`의 DNS 검증 ACM 인증서를 **`us-east-1`**에 준비하고 CloudFront viewer에 연결. 앱 리전 후보와 구분하며 DNS 검증 레코드 유지·갱신 상태 감시 |
| 브라우저 → EC2 Nginx | `api.example.com`에 Let's Encrypt·Certbot HTTP-01 사용. public DNS가 EC2를 가리키고 port 80의 challenge 경로에 접근 가능해야 함 |
| Nginx → FastAPI | 같은 호스트의 전용 Docker 네트워크에서만 plain HTTP. 공개 앱 포트·다른 호스트 구간으로 확대하지 않음 |
| FastAPI·Alembic → RDS | RDS CA와 endpoint hostname을 검증하는 TLS. 인증서·호스트명 오류 때 접속 실패 |

API 최초 기동은 **port 80의 challenge만 처리하는 Nginx 설정 → Certbot 최초 발급 → 인증서 파일 확인·새 HTTPS 후보 설정을 `nginx -t`로 검사 → HTTPS 설정 활성화·reload** 순서로 설계합니다. 인증서가 아직 없는데 HTTPS 설정부터 읽어 Nginx가 시작하지 못하는 순환을 피합니다. 인증서·개인키뿐 아니라 Certbot의 **`/etc/letsencrypt` 전체 상태**를 컨테이너 재생성 후에도 남는 접근 제한 런타임 저장소에 보관합니다. ACME 계정·갱신 설정·`archive`와 `live`의 symlink 대상까지 포함하며 Git·이미지에 넣지 않습니다. Nginx는 필요한 인증서를 읽고 Certbot은 갱신을 기록할 최소 권한만 가집니다. 정기 자동 갱신과 성공 후 새 후보 설정 검증·reload, 실패·만료 경보를 검증합니다. Nginx 설정은 버전 관리하고 인증서·키·앱 비밀값은 분리합니다. [CloudFront HTTPS 인증서 요구사항](https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cnames-and-https-requirements.html), [Let's Encrypt HTTP-01](https://letsencrypt.org/docs/challenge-types/), [Certbot 갱신과 hook](https://eff-certbot.readthedocs.io/en/stable/using.html), [Certbot 갱신 설정과 상태](https://eff-certbot.readthedocs.io/en/stable/using.html#modifying-the-renewal-configuration-of-existing-certificates)

## 인증·프록시·환경설정

`www.example.com`과 `api.example.com`은 HTTPS에서 same-site이지만 origin은 다릅니다. API 호스트 전용 `__Host-*` 쿠키의 `Secure`·`HttpOnly`·`SameSite=Lax`·`Path=/`를 유지하고 `Domain`을 추가하지 않습니다. 프론트는 이미 `credentials: include`를 사용하며, `/auth/csrf` 응답의 토큰을 메모리에 두고 상태 변경에 `X-CSRF-Token`으로 보냅니다. 프론트 도메인에서 API 쿠키를 직접 읽을 필요가 없습니다. [쿠키 구현](../../backend/app/routers/auth_cookies.py), [SameSite·host-only 설명](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie)

[앱 생성 코드](../../backend/app/main.py)와 [HTTP 경계](../../backend/app/core/http/deployment.py)는 `AUTH_ALLOWED_ORIGINS`의 정확한 HTTPS origin만 credentialed CORS로 허용합니다. `Content-Type`·`X-CSRF-Token`과 실제 메서드 목록을 허용하며 `X-Request-ID`·`Retry-After`를 노출합니다. CORS는 최외곽 오류 처리까지 감싸므로 허용 origin의 401·403·500·SSE에도 적용됩니다. 세션·CSRF·제품 응답·쿠키 계약은 유지하며 Nginx에서 CORS를 중복 발급하지 않습니다.

**앱이 전달 헤더를 해석하는 유일한 경계입니다.** 운영은 `python -m app.cli.serve`로 실행하거나 Uvicorn의 `--no-proxy-headers`와 동등한 설정을 사용합니다. 이 실행기는 `proxy_headers=False`, `forwarded_allow_ips=""`를 고정합니다. Nginx는 외부 전달 헤더를 제거하고 `X-Forwarded-For`를 실제 연결 IP 하나로, `X-Forwarded-Proto`를 `https`로 덮어써야 합니다. `Forwarded`·`X-Forwarded-Host` 등 추가 전달 헤더는 허용하지 않습니다. 앱은 원래 TCP peer가 `HTTP_TRUSTED_PROXIES`의 정확한 IP·좁은 CIDR에 속하는지, Host가 `HTTP_ALLOWED_HOSTS`와 일치하는지 CORS보다 먼저 검사합니다. OPTIONS도 같은 경계를 통과해야 하며, 위조 전달 IP·허용되지 않은 Host로 preflight를 우회할 수 없습니다. 실제 Nginx 컨테이너·고정 peer 구성의 증명은 [DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212)에서 수행합니다.

[Settings](../../backend/app/core/config.py)와 [환경변수 예시](../../backend/.env.example)가 설정 이름·기본값·허용 범위의 원본입니다. 운영 공통 설정은 명시적인 비로컬 PostgreSQL URL과 검증용 CA를 요구하며 URL query parameter는 금지합니다. HTTP 앱은 추가로 CSRF 키·정확한 origin·차단 목록 경로/버전·Host·trusted proxy를 요구합니다. CLI·Alembic은 별도의 DB 전용 운영 환경과 DDL 자격증명으로 실행할 수 있어 HTTP·AI 비밀값을 나눠 줄 수 있습니다. 검사를 피하려고 `APP_ENV=development`로 실행하지 않습니다.

[공통 DB 엔진](../../backend/app/core/db/session.py)은 앱·CLI·[Alembic](../../backend/alembic/env.py)에 CA·호스트명 검증 TLS와 유한한 연결·쿼리·잠금 예산을 적용합니다. RDS와 자체 CA PostgreSQL 모두 대상이며 인증서 실패 때 평문으로 전환하지 않습니다. migration은 `NullPool`, 앱은 프로세스별 제한 pool을 사용합니다. 기본값과 수명 정리 계약은 [백엔드 운영 계약](../development/backend.md#deployment-runtime)을 참조합니다. 연결 예산은 `슬롯 수 × 프로세스 수 × (pool size + overflow) + migration/정리 작업 + 관리 여유`로 산정하며, 기본 pool 값만으로 운영 DB 수용량을 보장하지 않습니다. 앱 DML 역할·migration DDL 역할과 필요한 권한의 실제 준비는 후속 운영 작업입니다.

AI 키의 비어 있지 않은 값에서 `ai_enabled`를 계산하며 기본 `AI_REQUIRED=false`는 기존 비AI 실행을 유지합니다. **AI를 제공하는 배포는 `AI_REQUIRED=true`를 명시**하여 키 누락을 설정 오류로 막습니다. 로컬 AI client 미초기화·종료 상태도 ready 실패입니다. 모델은 `gpt-6-luna`를 유지하고 키 유효성·외부 가용성·할당량은 ready에서 검사하지 않습니다.

초기 비밀값 저장소는 Parameter Store `SecureString`을 제안합니다. 자동 회전 요구가 있으면 Secrets Manager와 비용을 비교합니다. EC2 instance role이 정해진 환경 경로·필요한 KMS 키만 읽도록 하고 접근을 제한한 런타임 파일로 주입합니다. 같은 DB의 구/신 슬롯에는 같은 CSRF 키 버전을 공급하며 임의 동시 회전을 피합니다. [SecureString](https://docs.aws.amazon.com/systems-manager/latest/userguide/secure-string-parameter-kms-encryption.html)

공개 저장소의 코드·예시·문서·테스트·PR에는 설정 이름과 합성 자리표시자만 둡니다. 실제 도메인·IP·DB endpoint·계정 ID·ARN·자격증명·사용자 자료는 비공개 Secrets와 접근 제한 운영 기록으로 관리합니다. 이미지·Git·프론트 번들·SSM 인자·배포 로그에 비밀값을 넣지 않으며 `docker inspect` 접근도 운영 관리자 권한으로 취급합니다.

## 헬스 검사와 전환 조건

`GET /api/v1/health`는 기존 `{"status":"ok"}` liveness를 유지합니다. `GET /api/v1/ready`는 DB·호환 revision·로드된 차단 목록·현재 보안 설정·필요한 로컬 AI client를 확인하고 200 `{"status":"ready"}` 또는 503 `{"status":"unavailable"}`만 반환합니다. `Cache-Control: no-store`이며 상세 오류·버전·비밀값을 노출하지 않습니다. 외부 모델 요청은 발생하지 않습니다. 상세 동작은 [health·readiness API](../api/health.md), 원본은 [라우터](../../backend/app/routers/health.py)·[검사 서비스](../../backend/app/services/health.py)입니다. 릴리스 SHA·설정 버전 식별 endpoint는 아직 없으므로 readiness 성공과 배포할 image digest·SHA 확인을 구분합니다.

운영 전환 전 검사는 **trusted Nginx 컨테이너의 고정 네트워크 peer에서 후보 Docker 서비스 이름으로** 요청합니다. 예상 API Host와 `X-Forwarded-For`의 실제 검사 client IP 하나, `X-Forwarded-Proto: https`를 사용합니다. API 컨테이너 안·호스트 localhost에서 직접 호출하면 운영 프록시 경계가 의도적으로 거부하므로 그 요청을 readiness 성공 조건으로 쓰지 않습니다. 내부 rollout·monitor probe는 직렬화합니다. 이미 진행·취소 정리 중인 검사 한 개가 있으면 다른 probe는 즉시 503이며 동시 요청의 200은 보장하지 않습니다. Nginx 기반의 실제 경로 검증과 외부 공개 차단은 DEP-03 후속입니다.

DB 검사는 제한 시간 안의 `SELECT 1`과 단일 Alembic revision을 사용합니다. 릴리스의 [COMPATIBLE_SCHEMA_REVISIONS](../../backend/app/core/db/revisions.py)는 현재 `20261026_09`이며 소스 리뷰·테스트로만 확장합니다. 환경변수로 임의 revision을 허용하지 않습니다. 새 revision을 허용하는 **이전 앱의 호환 릴리스부터** 기존 schema에 배포한 뒤 safe expand·새 앱 전환을 진행해야 이전 슬롯을 재기동할 수 있습니다.

`SELECT 1`은 테이블·sequence의 DML 권한을 증명하지 않습니다. 앱 역할의 필요한 읽기/쓰기 권한은 배포 전 점검과 격리된 smoke에서 검사하고 반복 readiness에 사용자 생성·로그인·지속 DB 쓰기를 넣지 않습니다.

## 배포·스트림 드레인·롤백

### 동일 버전의 검증과 배포

1. 배포 후보를 하나의 Git SHA로 고정합니다. [Application CI](../../.github/workflows/ci.yml)의 `Frontend`·`Backend`와 [Docs and Pages](../../.github/workflows/docs.yml)의 `Validate docs`가 **같은 저장소·SHA의 `push`/`main` 실행**에서 모두 성공해야 합니다. PR 검사나 다른 SHA의 최근 성공으로 대체하지 않습니다.
2. 그 SHA를 checkout해 고정 도구·잠금 파일로 백엔드 이미지와 프론트 `dist`를 빌드합니다. ECR에 변경 불가능한 SHA tag와 digest를 기록하고, 프론트 산출물·manifest·공개 빌드 설정도 같은 릴리스에 보존합니다. 백엔드는 digest로 배포하며 `latest`나 EC2에서의 `git pull`·빌드를 사용하지 않습니다. [ECR 태그 불변성](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-tag-mutability.html)
3. **백엔드 전환부터 프론트 게시·invalidation·외부 smoke·실패 복원까지 전체 workflow를 직렬화**하고 EC2 배포 lock을 함께 사용합니다. 오래된 재실행은 변경 시작 전 최신 main SHA 검사로 건너뜁니다. 트래픽·HTML 활성화 직전에도 최신 SHA를 확인하며, 중간에 제외할 릴리스가 이미 변경을 수행했다면 안전한 복원 절차 후 종료합니다. 새 push로 진행 중인 배포를 강제 취소하지 않습니다. 장애 롤백은 별도 명시적 절차로 직전 검증 릴리스를 선택합니다.
4. 현재 슬롯·이전 digest·설정 버전·DB revision·프론트 HTML/manifest를 기록하고, 두 앱이 함께 동작할 메모리·디스크·연결 여유를 확인합니다. migration 필요 시 배포 lock 안에서 아래 DB 절차를 한 번 실행합니다.
5. 같은 DB·CSRF key를 사용하는 비활성 슬롯에 새 digest를 기동해 trusted Nginx peer의 직렬 readiness와 내부 smoke를 통과시킵니다. 실패하면 새 슬롯만 정리하고 기존 트래픽은 유지합니다.
6. 준비된 새 Docker 서비스 이름을 upstream으로 선택하고, 현재 컨테이너 주소 해석과 **새 upstream 후보 설정을 대상으로 한 `nginx -t` 성공**을 확인한 뒤 설정을 원자적으로 활성화·reload합니다. 새 연결은 새 슬롯으로, 이미 처리 중인 요청은 기존 worker와 기존 슬롯에서 끝나게 합니다. 전환 실패 시 기존 설정으로 복원합니다. [Nginx reload 동작](https://nginx.org/en/docs/control.html)
7. 실제 HTTPS 경로에서 버전·인증·API smoke를 수행합니다. SSE 전송·전환 검사는 먼저 격리된 fake provider 환경에서 같은 이미지/프록시 기반으로 통과시킵니다. 운영의 실제 모델 smoke는 #164에서 키·호출 예산을 정한 별도 단계이며 자동 배포 검사에 무조건 포함하지 않습니다. 실패 시 schema 호환이 확인된 이전 슬롯으로 reload하고, 새 슬롯에 이미 열린 스트림도 같은 원칙으로 정리합니다.
8. 이전 Nginx worker가 종료되어 이전 upstream으로 가는 요청이 없음을 확인한 뒤 이전 앱 컨테이너를 정상 종료합니다. 상태·로그·전환 시각을 기록하고 직전 이미지는 보존합니다. 드레인이 실패하면 완료로 표시하지 않고 다음 슬롯 재사용을 막습니다.
9. 호환되는 백엔드의 전환·드레인이 성공하면 같은 릴리스의 해시·release별 프론트 자산을 S3에 먼저 올려 확인하고, 진입 HTML을 마지막에 게시합니다. 이전 자산은 삭제하지 않습니다.
10. HTML과 필요한 navigation 경로에 한정해 CloudFront invalidation을 요청하고 완료를 기다립니다. 실제 `www`에서 릴리스·SPA 새로고침·자산·인증·API를 smoke한 뒤 전체 배포를 완료로 기록합니다.
11. **HTML 게시·invalidation·외부 smoke가 실패하면 이전 프론트가 자동으로 남아 있다고 가정하지 않습니다.** 보관한 이전 HTML·manifest·필요한 변경 가능 자산을 복원하고 해당 경로를 다시 invalidation한 뒤 완료·외부 smoke를 확인합니다. 복원도 실패하면 미완료 장애로 기록·알림하고 다음 배포를 막습니다. 새 백엔드는 이전 프론트와의 호환성을 유지해야 하며, 백엔드도 되돌려야 할 때는 별도 readiness·전환·드레인 절차를 적용합니다.

### SSE 종료 예산

현재 [AiStreamResponse](../../backend/app/routers/ai.py)는 10초 heartbeat를 보내며, 연결이 끊기면 생성 작업을 취소합니다. [AiService](../../backend/app/services/ai.py)는 설정된 실행 제한시간과 종료 정리를 적용합니다. 실행은 API 프로세스 안에 있고 checkpoint나 다른 프로세스로의 스트림 인계가 없습니다. 강제 종료 뒤 재연결로 같은 답변을 이어받을 수 없습니다.

앱의 SSE 응답 상한은 협조적 취소와 유한한 DB·driver I/O를 전제로 `AI_TIMEOUT_SECONDS + 9초 + AI_CLEANUP_TIMEOUT_SECONDS`에 스케줄링 여유를 더한 값입니다. 헤더 전송 전부터 실행 예산을 측정하며 각 전송은 3초, 예외 상태 저장·provider/generator 종료·`on_close`는 첫 정리 때 시작한 하나의 deadline을 공유합니다. 기본 정리 예산은 5초이며 경로마다 초기화하지 않습니다. 시간 초과·닫기 실패는 성공 결과·`done`으로 위장하지 않고 기존 완료 commit 경계를 유지합니다. 취소를 무시하는 임의 외부 코드의 강제 종료를 보장하지 않습니다. 구현과 지연 정리의 상태 전이는 [AI 종료 계약](../api/ai.md#termination)을 따릅니다.

드레인 제안값은 `D = max(구/신 슬롯의 전체 AI 응답 상한, 일반 요청 처리 상한) + 운영 여유`입니다. 일반 요청 상한·운영 여유는 실제 프록시·부하·DB 잠금 시험으로 정합니다. 앱 lifespan의 readiness probe·로컬 AI client·DB engine 종료는 **자원별** `SHUTDOWN_TIMEOUT_SECONDS`를 각각 사용하므로 기본 총 30초, 설정 최대 총 90초의 별도 정리 예산도 Uvicorn·Docker의 전체 종료 유예에 반영합니다. 앱의 유한한 정리 계약과 Nginx 드레인 구현·검증은 구분합니다.

| 계층 | 제안 조건과 검증 |
| --- | --- |
| Nginx 프록시 | SSE `proxy_buffering off`·cache 비활성, 압축·변환으로 chunk를 모으지 않음. POST/스트림의 upstream 자동 재시도 금지. `proxy_read_timeout`은 heartbeat 간격보다 충분히 크고 초기에는 D 이상으로 설정. 응답 전체 제한과 유휴 제한을 혼동하지 않음 |
| Nginx 이전 worker | reload 이전 worker를 식별해 종료를 관측. `worker_shutdown_timeout`을 D보다 여유 있게 설정해 정상 요청을 먼저 끝냄. 한도 도달에 의한 강제 연결 종료는 실패로 기록 |
| Uvicorn·Docker | exec 방식으로 신호를 전달하고 `--timeout-graceful-shutdown`과 `stop_grace_period`에 D와 자원별 lifespan 정리 합산 예산·추가 여유를 반영. Docker 강제 종료가 앱 정리보다 먼저 발생하지 않게 실제 종료 순서를 검증 |
| 배포 스크립트 | reload 직후 `docker stop`하지 않음. 이전 worker 종료를 기다리고, 대기 초과·취소·SSM 연결 유실에도 활성 버전·미완료 드레인을 복구 가능한 상태 파일로 남김 |
| 브라우저 | 구 연결의 최종 `done`까지 수신. 실제 네트워크·프로세스 장애는 기존 상태 조회·재시도 UI로 복구하며 성공으로 위장하거나 POST를 자동 재전송하지 않음 |

Nginx의 buffering 설정, worker 종료 한도, Docker 종료 유예는 각각 별도 설정입니다. 한 곳의 timeout만 늘려서 전체 드레인이 보장된다고 판단하지 않습니다. Uvicorn 옵션은 고정한 실행 버전으로 확인합니다. [Nginx buffering](https://docs.nginx.com/nginx/admin-guide/web-server/reverse-proxy/), [worker 종료 한도](https://nginx.org/en/docs/ngx_core_module.html#worker_shutdown_timeout), [Docker 종료 유예](https://docs.docker.com/reference/compose-file/services/#stop_grace_period)

### DB와 프론트 호환성

Alembic migration은 컨테이너마다 시작 시 실행하지 않습니다. 배포 lock 안의 단일 작업이 새 이미지의 migration을 별도 DDL 계정으로 실행합니다. **이전 앱의 구/신 revision 호환 릴리스 배포 → 안전한 expand 변경 → 새 앱 readiness·전환 → 관찰 기간 후 contract 변경** 순서를 사용합니다. migration 실패·잠금 대기 초과면 전환하지 않습니다. 오래 걸리는 backfill과 인덱스 작업은 실행 시간·잠금 영향을 따로 검증합니다.

N과 N−1 앱·schema 호환성을 테스트하고 릴리스에 기록합니다. 컬럼 삭제·이름 변경·필수값 강제 같은 contract 작업은 이전 앱·열린 브라우저·진행 중 스트림의 사용이 끝난 후 별도 릴리스로 수행합니다. 즉시 파괴적 migration이 필요한 변경은 이 교체 절차로 실행하지 않고 점검 시간을 계획합니다.

앱 롤백은 호환되는 이전 **이미지와 설정**으로의 전환입니다. 자동 `alembic downgrade`로 운영 데이터를 되돌리지 않습니다. 프론트·백엔드는 원자적으로 함께 전환되지 않고 오래 열린 탭도 있으므로, 새 백엔드는 기존 프론트 요청과 SSE 계약을 유지해야 합니다. 프론트만 이전 릴리스의 HTML·자산으로 복원하는 경로도 시험합니다. 이전 JS 자산의 접근·캐시·동적 import 실패 회복을 확인하고, 호환 계약을 지우는 릴리스는 별도 안내와 검증을 거칩니다.

현재 프론트 DTO와 [AI 이벤트 스키마](../../frontend/src/features/ai/contract.ts)는 Zod `.strict()`를 사용합니다. **응답 필드 추가도 구 프론트에는 비호환일 수 있습니다.** 구/신 프론트 × 구/신 백엔드 조합과 열린 탭을 검사하고, 필요하면 먼저 호환 파서를 배포하거나 버전별 응답을 유지한 뒤 확장합니다. DB expand-contract만으로 API·SSE 호환성을 보장하지 않습니다.

## 배포 권한과 복구·운영

GitHub Actions는 AWS OIDC로 단기 역할을 얻습니다. `aud=sts.amazonaws.com`, 정확한 저장소와 `sub`를 제한하며, production environment를 사용하면 `sub`가 branch 대신 environment를 나타내므로 environment 자체에서 main만 허용합니다. 저장소 생성 시점·설정에 따라 owner/repository의 불변 ID가 subject에 포함될 수 있으므로 실제 발급 claim 형태를 확인해 trust policy를 만들고 예전 문자열 예제를 그대로 복사하지 않습니다. PR·fork 실행에는 운영 역할을 주지 않습니다. 정적 AWS access key를 GitHub secret으로 보관하지 않습니다. [GitHub OIDC와 AWS](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)

| 역할 | 최소 책임 |
| --- | --- |
| 이미지 게시 역할 | 정해진 ECR 저장소에 push. 인증 토큰 작업의 `*`와 저장소별 권한을 구분 |
| API 배포 역할 | 대상 instance·태그와 지정 SSM document에 대한 실행·결과 조회. DB·IAM·VPC 관리자 권한과 운영 비밀값 직접 읽기 없음 |
| 프론트 게시 역할 | 지정 S3 버킷·prefix의 산출물 게시와 이전 릴리스 복원에 필요한 조회, 지정 CloudFront 배포의 invalidation 생성·완료 조회. 버킷 공개화·임의 자산 삭제·인프라 관리 권한 없음 |
| EC2 instance role | SSM agent, 해당 ECR pull, 해당 환경 시크릿·필요 KMS decrypt, 정해진 로그 기록 |
| 운영 관리자 | 계정 MFA·역할 기반 접근, 인프라 변경·복구 권한과 책임. 앱 배포 역할과 분리 |

SSM은 임의 shell 문자열을 넘기는 통로보다 root 소유 배포 스크립트를 호출하는 제한된 document를 제안합니다. 이미지 digest·release SHA 입력 형식을 검증하고 허용 ECR·저장소를 확인합니다. 대상 선택·문서 수정 권한까지 제한해야 합니다. EC2의 Docker 관리 권한은 호스트 관리자 권한으로 취급합니다. [ECR push 권한](https://docs.aws.amazon.com/AmazonECR/latest/userguide/image-push-iam.html), [SSM Run Command 설정](https://docs.aws.amazon.com/systems-manager/latest/userguide/run-command-setting-up.html)

RDS 자동 백업 보존은 초기 **7일 제안**이며, 실제 데이터 보존·삭제 정책과 함께 확정합니다. 삭제 방지·최종 snapshot·복원 연습을 설정합니다. PITR은 새 DB 인스턴스를 만들고 endpoint를 바꾸는 복구이므로, 쓰기 중지·복원 시점 이후 데이터 처리·설정 변경·재검증·구 DB 보존/폐기 절차가 필요합니다. RPO·RTO는 담당자와 부하·복원 시험 후 정하며 검증 전 숫자를 보장하지 않습니다. 암호화된 EBS와 재구축 가능한 호스트 설정도 관리합니다. [백업 보존](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_WorkingWithAutomatedBackups.BackupRetention.html), [RDS PITR](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PIT.html)

로그는 요청 ID·release SHA·상태·지연·SSE 종료 사유·모델 사용량 메타데이터를 중심으로 남깁니다. 기존 오류의 `X-Request-ID`와 AI의 `requestId`/`attempt`는 별개이며, 프록시부터 앱까지의 상관관계와 드레인 관측은 추가 구현 대상입니다. 쿠키·CSRF·비밀번호·API 키·요청/응답 원문·지원자 개인정보를 기록하지 않습니다. 로그 보존 14일을 초기 비용 검토값으로 두고, 데이터 종류별 보존 정책 확정 후 적용합니다. HTTP 오류율·지연, AI 오류/중단/429, DB 연결·스토리지, EC2 메모리·디스크, 인증서 만료, 백업·정리 작업 실패를 감시하고 실제 알림 수신자를 지정합니다.

AI 실행 메타데이터 정리는 기존 `python -m app.cli.ai_runs`를 **활성 릴리스 하나의 스케줄**에서 실행합니다. 초기 1시간 주기를 제안하며 실패·장기 미실행을 알립니다. 이 CLI는 대화 본문을 지우지 않습니다. [구현](../../backend/app/cli/ai_runs.py)의 기본 24시간 실행 보존과 일반 채팅의 저장·삭제 정책을 혼동하지 않습니다. 대화·백업·로그 보존은 #164, 종료 세션·인증 시도 기록 정리와 blocklist 운영은 #98에서 확정할 후속 작업입니다. 미구현 정리 명령을 이미 있는 것으로 취급하지 않습니다.

종료 세션의 물리 삭제는 `ai_runs`의 세션 참조와 `RESTRICT` 제약을 고려해 실행 메타데이터 정리 이후에 수행해야 합니다. 보존 정책을 결정한 뒤 삭제 순서·실패 재시도·백업 만료까지 검증하며, 기존 외래 키를 임의 cascade로 바꾸지 않습니다.

비용 계산에는 S3 저장량·요청·이전 자산 보관, CloudFront 전송·요청·invalidation, EC2·EBS·public IPv4, RDS 인스턴스/스토리지/백업, ECR·로그·시크릿/KMS·DNS/도메인·모델 사용량을 포함합니다. 계정 혜택과 리전·용량을 확인하기 전 무료 운영이나 월 총액을 약속하지 않습니다. AWS Budgets의 실제/예측 비용 알림을 설정하되 지출 상한으로 취급하지 않습니다. 테스트 자원은 소유자·만료일을 태그하고, 사용 후 자원·snapshot·이미지·IP·자산 보관까지 정리 대상을 확인합니다. [S3 가격 항목](https://aws.amazon.com/s3/pricing/), [CloudFront 가격 항목](https://aws.amazon.com/cloudfront/pricing/), [RDS 가격 항목](https://aws.amazon.com/rds/postgresql/pricing/), [public IPv4 비용](https://aws.amazon.com/vpc/pricing/), [Budgets 한계](https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html)

## 구현 작업과 완료 조건

[DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211)의 앱 계약을 구현했으며 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. DEP-01과 DEP-03~07은 **예정**이며 인프라·운영 배포는 수행하지 않았습니다. 아래 이슈를 상태·검증 기록의 원본으로 사용합니다.

### [DEP-01 #210](https://github.com/wejo-team/sku-dreamon/issues/210): 배포 대상과 비용·운영 책임 확정

- 수정 범위: 이 문서와 #165·#98·#164의 관련 결정 기록. 인프라 코드는 아직 생성하지 않음.
- 입력: 소유할 도메인과 `www`·`api` DNS, AWS 계정/리전·예산·자원 용량, 검증 환경과 운영 환경의 수명, 데이터·프론트 자산·인증서 보관과 운영 담당자.
- 출력: 자원별 비용표·환경 구분·DNS/TLS·알림·백업 담당자. 앱의 서울 `ap-northeast-2`는 후보값으로, CloudFront viewer 인증서의 `us-east-1` 요구와 구분.
- 완료 조건 **DEP-AC01**: AWS 전용 방향의 자원별 비용·책임과 같은 도메인 인증·검증 환경 격리·운영 보존/복구 목표를 결정. 계정 식별자·비밀값은 문서에 노출하지 않음.

### [DEP-02 #211](https://github.com/wejo-team/sku-dreamon/issues/211): 앱의 운영 준비 계약 구현

- 수정 범위: `backend/app/main.py`, `core/config.py`, `core/db/session.py`, `routers/health.py`, `services/ai.py`, `backend/alembic/env.py`, 관련 schema·tests. 운영 설정·readiness·CORS·DB TLS/pool과 스트림 정리 제한. `docs/api/`·`docs/development/`의 해당 계약도 갱신.
- 상태: 앱 계약 구현. 구현·검증 근거 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217). 운영 origin·DB·AI 제공 여부를 합성 설정으로 검증하며 실제 값 공급·배포는 후속. 입력은 `Settings`, 출력은 `/api/v1/ready`의 200/503와 기존 전송 계약.
- 완료 조건 **DEP-AC02**: 정상 origin의 쿠키/CSRF·preflight·오류 응답 성공, 악성/preview origin·위조 전달 IP 거부, DB/schema/설정 실패 때 ready 불가. health 검사로 모델 요청 0회.
- 검증: 새 CORS/readiness 단위·DB 통합 검사, TLS·설정 실패 검사, DB 연결 지연·row lock 중 스트림 예외/종료의 시간 제한·지연 정리 회수. 동작에 맞는 기존 backend CI 및 프론트 인증 계약 검사.

### [DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212): 실행 이미지·프록시·드레인 절차 구현

- 생성 예정: `backend/Dockerfile`, `.dockerignore`, `deploy/compose.production.yaml`, `deploy/nginx/`, `deploy/release.sh`, Certbot 기동·갱신 설정과 테스트. 기존 개발 `compose.yaml`은 운영 DB로 전환하지 않음.
- 선행: DEP-02. 입력은 image digest·SHA·설정 버전·전용 Docker 네트워크의 서비스 이름·timeout·인증서 런타임 저장소, 출력은 활성/이전 슬롯과 전환·드레인 결과.
- 완료 조건 **DEP-AC03**: 별도 Nginx를 유지하고 평소 활성 FastAPI 하나만 선택 기동·배포 중 비활성 슬롯을 추가해 둘 실행. 비root 앱·고정 의존성·신호 전달·앱 포트 비공개와 서비스 이름 해석 확인. 잘못된 readiness는 기존 슬롯 유지. fake provider SSE 중 reload에서 구 요청이 끝나고 새 요청은 새 슬롯 사용. 배포 lock·재실행·실패 복구 확인.
- 검증: 실제 Nginx·앱 컨테이너로 기본/최대 실행시간·중단·정상 종료·강제 장애와 DB 지연/잠금 중 종료를 구분. 컨테이너 재생성 후 upstream 해석·trusted proxy, 인증서 없는 최초 HTTP-01 기동·HTTPS 전환·자동 갱신·실패 경보 확인. Certbot·Nginx 재시작·재생성 후 영속 상태를 이용한 renewal dry-run과, 성공한 인증서 적용·새 후보 설정 검사/reload smoke를 각각 검증하며 dry-run만으로 인증서 적용을 입증하지 않음. TLS/proxy fixture에는 가상 계정·데이터만 사용.

### [DEP-04 #213](https://github.com/wejo-team/sku-dreamon/issues/213): 재현 가능한 AWS 기반과 접근 권한 준비

- 생성 예정: `infra/`의 IaC와 환경 예제, 호스트 bootstrap·SSM document, 운영 runbook. 도구는 Terraform 후보로 두고 팀 운영 방식과 state 암호화·잠금·권한을 DEP-01에서 확정.
- 선행: DEP-01·DEP-03. 입력은 확정한 계정/리전·자원 용량·네트워크·역할, 출력은 S3·CloudFront·OAC·ACM·VPC·EC2·RDS·ECR·시크릿 경로·OIDC 역할 참조와 DNS/TLS 경로.
- 완료 조건 **DEP-AC04**: S3 public access 차단·REST origin·OAC, CloudFront viewer의 DNS 검증 ACM 인증서, DB private·SG 최소 접근·TLS·암호화·SSM 운영·secret 권한·예산/알림 확인. 초기 ALB·Kubernetes 없음. RDS 기준안과 자체 PostgreSQL 후보 중 DEP-01에서 결정한 DB 구성 적용. CI·검증 환경에서 운영 데이터 복제 없음. 검증용 자원의 비용·철거 방법 기록.
- 검증: IaC 정적 검사/계획 검토 후 정해진 검증 환경에서 S3 직접 접근 거부·CloudFront 접근 허용, ACM 리전·DNS와 API HTTP-01 port 80, 최소 역할 권한·백업·호스트 재구축을 시험. 리소스 생성은 별도 실행 작업이며 현재 문서 수정에 포함되지 않음.

### [DEP-05 #214](https://github.com/wejo-team/sku-dreamon/issues/214): migration과 앱 롤백 검증

- 수정/생성 예정: `backend/alembic/`의 필요한 호환 변경, `deploy/`의 단일 migration·rollback 절차와 통합 테스트.
- 선행: DEP-03·DEP-04. 입력은 N/N−1 image·호환 schema 목록·백업 상태, 출력은 migration 기록·전환 가능 여부·검증된 rollback 대상.
- 완료 조건 **DEP-AC05**: N−1 요청을 처리하면서 expand 성공, 실패/잠금 초과 때 전환 차단, N·N−1 검증 통과 후 이전 digest로 복귀. 자동 파괴적 downgrade 없음.
- 검증: 버전 간 DB 통합 테스트·진행 중 SSE에서 migration·롤백·중복 migration 방지. 별도 복구 연습에서는 snapshot/PITR 새 endpoint의 데이터와 인증·API를 확인.

### [DEP-06 #215](https://github.com/wejo-team/sku-dreamon/issues/215): CI와 프론트·백엔드 배포 연결

- 생성 예정: `.github/workflows/deploy.yml`, `deploy/frontend/`의 게시·캐시·SPA rewrite·복원 설정과 release 검사 스크립트. 기존 필수 CI 이름과 문서 GitHub Pages workflow 책임 유지.
- 선행: DEP-01~05. 입력은 검증된 main SHA·image digest·동일 SHA의 `frontend/dist`와 manifest·S3/CloudFront 참조, 출력은 백엔드/프론트 릴리스 식별과 invalidation·배포 결과.
- 완료 조건 **DEP-AC06**: 정확한 SHA의 세 필수 검사 성공 때만 배포, 실패·대기·과거 rerun·fork는 거부. OIDC/환경 제한·전체 배포 직렬화·host lock·mock false·API 직접 호출 확인. 백엔드 전환/드레인 후 자산 우선·HTML 최종 게시, HTML Minimum TTL 0·해시 자산 immutable·구 자산 보존, 제한된 navigation rewrite, invalidation 완료와 외부 smoke까지 검증.
- 검증: 실패한 CI/오래된 SHA/동시 push, 백엔드 우선 전환과 이전 탭·동적 import 호환, 없는 자산의 오류 유지, HTML/자산 캐시 헤더와 직접 URL 재검증. 자산 업로드·HTML 게시·invalidation·smoke 단계별 실패를 주입해 이전 HTML/자산 복원·재무효화·완료 확인과 개별 롤백을 시험. 권한 시험은 정해진 검증 환경에서 수행.

### [DEP-07 #216](https://github.com/wejo-team/sku-dreamon/issues/216): 공동 HTTPS 검증과 운영 준비 판정

- 수정/생성 예정: 기존 `frontend/e2e/`·검증 runner의 원격 합성 데이터 경로, `docs/development/bug-bash.md`, 생성 예정 운영 runbook과 정리 스케줄. 로컬 전용 AI fixture의 DB·빈 키 제한을 완화하지 않음.
- 선행: DEP-06. 원격 fake provider 검사는 운영 이미지·운영 환경과 분리한 테스트 배포로 수행하며, 원격에서도 기본 업무 권한·쿠키 계약은 유지.
- 완료 조건 **DEP-AC07**: 데스크톱·모바일 브라우저의 가입/로그인/로그아웃/세션 만료, 팀·지원 흐름, AI heartbeat/delta/done·취소·권한 철회·배포 드레인·중복 방지 확인. Safari 등 실제 대상 기기는 수행 여부를 별도 기록.
- 완료 조건 **DEP-AC08**: 복원·롤백 연습, 알림 수신, 인증/AI 정리 작업과 보존 정책, 비용·로그 점검을 완료. 확인하지 않은 항목을 배포 완료 근거로 쓰지 않음.
- 모델을 실제 호출하는 품질·지연·비용 smoke는 #164의 별도 실행 단계로 남김. 그때 승인된 런타임 키·한도·합성 입력을 사용하고 호출 수를 기록. 문서·PR CI·readiness는 실제 모델 호출 없이 검증.

## API·DB 영향과 다음 결정

DEP-02는 기존 제품 endpoint·SSE 이벤트·쿠키·CSRF 계약을 유지하면서 readiness·credentialed CORS·검증 TLS·유한한 DB/SSE 정리 예산을 구현했습니다. 구현·검증 근거는 [PR #217](https://github.com/wejo-team/sku-dreamon/pull/217)입니다. DB 업무 schema 변경은 없으며 운영 권한·migration 실행·배포 경로 검증은 후속입니다. 로그·세션·대화의 삭제/보존 정책은 자동 확정하지 않고 기존 운영 이슈에서 검토합니다.

AWS 전용 호스팅 방향은 합의했으며, 구현 전에 정할 세부 사항은 **AWS 계정/앱 리전, 월 3만 원 미만 목표의 비용 충족 여부와 DB 호스팅, 도메인, 검증 환경 격리 수준, 자원 용량, 프론트 자산·인증서·데이터의 보관/복구 기준과 운영 담당자**입니다. 초기 제안은 서울 앱 리전·단일 EC2·Single-AZ RDS이며 CloudFront viewer 인증서는 `us-east-1`에 둡니다. 서버 크기와 월 비용은 견적·부하 측정으로 정하고, 팀 검증을 운영 공개보다 먼저 진행해 실제 사용자 데이터가 들어오기 전 정책을 확정합니다.

EC2 장애까지 감당해야 하거나 인스턴스 운영 부담이 커지면 ECS·ALB·복수 task와 RDS Multi-AZ를 별도 비교합니다. 그때도 connection draining·task 종료 유예·DB 호환성 검증이 필요하고 ALB·추가 task·Multi-AZ 비용이 늘어납니다. 서비스 가이드와 pgvector는 배포 기반과 운영 관측을 갖춘 뒤 별도 요구에 따라 검토합니다.
