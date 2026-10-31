# 단일 호스트 컨테이너 실행과 앱 교체

[DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212)의 실행 절차입니다. [제품 배포 계획](../development-plans/deployment-foundation.md)의 단일 호스트·별도 PostgreSQL 수명을 구현하며, AWS 자원 생성·ECR 게시·자동 CD·운영 용량·백업 정책은 후속 범위입니다. 아래 주소와 경로는 예시입니다. 실제 AWS·EBS나 공개 인증기관에 배포한 기록을 뜻하지 않습니다.

[단일 EBS 경로 #223](https://github.com/wejo-team/sku-dreamon/issues/223)은 기존 루트 EBS 하나에 OS·Docker·PostgreSQL 데이터를 함께 두는 구성을 다룹니다. 별도 DB EBS도 같은 검증 계약으로 선택할 수 있습니다.

## 실행 구성

원본은 [운영 Compose](../../deploy/compose.production.yaml), [앱 이미지](../../backend/Dockerfile), [Nginx 설정 생성기](../../deploy/nginx/render.py), [PostgreSQL 기동 검사](../../deploy/postgres/guard-entrypoint.sh), [배포 엔진](../../deploy/release.py)입니다. 개발용 루트 `compose.yaml`은 그대로 사용합니다.

| 서비스 | 수명과 접근 |
| --- | --- |
| `postgres` | 앱 교체와 별도 수명. 호스트 DB 포트 미게시, DB 전용 내부 네트워크, 자체 CA·`postgres` 서비스 호스트명 검증 TLS |
| `nginx` | 호스트 80/443만 게시. 정확한 API Host와 활성 앱 하나로 전달. readiness는 외부 404 |
| `app_blue`, `app_green` | 각각 `blue`, `green` profile. 평소 활성 하나, 교체 중 후보만 추가. 호스트 포트 미게시, 비root UID 10001, Uvicorn 한 프로세스 |
| `migrate` | 필요할 때 배포 lock 안에서 단일 Alembic job. 앱 시작 명령에 migration을 넣지 않음 |
| `certbot` | HTTP-01 최초 발급·갱신·dry-run job. ACME 계정과 `archive`·`live`·갱신 설정 전체를 영속화 |

앱은 `--no-proxy-headers`로 실행합니다. Nginx는 외부 전달 헤더를 버리고 실제 연결 IP 하나와 `https`만 설정합니다. `HTTP_TRUSTED_PROXIES`는 고정된 Nginx IP 하나, `HTTP_ALLOWED_HOSTS`는 정확한 API Host 하나입니다. credentialed CORS·쿠키·CSRF는 기존 제품 앱이 처리하며 Nginx에서 중복 설정하지 않습니다.

## 상태 확인과 실행 순서

운영 Compose는 계속 실행되는 서비스에 30초 간격의 `healthcheck`를 설정합니다. 시작 유예는 30초, 검사 제한은 3초, 연속 실패 기준은 3회입니다. 일회성 `migrate`·`certbot`은 작업 종료 상태를 배포 엔진이 확인합니다.

| 서비스 | 주기적으로 확인하는 범위 |
| --- | --- |
| `postgres` | TCP `127.0.0.1:5432`의 `pg_isready`. 초기화 중 임시 Unix socket 서버는 성공으로 판단하지 않으며 앱 계정의 인증·쿼리 권한까지 검증하지 않음 |
| `app_blue`, `app_green` | 컨테이너 내부 TCP `127.0.0.1:8000` 연결. HTTP 처리·DB·이벤트 루프의 정상 동작까지 검증하지 않음 |
| `nginx` | 컨테이너 loopback에만 열린 `127.0.0.1:8080/health`의 HTTP 응답. 앱·DB·인증서 상태와 독립적이며 해당 포트는 외부에 게시하지 않음 |

앱의 직접 localhost HTTP 호출은 기존 production 프록시 경계에서 거부됩니다. 주기 검사 때문에 trusted proxy를 넓히거나 `/ready`를 외부에 공개하지 않습니다. 새 앱의 실제 준비 여부는 배포 엔진이 trusted Nginx peer에서 `/api/v1/ready`를 직렬 호출해 검사하고, 전환 후 HTTPS 응답을 추가 확인합니다.

`depends_on` 대신 배포 엔진이 DB 기동 대기·필요한 migration·후보 앱 기동·readiness·Nginx 전환 순서를 제어합니다. 앱 교체는 `--no-deps`로 후보 슬롯만 재생성합니다. 이 절차는 EC2 재부팅 시 Docker의 자동 재시작 순서를 제어하지 않으며, 실제 호스트의 재부팅·EBS 재마운트·서비스 복구는 [AWS 기반 작업](https://github.com/wejo-team/sku-dreamon/issues/213)에서 확인합니다.

`docker compose ps`와 컨테이너의 `State.Health`로 상태를 확인할 수 있습니다. `unhealthy` 판정만으로 컨테이너가 재시작되거나 Nginx 경로가 바뀌지는 않습니다. `restart: unless-stopped`는 컨테이너 종료에 대응하며, 주기 상태 확인과 알림·복구 연결은 별도 운영 설정입니다.

<a id="host-prerequisites"></a>

## 호스트 준비와 권한

호스트에는 Python 3.13 이상, 로컬 Docker daemon, Compose v2의 `env_file.format: raw` 지원, `findmnt`·`realpath`가 필요합니다. Docker 관리와 파일시스템 검사는 호스트 관리자 권한입니다. 수동 검사 스크립트는 새 임시 loopback 파일시스템에만 root 권한을 사용합니다. 운영 파일시스템을 포맷하거나 Docker 사용자의 권한을 자동 변경하는 스크립트는 없습니다.

Amazon Linux 2023의 `/usr/bin/python3`는 시스템용 Python 3.9로 유지합니다. Python 3.13을 함께 준비하고 아래 배포 명령처럼 `sudo python3.13 deploy/release.py ...`로 호스트 배포 엔진을 명시적으로 실행합니다. `deploy/release.sh`는 `python3`를 직접 호출하므로 시스템 Python이 3.9인 환경에서는 이 명시적 호출을 사용합니다. `/usr/bin/python3` symlink를 교체하지 않습니다. [AL2023의 Python 버전](https://docs.aws.amazon.com/linux/al2023/ug/python.html)

기본 구성은 기존 루트 EBS의 파일시스템을 사용합니다. `postgres_mount_path`는 정확한 mountpoint인 `/`, `postgres_data_dir`은 `/var/lib/sku-dreamon/postgres/pgdata`로 명시합니다. `postgres_filesystem_uuid`에는 `findmnt --mountpoint / --output TARGET,SOURCE,FSTYPE,UUID`로 확인한 실제 루트 파일시스템 UUID를 공급합니다. 예를 들어 40 GiB 루트 EBS 하나라면 OS·Docker 이미지/캐시·로그·DB/WAL·백업 임시 파일이 같은 용량과 I/O를 공유하므로 여유 공간과 증가량을 함께 점검합니다. 이 용량은 일반 예시이며 운영 수용량을 보장하지 않습니다.

배포 엔진은 설정 경로를 정규화하고, 호스트 검사는 정규화한 경로가 정확한 mountpoint와 그 엄격한 하위 데이터 디렉터리인지 확인합니다. mountpoint 자체를 데이터 경로로 쓰지 않습니다. 호스트 검사는 정확한 mountpoint의 UUID·데이터 경로의 실제 장치 번호·쓰기 가능 여부도 확인합니다. PostgreSQL 컨테이너는 UUID 경로로 선택한 장치 node의 `stat` major:minor와 `PGDATA`의 mountinfo 장치를 대조한 뒤에만 공식 entrypoint를 실행합니다. 장치 node는 메타데이터 조회용 readonly bind로 전달하며 device cgroup에 원시 디스크 읽기 권한을 추가하지 않습니다. 다른 UUID·중첩된 다른 파일시스템이면 시작을 거부합니다.

별도 EBS를 선택하면 `postgres_mount_path`를 실제 DB 파일시스템의 mountpoint로, `postgres_data_dir`을 그 아래 `pgdata`로 설정하고 해당 UUID를 공급합니다. 별도 EBS가 마운트되지 않았을 때 루트 파일시스템의 빈 디렉터리로 대신 시작하는 동작은 허용하지 않습니다. 아래 준비 명령은 기존 루트 파일시스템에 디렉터리만 만들며 포맷·신규 볼륨 생성·`fstab` 변경을 하지 않습니다. 이미 bootstrap한 DB를 옮기는 작업은 설정 변경만으로 처리하지 않고 별도 백업·이동·복원 절차로 수행합니다.

배포 원본과 설정은 신뢰할 관리자만 변경할 수 있어야 합니다. 런타임은 Git checkout 밖의 root 소유 디렉터리로 둡니다.

```bash
sudo install -d -o root -g root -m 0700 /etc/sku-dreamon
sudo install -d -o root -g root -m 0700 /var/lib/sku-dreamon /var/lib/sku-dreamon/private
sudo install -d -o root -g root -m 0700 /var/lib/sku-dreamon/postgres/pgdata
sudo install -o root -g root -m 0600 deploy/runtime.example.json /etc/sku-dreamon/runtime.json
```

이 명령은 DB mountpoint나 파일시스템을 만들지 않습니다. 예시 JSON의 0 digest·UUID·비밀번호·CSRF 키·도메인을 실제 공급값으로 교체해야 실행할 수 있습니다. 실제 JSON·비밀값·키를 저장소나 CI artifact에 올리지 않습니다.

재부팅 후에도 `/`의 UUID와 데이터 경로 장치가 같은지, DB와 앱이 복구되는지 확인합니다. EC2를 종료(terminate)하면 루트 EBS는 기본적으로 삭제되므로 DB를 보존할 루트 볼륨의 `DeleteOnTermination=false`를 설정하고 실제 연결 속성에서 확인해야 합니다. 이 설정은 호스트 장애·실수·DB 손상을 복구하는 백업을 대신하지 않습니다. 실제 데이터를 저장하기 전에는 호스트 밖의 비공개 저장소에 `pg_dump`를 보관하고 첫 백업의 격리 복원을 확인합니다. 주기·보존·담당자와 실패 알림은 [PoC/MVP 복구 계획](../development-plans/deployment-foundation.md#poc-mvp-recovery)에서 정합니다. [EC2 종료 시 루트 EBS 보존](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configure-root-volume-delete-on-termination.html)

## 비공개 입력과 고정 이미지

[JSON 예시](../../deploy/runtime.example.json)와 [입력 검증기](../../deploy/config.py)가 필드의 원본입니다. 설정은 JSON으로만 읽고 `.env`를 shell에서 실행하지 않습니다. 허용한 app·migration·PostgreSQL 키만 받아 별도 파일을 생성합니다. 알 수 없는 키와 newline·NUL을 거부합니다. 앱의 raw env 파일은 `$`·인용부호·backslash를 문자 그대로 전달하고, Compose 자체 입력 파일은 별도로 생성합니다.

`runtime_dir/private`에는 아래 파일을 관리자가 공급합니다. 부모 디렉터리는 root 0700이며 컨테이너에는 필요한 파일만 개별 bind mount합니다.

| 파일 | 호스트 권한과 용도 |
| --- | --- |
| `db-ca.crt` | root 0644. 비root 앱·migration이 읽는 DB 신뢰 CA |
| `password-blocklist.txt` | root 0644. 앱이 읽으며 JSON의 version과 내용이 readiness 검사를 통과해야 함 |
| `postgres.crt`, `postgres.key` | 인증서 root 0644, 개인키 root 0600. DB guard가 필요한 런타임 사본 권한을 맞춤 |
| `postgres-bootstrap-password` | root 0600. PostgreSQL 최초 관리자 비밀번호 |
| `app-password`, `migration-password` | root 0600. 최초 생성하는 `dreamon_app`·`dreamon_migration`의 비밀번호 |

DB 이름은 `POSTGRES_DB`, 앱 역할은 `dreamon_app`, DDL 역할은 `dreamon_migration`으로 고정합니다. URL의 비밀번호는 원본 secret 파일과 같아야 하며 URL 구문에 맞게 percent encoding합니다. 두 URL 모두 `postgres` 서비스와 동일 DB를 가리킵니다. URL query로 TLS나 timeout을 덮어쓸 수 없습니다. 기존 DB가 있는 경우 init script가 계정을 재초기화하지 않습니다. DB 인증서는 올바른 CA `basicConstraints`·`keyUsage`, 서버 leaf의 `serverAuth`·`postgres` DNS SAN 등 strict X.509 검증을 통과해야 합니다. 수동 검사용 합성 인증서·개인키·계정을 운영에 재사용하지 않습니다.

`app_env`의 `AI_TIMEOUT_SECONDS`, `AI_CLEANUP_TIMEOUT_SECONDS`, `SHUTDOWN_TIMEOUT_SECONDS`는 명시적으로 입력합니다. AI 제공을 선택하면 `OPENAI_API_KEY`를 공급하고 필요한 경우 `AI_REQUIRED=true`로 설정합니다. 최초 bootstrap 뒤 [SSM 설정 관리](ssm-configuration.md)를 연결하면 `app_env` 전체의 원본은 고정된 SecureString parameter이며, runtime JSON과 env 파일은 코드·설정 배포가 생성하는 적용본입니다. [코드 CD](continuous-deployment.md)는 새 SHA에 조회 시점의 SSM 버전을 함께 적용하며, 직접 편집한 JSON을 다음 코드 배포로 적용하지 않습니다. 실제 모델 호출은 수동 컨테이너 검사에 포함하지 않습니다.

앱·migration·PostgreSQL env 파일은 내용 digest에 따라 불변 파일로 생성됩니다. journal은 각 앱의 이미지·설정 revision·파일 참조·timeout 예산을 보존합니다. 앱 교체 중 DB 접속 값·CSRF 키 변경과 공유 CA·blocklist 파일의 임의 변경을 차단합니다. 호스트·API Host·DB mount·인프라 이미지·네트워크 설정도 bootstrap 때의 비밀값 없는 fingerprint와 대조합니다. 키 회전·DB 이동·인프라 변경은 별도 운영 절차로 처리합니다.

설정만 바꿀 때는 [설정 전용 실행기](../../deploy/config_release.py)가 같은 이미지·SHA와 위 교체 엔진을 사용합니다. 1차 허용 변수와 rollback·중단 복구 경계는 [SSM 운영 가이드](ssm-configuration.md)에 정의하며, 일반 `release.py deploy`나 동일 SHA의 코드 CD 재실행으로 대체하지 않습니다. 같은 SHA의 설정 교체·rollback을 직접 실행하는 경로와 설정 또는 코드·설정 결합 배포의 진행 기록이 남은 동안의 일반 release·인증서 명령은 차단합니다. 코드·설정 전환 복구는 [코드 CD 실행기](continuous-deployment.md)의 호스트 `recover` 명령을 사용합니다.

앱 이미지는 전체 commit SHA를 `RELEASE_SHA` build argument와 OCI revision label에 넣어 빌드합니다.

```bash
release_sha=$(git rev-parse HEAD)
docker build --file backend/Dockerfile --build-arg RELEASE_SHA="$release_sha" --tag sku-dreamon-api:build .
docker build --file deploy/nginx/Dockerfile --tag sku-dreamon-nginx:build deploy/nginx
docker build --file deploy/postgres/Dockerfile --tag sku-dreamon-postgres:build .
```

registry 게시·인증·배포 호스트로의 이미지 전달은 후속 배포 경로에서 담당합니다. 엔진이 사용할 앱 이미지는 호스트에 준비되어 있어야 합니다. 배포 입력은 `repository@sha256:<64자리>`이며 mutable tag는 거부합니다. 격리 수동 검사에서는 Docker가 검증한 로컬 `sha256:<64자리>` image ID를 사용합니다. 엔진은 요청 digest·OCI revision·실제 컨테이너 image ID와 저장한 환경설정을 확인합니다. 운영 이미지는 제품 소스와 고정된 production 의존성만 포함하며 테스트 모델은 별도 파생 fixture 이미지에만 들어갑니다.

## 최초 실행

운영 도메인의 HTTP-01 경로에 접근할 수 있는 상태에서 수행합니다. 인증서가 없는 최초 Nginx는 challenge와 HTTP 경로만 읽으므로 앱 DNS나 HTTPS 개인키를 필요로 하지 않습니다.

```bash
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json bootstrap
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json certificate issue --email ops@example.com
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json deploy --image registry.example.com/sku-dreamon-api@sha256:0000000000000000000000000000000000000000000000000000000000000000 --sha 0000000000000000000000000000000000000000 --migrate
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json status
```

`bootstrap`은 빈 journal에서만 PostgreSQL과 HTTP Nginx를 시작하고 PostgreSQL의 최종 TCP listener 준비를 제한 시간 안에 확인합니다. 기존 unmanaged 컨테이너를 임의로 인수하지 않습니다. 발급 성공 후 첫 앱을 시작하고 trusted Nginx peer에서 production readiness를 직렬 검사한 뒤 HTTPS 후보 설정 전체를 `nginx -t -c <후보>`로 검사합니다. 검사한 설정을 원자적으로 설치·reload하고 새 HTTPS 연결의 release SHA·slot을 확인합니다.

`--migrate`는 최초 schema 준비나 실제 변경이 필요할 때만 사용합니다. 이름을 먼저 journal에 기록하고 detached job의 실제 종료 상태를 확인하므로, Docker CLI나 원격 연결이 끊겨도 살아 있는 migration과 두 번째 job을 겹쳐 실행하지 않습니다. 실행 중·실패·사라진 job은 새 전환을 차단합니다. 호환 revision은 이미지의 [고정 호환 목록](../../backend/app/core/db/revisions.py)과 readiness가 검사하며 JSON으로 임의 확장하지 않습니다.

## 앱 교체·복구·롤백

다음 교체도 같은 `deploy` 명령을 사용하며 migration이 필요하지 않으면 `--migrate`를 생략합니다. 엔진은 활성 슬롯과 journal·실제 이미지·설정 hash·DB 컨테이너 ID를 대조합니다. 비활성 후보만 재생성하고 후보 실패 때 활성 경로를 유지합니다. 앱 교체나 롤백에서 PostgreSQL stop·recreate·버전 변경·volume 삭제·Alembic downgrade를 실행하지 않습니다.

reload 전에 이전 Nginx worker의 PID와 process start identity, Nginx 컨테이너·master identity를 기록합니다. 새 HTTPS 요청은 새 슬롯을 사용하고 기존 worker는 진행 중인 요청을 처리합니다. 엔진은 **이전 worker의 종료를 관측한 뒤에만** 이전 앱에 graceful stop을 요청합니다. reload 명령의 exit code만으로 전환 성공을 판단하지 않습니다.

```bash
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json status
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json recover
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json rollback
```

`status`는 phase·slot·SHA·image ID·config revision·안전한 실패 코드만 출력합니다. 실패나 중단이 남으면 다음 deploy와 슬롯 재사용을 거부합니다. `recover`는 저장한 의도와 현재 설정 hash·컨테이너·worker를 대조하여 전환 전 후보 정리, 모호한 reload 재개, 드레인 후 정리 등을 수행합니다. 설정 drift·DB 교체·드레인 중 Nginx master나 컨테이너 재생성은 자동으로 덮어쓰지 않고 관리자 대조를 요구합니다. 새 트래픽 검사 실패 시 이전 후보를 같은 절차로 검사·복귀하고 실패 슬롯의 연결도 드레인한 뒤 종료합니다. 최초 앱의 전환 실패는 HTTP bootstrap 설정으로 복귀합니다.

rollback은 기록된 이전 이미지와 **그 이미지의 설정 파일**을 사용합니다. 현재 DB revision에 호환되는 이전 앱만 readiness를 통과합니다. 복귀 가능한 앱이 없거나 DB가 비호환이면 차단하며 데이터를 자동으로 되돌리지 않습니다.

## 드레인 예산과 실패의 의미

예산의 원본은 `deploy/config.py`의 `Budgets`입니다. 전체 AI 응답 상한은 `AI_TIMEOUT_SECONDS + 9 + AI_CLEANUP_TIMEOUT_SECONDS`이며 일반 요청 상한과 비교해 큰 값에 운영 여유를 더합니다. Nginx의 전환 드레인은 구·신 릴리스 예산 중 큰 값을 사용하므로 새 timeout을 줄여도 구 스트림의 한도를 잃지 않습니다. 앱별 Uvicorn·Docker 유예는 해당 앱의 실제 설정과 별도로 보존합니다.

| 기본 입력: AI 90초·공유 정리 5초·자원별 종료 10초·일반 요청 30초·운영 여유 10초 | 계산값 |
| --- | --- |
| 전체 응답 상한 | 104초 |
| 프록시 read/send·엔진 드레인 | 114초 |
| Nginx worker shutdown 한도 | 129초 |
| Uvicorn graceful shutdown | 169초 |
| Docker stop 유예 | 179초 |

제품 설정 최대인 AI 300초·공유 정리 30초·자원별 종료 30초와 같은 일반 요청·운영 여유를 넣으면 각각 339·349·364·464·474초입니다. 이 표는 계산값이며 해당 시간 동안 실제 벽시계 부하를 실행한 증거가 아닙니다. 실제 컨테이너 실행의 설정·경과 시간은 수동 실행 결과 파일로 별도 확인합니다. 일반 요청 상한·여유는 운영 부하와 DB 지연 시험으로 다시 결정해야 합니다. 프록시 read timeout은 idle 제한이며 요청 전체 deadline을 강제하는 장치가 아닙니다.

드레인 기한까지 worker가 남으면 실패를 기록하고 이전 앱을 유지합니다. 이후 worker가 없어져 `recover`로 안전하게 정리하더라도 기한 내 정상 완료를 관측했다는 기록으로 바꾸지 않습니다. Docker의 강제 종료·OOM도 정상 종료로 취급하지 않습니다. 프로세스 강제 kill·호스트 장애·취소를 무시하는 외부 코드를 투명한 교체로 보장하지 않습니다.

## 인증서 갱신과 알림 연결

```bash
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json certificate dry-run
sudo python3.13 deploy/release.py --config /etc/sku-dreamon/runtime.json certificate renew
```

발급·갱신도 동일 host lock과 이름을 기록한 단일 Certbot job을 사용합니다. 성공한 deploy hook만 인증서 파일 hash 이벤트를 남깁니다. 실제 갱신 이벤트가 생기면 전체 후보 설정 검사·reload·새 HTTPS 인증서 fingerprint와 슬롯 확인·기존 worker 드레인까지 진행합니다. dry-run은 실제 발급 상태나 적용 성공으로 계산하지 않으며 reload하지 않습니다. 실패나 살아 있는 job을 자동 재실행하지 않고 `status`·`recover`로 상태를 확인합니다.

갱신·dry-run은 `--no-random-sleep-on-renew`로 Certbot 내부 무작위 대기를 끕니다. 이 대기가 host lock을 잡은 채 300초 작업 제한을 초과하지 않도록, scheduler의 systemd timer에 `RandomizedDelaySec`를 설정해 lock 획득 전에 실행 시각을 분산합니다. 최초 `certonly` 발급에는 이 갱신 전용 옵션을 넣지 않습니다.

Certbot의 `/etc/letsencrypt` 전체와 webroot·work·logs는 런타임에 남습니다. Nginx에는 인증서 상태를 읽기 전용으로 전달합니다. webroot는 Nginx worker가 읽을 수 있게 0755이며 계정·키 저장소는 root 전용입니다. 별도 ACME 서버를 명시적으로 선택할 때는 HTTPS `--server`와 root 전용 `--ca-file`로 해당 신뢰 CA를 공급할 수 있습니다. 이 옵션의 존재를 실제 ACME 발급·갱신 검증 완료로 계산하지 않습니다. 인증서 검증을 끄는 옵션은 제공하지 않습니다.

호스트 scheduler·실패 통보 수신자·인증서 만료 감시는 후속 운영 설정입니다. scheduler는 이 명령의 nonzero exit와 안전한 실패 코드에 알림을 연결하고, 실패 후에는 같은 job을 무한 반복하지 않아야 합니다. 이 저장소에 외부 알림 전송이나 운영 cron 설치가 완료되었다고 해석하지 않습니다.

<a id="verification"></a>

## 검증과 범위

```bash
python3.13 -m unittest discover -s deploy/tests -p 'test_*.py' -v
sudo python3.13 deploy/tests/container_e2e.py
```

첫 명령은 배포 journal·실패·중단 복구·설정 검증과 정적 런타임 계약을 검사합니다. 두 번째 명령은 Linux 로컬 Docker와 새 합성 loopback mount가 필요하며 실제 운영 데이터에 실행하지 않습니다. 실제 Nginx·PostgreSQL 17·production 앱 이미지와 별도 fixture 파생 이미지를 사용합니다. 원본 제품의 localhost 전용 E2E 보호 조건을 넓히지 않고 컨테이너 fixture는 별도 opt-in·`postgres` 호스트·`*_e2e` DB·빈 모델 키를 요구합니다.

수동 스크립트의 범위는 실제 이미지·HTTP bootstrap·명시적으로 신뢰한 단일 자체 서명 SAN 인증서·앱 교체/롤백·DB 컨테이너와 데이터 보존·짧은 fixture SSE입니다. 인증서는 기존 DB TLS 단위 검사와 같은 패턴을 사용하며, 공개 ACME 호출이나 별도 ACME 시험 서버는 사용하지 않습니다.

이 배포 기반 PR은 기존 앱 CI를 유지하며 새 필수 컨테이너 job을 추가하지 않습니다. CI 변경은 별도 PR로 다룹니다. 수동 실행 결과는 실행한 SHA와 `deploy/test-results/container-e2e.json`의 안전한 JSON으로 확인합니다. 소스 파일 존재·unit 통과·이전 SHA의 결과로 현재 SHA의 실제 실행을 대신하지 않습니다. AWS의 실제 EBS 부착·재부팅·복원·공개 ACME·운영 부하·비용·모델 제공자 검증은 포함하지 않습니다.

2026-10-30에 [단일 EBS 지원 코드 커밋](https://github.com/wejo-team/sku-dreamon/commit/c381b023c4f6aefe73453016e2d199330691df34)의 루트 경로 선택·별도 마운트 회귀·Compose 해석을 포함한 단위/정적 검사 41개와 격리 Docker-in-Docker의 production Compose·PostgreSQL guard 수동 검사 8개를 통과했습니다. 수동 검사는 합성 loop 장치 두 개로 정상 기동·SQL·장치 메타데이터 조회, 컨테이너 root와 postgres 사용자의 원시 디스크 읽기 차단, 다른 loop 데이터 마운트 거부, UUID 장치 경로 제거 후 재시작 거부를 확인했습니다. 단일 루트 EBS 경로는 설정/호스트 단위 검사로 확인했으며 실제 장치 연결 검사는 합성 loop 대상입니다. AWS·AL2023·실제 루트 EBS의 실행 검증과 운영 배포는 수행하지 않았습니다. 새 CI job·외부 모델·공개 ACME 호출은 추가하지 않았으며, 문서 원본 67개 링크/앵커·사이트 빌드·생성 링크 검사도 통과했습니다. 후속 실행 기록은 [#223](https://github.com/wejo-team/sku-dreamon/issues/223)에서 확인합니다.

2026-10-30에 [검증한 코드 커밋](https://github.com/wejo-team/sku-dreamon/commit/fb7d25b449447baee5630c9e47a338b3aa370021)의 배포 단위·정적 검사 40개와 전체 수동 컨테이너 검사 11개를 통과했습니다. 수동 검사는 기존 호스트 데이터나 Docker socket을 공유하지 않는 임시 Docker-in-Docker 환경에서 합성 loopback 디스크·인증서·계정으로 실행했습니다. Docker 29.8.0·Compose 5.5.1·검사 호스트 Python 3.14.10을 사용했고, 제품 이미지는 Dockerfile의 Python 3.13.14를 유지합니다. 전체 실행은 100.75초, 짧은 인증 SSE와 앱 전환 관측 구간은 14.95초였습니다. 이는 해당 격리 실행의 기록이며 운영 성능 기준은 아닙니다.

인증서 없는 HTTP 기동, PostgreSQL 검증 TLS와 migration, 제품 HTTPS·CORS·전달 헤더 경계, 앱 교체·롤백 중 DB 데이터와 컨테이너·Nginx 유지, 실패 후보의 기존 경로 보존과 recover를 확인했습니다. 후보 컨테이너의 TCP health가 `healthy`여도 `/ready` 실패로 전환이 차단됐고, 새 요청이 새 슬롯에 도달한 뒤 기존 SSE와 Nginx worker가 종료되어 이전 앱이 중지되는 것을 확인했습니다. 수동 실패 fixture는 FastAPI의 지연된 included router보다 앞에서 `/ready` 503을 반환하도록 구성합니다.

로컬 실행 근거는 Git에서 제외한 `deploy/test-results/container-e2e.json`과 소스 커밋·파일 hash를 담은 `container-e2e-source.json`에 보관합니다. 이미지의 blue/green 릴리스 표식은 합성 값이며 실제 검사 소스 커밋과 구분합니다. 임시 컨테이너·볼륨·loopback 자원은 정리했습니다. 일반 단위 검사와 CI에는 인증서 생성·수동 컨테이너 검사를 추가하지 않았습니다.

실제 도메인의 HTTP-01 최초 발급·재생성 후 갱신과 새 인증서 적용, 최대 300초 AI 설정의 전체 벽시계 스트리밍, DB 지연·행 잠금·종료 조합의 종합 검증은 최초 운영 환경 확인으로 남깁니다. 배포·인증서 명령과 timeout unit이 있다는 사실로 이 검증을 완료 처리하지 않습니다. 후속 실행 결과는 [DEP-03 #212](https://github.com/wejo-team/sku-dreamon/issues/212)에 기록합니다.
