# SSM 백엔드 설정 관리와 재배포

백엔드 HTTP 앱의 `app_env` 전체를 SSM Parameter Store의 **단일 SecureString JSON**으로 관리합니다. 운영자는 적용할 버전을 지정하고, 서버는 현재 코드 SHA·이미지 digest를 유지한 채 앱 컨테이너를 교체합니다. 설정 조회·후보 검증·전환이 실패하면 작업 전 설정으로 복구합니다. 이 문서는 실행 계약을 설명하며 실제 AWS 권한 설치·운영 적용·복구 시험의 완료 기록을 대신하지 않습니다.

원본은 [SSM 조회기](../../deploy/ssm_config.py), [설정 교체 실행기](../../deploy/config_release.py), [GitHub 실행기](../../deploy/config_cd.py), [수동 workflow](../../.github/workflows/config-deploy.yml)와 [SSM 명령 문서](../../deploy/ssm-production-config.json)입니다. 앱의 변수 이름·기본값·값 검증은 기존 [Settings](../../backend/app/core/config.py)를 따릅니다.

## 원본과 적용본

| 위치 | 책임 |
| --- | --- |
| SSM의 고정된 환경별 parameter | `app_env` 전체의 원본. 일반 설정과 비밀값을 같은 SecureString 버전에 보관 |
| `/etc/sku-dreamon/ssm-config.json` | root 0600. 조회할 리전·parameter 이름만 고정 |
| `/etc/sku-dreamon/runtime.json` | root 0600. 현재 적용된 `app_env`·설정 revision과 기존 호스트·DB 실행 정보 |
| `runtime_dir/private/app-<digest>.env` | 슬롯별로 생성한 불변 적용본. 컨테이너 환경변수로 전달 |
| `runtime_dir/private/config-<digest>.json` | 설정 작업 전·후의 비공개 런타임 snapshot. 실패·중단 복구용 |
| `runtime_dir/state/config-pending.json` | 완료되지 않은 설정 작업의 식별자와 snapshot 참조 |

중앙화 이후 `runtime.json`의 `app_env`나 생성된 env 파일을 직접 편집하지 않습니다. 설정은 SSM에서 버전을 만든 뒤 적용합니다. 로컬 개발 `.env`, CI의 격리 DB 설정, DDL용 `migration_env`, PostgreSQL 초기 비밀번호·TLS/차단 목록 파일과 호스트 설정은 이번 중앙화 대상과 수명이 다릅니다.

SSM 값을 수정한 것만으로 실행 중인 앱이 바뀌지 않습니다. 앱 요청마다 SSM을 조회하지 않으며, 재배포가 지정한 `name:version`을 한 번 읽습니다. 한 JSON 버전이 설정 집합 전체를 나타내므로 조회 도중 서로 다른 parameter 버전이 섞이지 않습니다. 키가 없거나 권한·복호화·형식 검증이 실패하면 최신 버전이나 로컬 값으로 대체하지 않습니다. [AWS GetParameter 버전 조회](https://docs.aws.amazon.com/systems-manager/latest/APIReference/API_GetParameter.html)

## 1차 변경 범위

설정 원본에는 **현재 `app_env` 전체**를 넣습니다. 숫자·boolean·JSON 배열 형태의 환경변수도 문자열 값으로 표현합니다. 예를 들어 `AI_REQUIRED`는 `"true"`, `AUTH_ALLOWED_ORIGINS`는 `"[\"https://www.example.com\"]"`입니다. 변경할 키만 보내는 부분 patch는 지원하지 않습니다. 알 수 없는 키·중복 JSON 키·개행·NUL과 8 KiB를 넘는 값을 거부합니다.

일반 설정 재배포에서 바꿀 수 있는 키는 [실행기의 `MUTABLE_KEYS`](../../deploy/config_release.py)에 한정합니다.

| 변경 가능 | 예 |
| --- | --- |
| AI 설정 | `OPENAI_API_KEY`, `AI_REQUIRED`, 현재 Settings가 허용하는 `AI_*` |
| 실행 추적 | `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT`, `LANGSMITH_WORKSPACE_ID`, `LANGSMITH_HIDE_INPUTS`, `LANGSMITH_HIDE_OUTPUTS` |
| 인증 요청 제한 | `AUTH_LOGIN_ACCOUNT_LIMIT`, `AUTH_LOGIN_IP_LIMIT`, `AUTH_SIGNUP_IP_LIMIT`, `AUTH_AVAILABILITY_IP_LIMIT` |
| 준비·종료 제한 시간 | `READINESS_TIMEOUT_SECONDS`, `SHUTDOWN_TIMEOUT_SECONDS` |

DB URL·DB pool/TLS 설정, CSRF 키, origin·Host·trusted proxy, 차단 목록 경로·버전, `APP_ENV`는 기존 적용값과 같아야 합니다. 이 키의 추가·삭제도 변경으로 취급합니다. DB 자격증명 회전·CSRF 키 회전·공유 CA/차단 목록 교체·호스트/네트워크 변경은 별도 절차로 처리합니다. AI 키의 실제 제공자 유효성·할당량은 `/ready`에서 호출해 검사하지 않습니다.

LangSmith는 키가 있으면 항상 추적합니다. 해당 코드를 먼저 릴리스한 뒤 SSM bundle에 키·운영 프로젝트를 등록하고 설정 재배포로 적용합니다. 운영 AI에 키가 없으면 초기화 경고를 남기며 서비스 시작은 허용합니다. 키 교체와 프로젝트·입출력 숨김 변경도 같은 설정 재배포 절차로 적용합니다. 기존 `LANGSMITH_TRACING`은 bundle·rollback 호환용으로 허용하지만 앱은 값을 무시하므로 `false`로 추적을 끌 수 없습니다. 새 bundle에는 이 키를 추가하지 않습니다.

LangSmith의 실제 접속은 readiness 조건으로 사용하지 않습니다. 자동 추적의 원문 범위·masking과 프로젝트 접근·보존 확인은 [실행 추적](langsmith-tracing.md)을 따릅니다.

프론트 `VITE_*`는 빌드에 포함되는 공개 설정이므로 이번 workflow에서 변경하지 않습니다. 설정 재배포는 이미지 build/push, 프론트 게시, DB migration·DB 컨테이너 교체를 실행하지 않습니다.

## 최초 연결

먼저 이 기능을 포함한 코드를 `작업 브랜치 → develop → main`으로 릴리스하고 [운영 CD](continuous-deployment.md)가 성공했는지 확인합니다. SSM 명령은 현재 운영 소스의 `/opt/sku-dreamon/current/deploy/config_release.py`를 실행합니다. 최초 코드 릴리스 전에 설정 workflow를 실행하면 이 파일이 없어 실패하며 이전 실행기로 대체하지 않습니다.

호스트에는 기존 Python 3.13·Docker·Compose와 AWS CLI v2가 필요합니다. `/etc/sku-dreamon/cd.json`은 기존 CD의 root 전용 설정을 그대로 사용합니다. 관리자는 `/etc/sku-dreamon/ssm-config.json`을 root 소유·0600·직접 파일로 준비합니다. 아래는 가상 예시이며 요청 입력으로 parameter 경로나 리전을 바꿀 수 없습니다.

```json
{
  "region": "ap-northeast-2",
  "parameter_name": "/sku-dreamon/production/backend"
}
```

역할은 다음 책임으로 나눕니다. 이 문서의 설명만으로 AWS 권한이 설치되지는 않습니다.

- **운영자 설정 관리 역할:** 지정 parameter에 새 버전을 쓰는 `ssm:PutParameter`와 사용하는 KMS 키의 암호화 권한. 실제 값 등록·변경은 이 역할의 임시 권한으로 수행합니다.
- **EC2 instance role:** 지정 parameter 하나의 `ssm:GetParameter`와 복호화에 필요한 KMS 권한. customer-managed key를 사용하면 해당 키의 `kms:Decrypt`와 key policy도 맞춥니다. parameter 목록·전체 경로 조회·쓰기 권한은 필요하지 않습니다.
- **GitHub production 배포 역할:** 지정 서버와 설정 전용 SSM 명령 문서에 대한 실행·결과 조회. Parameter Store 값이나 KMS 평문을 읽는 권한을 주지 않습니다. 기존 OIDC의 저장소·`production` environment·audience 제한을 유지합니다.

`deploy/ssm-production-config.json`을 별도 SSM Command 문서로 등록하고 GitHub `production` environment에 `DEPLOY_CONFIG_SSM_DOCUMENT`를 설정합니다. 기존 `AWS_REGION`, `AWS_ROLE_ARN`, `DEPLOY_INSTANCE_ID`를 함께 사용합니다. workflow는 **설정 문서 버전 1**을 명시하므로 CLI 계약을 바꿀 때 문서와 실행기를 함께 관리합니다. SSM Agent는 `interpolationType: ENV_VAR`를 지원해야 하며 문서 내용 수정 권한은 운영 관리자에게만 둡니다.

## 설정 등록과 변경

첫 parameter는 현재 정상 동작 중인 `runtime.json`의 `app_env`에서 만듭니다. 코드 배포·설정 작업을 겹치지 않게 하고 아래 `status`로 `phase=stable`, `config_phase=idle`을 확인한 뒤 진행합니다. 이후 변경도 현재 적용본을 기준으로 전체 JSON을 준비하면 아직 적용하지 않은 버전의 값을 섞는 일을 줄일 수 있습니다.

다음은 **런타임 파일을 읽을 수 있는 관리자 세션**에서 값은 출력하지 않고 root 전용 파일로 내보내는 예입니다. 기존 파일은 덮어쓰지 않습니다.

```bash
sudo python3.13 - <<'PY'
import json
import os
from pathlib import Path

runtime = json.loads(Path('/etc/sku-dreamon/runtime.json').read_text())
target = '/etc/sku-dreamon/backend-parameters.json'
descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w') as output:
    json.dump(runtime['app_env'], output, ensure_ascii=False, separators=(',', ':'))
PY
```

접근 제한 파일을 준비한 **설정 관리 역할의 임시 권한 세션**에서 다음과 같이 등록합니다. 파일에 접근할 수 있는 실행 환경이어야 합니다. EC2의 기본 읽기 전용 역할에 parameter 쓰기 권한을 추가해 실행하지 않습니다. `--value`에는 `file://` 경로를 사용하여 실제 값을 명령 인자·shell history에 넣지 않고, 결과도 버전 번호만 출력합니다.

```bash
aws ssm put-parameter \
  --region ap-northeast-2 \
  --name /sku-dreamon/production/backend \
  --type SecureString \
  --tier Standard \
  --overwrite \
  --value file:///etc/sku-dreamon/backend-parameters.json \
  --query Version \
  --output text
```

위 예시는 AWS 관리형 SSM 키를 사용합니다. 별도 KMS 키를 선택했다면 `--key-id`에 그 키를 지정하고 역할·key policy를 맞춥니다. 파일은 공개 저장소·PR·CI artifact에 넣지 않으며, 편집·전송·보관도 운영 비밀값의 접근 경계를 따릅니다. `--debug`나 shell tracing으로 원문을 기록하지 않습니다.

Standard parameter는 값이 **4 KiB 이하**, Advanced는 **8 KiB 이하**입니다. UTF-8로 직렬화한 JSON 전체 크기를 기준으로 선택합니다. Advanced는 과금되며 Standard로 다시 내릴 수 없으므로 실제 크기가 4 KiB를 넘을 때 운영 비용과 함께 판단합니다. 조회기는 8 KiB까지 허용합니다. [AWS parameter 등급](https://docs.aws.amazon.com/systems-manager/latest/userguide/parameter-store-advanced-parameters.html), [PutParameter](https://docs.aws.amazon.com/cli/latest/reference/ssm/put-parameter.html)

## 설정 전용 실행

GitHub Actions의 **Production configuration**에서 **Run workflow → main**을 선택합니다. `production` environment의 허용 브랜치도 `main`으로 유지합니다. `develop`·PR·fork에서 운영 설정을 적용하지 않습니다.

| action | parameter_version | 동작 |
| --- | --- | --- |
| `status` | `0` | 활성·이전 코드 SHA, env hash, 설정 revision, 진행 상태 조회 |
| `apply` | 등록 결과의 정확한 양수 버전 | 현재 이미지·코드를 유지하고 해당 SSM 버전으로 앱 교체 |
| `rollback` | `0` | 같은 코드 SHA·이미지의 직전 설정으로 복귀 |
| `recover` | `0` | 중단된 설정 작업을 작업 전 상태로 복구 |

`apply`는 최신 `main`의 `Frontend`, `Backend`, `Validate docs` 성공을 요구합니다. `status`·`rollback`·`recover`는 최신 `main`의 실행 소스를 사용하되 새 코드의 CI 실패 때문에 기존 설정 복구가 막히지 않도록 검사 성공과 독립적으로 실행합니다. 모든 작업은 기존 코드 CD와 같은 `production-deploy` concurrency를 사용하고 진행 중 작업을 새 실행 때문에 취소하지 않습니다.

서버에서만 상태를 확인해야 할 때는 다음 명령을 사용할 수 있습니다. 설정값은 출력하지 않습니다.

```bash
sudo python3.13 /opt/sku-dreamon/current/deploy/config_release.py \
  --cd-config /etc/sku-dreamon/cd.json \
  --source-config /etc/sku-dreamon/ssm-config.json \
  --action status
```

실행기는 상태 조회에서 얻은 코드 SHA·env hash·설정 revision을 서버에 전달하고, 서버가 잠금 안에서 다시 대조합니다. 사이에 다른 배포가 끝났다면 오래된 요청을 적용하지 않습니다. 설정 revision은 `ssm-<parameter 버전>-<내용 식별자>`이며 같은 요청 재실행은 같은 설정이면 `unchanged`로 끝납니다.

적용 순서는 **고정 SSM 버전 조회 → 설정 형식·변경 범위 검증 → 이전/후보 snapshot과 진행 기록 저장 → 같은 이미지의 반대 슬롯 기동 → 기존 `/ready`·Nginx·HTTPS 검사 → 기존 연결 종료 확인 → 적용된 runtime JSON 게시**입니다. 기존 앱·DB 수명과 드레인 규칙은 [컨테이너 실행 가이드](container-deployment.md)를 따릅니다. 성공 후 코드 CD도 게시된 설정을 사용합니다. 코드 CD는 runtime의 `app_env`·revision이 실제 활성 슬롯과 일치해야 진행하며, SSM 최신 버전을 자동 적용하지 않습니다.

동일 코드 SHA의 설정 적용·rollback·recover는 반드시 설정 전용 실행기를 사용합니다. 기존 코드 CD나 직접 `release.py` 명령으로 같은 SHA의 설정만 교체·rollback하는 경로는 runtime 입력 갱신을 우회하므로 차단합니다.

## 실패와 복구

- **SSM 조회·입력 검증 실패:** 기존 앱과 적용 설정을 유지합니다. 누락된 버전·읽기/KMS 권한·JSON·허용 변경 범위를 확인합니다.
- **`configuration_failed_restored`:** 후보 전환이 실패했고 작업 전 앱과 설정의 복구 검사가 완료됐습니다. 작업 결과는 실패로 남습니다.
- **`configuration_recovery_required` 또는 `config_phase=pending`:** 복구가 끝났다고 확인할 수 없습니다. `status`와 SSM 명령 결과를 확인하고 `recover`를 실행합니다. 실행 중 프로세스가 있으면 잠금이 먼저 차단하므로 동시에 강제로 실행하지 않습니다.
- **SSM 응답 유실·runner 중단:** 성공으로 추정하지 않습니다. 명령 ID의 실제 종료와 호스트 상태를 확인합니다. 중단 기록이 남으면 `recover`는 후보를 이어서 확정하지 않고 작업 전 상태로 돌아갑니다.
- **snapshot·실행 상태 불일치:** 임의로 journal·env hash·활성 슬롯을 고쳐 통과시키지 않습니다. 복구 자료를 보존하고 해당 오류의 원인을 확인합니다.

복구가 확인되기 전에는 새로운 설정 적용과 코드 CD를 차단하고, 백업도 혼합된 설정을 정상 백업으로 기록하지 않도록 거부합니다. 진행 기록이 남아 있을 때 직접 `release.py`·인증서 명령으로 상태를 바꾸지 않으며 설정 실행기의 `recover`로 먼저 복구합니다. 이전 설정 복구는 `runtime.json`도 되돌리므로 다음 코드 배포가 실패했던 설정을 다시 사용하지 않습니다.

`rollback`은 journal에 남은 **같은 코드·이미지의 직전 설정**만 사용하며 SSM 조회 없이 수행합니다. 코드 배포로 이전 슬롯이 다른 SHA가 되면 설정 rollback 대상이 아니므로 필요한 설정 버전을 `apply`로 다시 지정합니다. SSM의 parameter 최신값 자체를 되돌리지는 않습니다. 잘못된 버전을 수정하려면 원본에서 새 버전을 만들고 그 번호를 적용합니다.

기존 blue/green 두 슬롯을 재사용하므로 설정 배포도 직전 릴리스 슬롯을 갱신합니다. 여러 단계 전의 코드 rollback 이력을 따로 보존하지 않습니다. 오래된 설정을 다시 적용할 때는 현재 코드와의 호환성을 확인하고 SSM 버전을 지정합니다.

OpenAI·LangSmith 키를 바꿀 때 이전 키를 제공자에서 즉시 폐기하면 설정 파일을 복구해도 그 키의 유효성이 돌아오지 않습니다. 전환·복구 확인과 키 폐기 순서를 함께 관리합니다. `/ready`는 실제 모델·계측 호출 없이 로컬 client 준비만 검사합니다.

snapshot에는 전체 비밀값이 있으므로 root 전용 경로에 보존합니다. `config-*.json`은 현재 백업 archive 대상이 아니고 미완료 작업은 백업을 차단합니다. 정상 적용 후의 호스트 복원·활성/이전 버전별 OpenAI·LangSmith 키 재주입은 [운영 백업](production-backups.md)을 따릅니다. 백업 보존 기간 동안 필요한 SSM 버전과 기존 키의 복구 가능성을 별도로 유지해야 합니다.

## 검증

소스·실행기·workflow의 합성 검사는 실제 운영값이나 모델 API를 사용하지 않습니다.

```bash
python3.13 -m unittest discover -s deploy/tests -p 'test_ssm_config.py' -v
python3.13 -m unittest discover -s deploy/tests -p 'test_config_release.py' -v
python3.13 -m unittest discover -s deploy/tests -p 'test_config_cd.py' -v
```

검사 범위는 고정 버전·중복 키/누락/잘못된 값 거부, 같은 코드의 설정 교체, 실패 후 runtime 입력 복구, 중단 상태 재실행, 잠금·경쟁 차단, 운영 비밀값 없는 출력입니다. 실제 EC2에서의 SSM/KMS 읽기, 권한 거부, 정상 설정 적용과 실패 복구는 지정된 운영 환경에서 별도로 확인하고 비공개 운영 기록에 명령 ID·코드 SHA·설정 버전·결과를 남깁니다.

실제 앱 이미지와 Compose의 설정 적용·rollback·잘못된 설정의 시작 실패 복구·전환 직후 중단 복구는 선택 검사로 실행합니다. 운영 호스트와 분리된 root 환경에 로컬 Docker/Compose, Python 3.13, GNU coreutils, util-linux, e2fsprogs, OpenSSL, curl을 준비합니다. 기존 [컨테이너 검사](../../deploy/tests/container_e2e.py)와 같은 합성 loopback mount 권한이 필요합니다.

```bash
python3.13 deploy/tests/config_container_e2e.py
```

SSM 응답만 합성하며 AWS·모델 API는 호출하지 않습니다. 설정을 바꿔도 이미지·코드 SHA와 DB·Nginx 컨테이너가 유지되는지 확인합니다. 검사 결과와 실행 소스 해시는 `deploy/test-results/config-container-e2e.json`에 기록하고 합성 앱·디스크는 종료 시 정리합니다. 이 검사는 일반 CI에 자동 추가되지 않습니다.
