# 운영 자동 배포

작업 브랜치의 PR은 `develop`에 통합하고, 배포할 때 `develop → main` 릴리스 PR을 병합합니다. `develop`과 PR에서는 CI만 실행합니다. E2E는 같은 저장소의 릴리스 PR에서만 수행하고 `develop`·`main` push에서는 생략합니다. 운영 CD는 **main push의 동일 커밋**에 대한 `Frontend`, `Backend`, `Validate docs`가 성공한 뒤 실행합니다. 브랜치·병합 방식은 [팀 작업 흐름](workflow.md)이 원본입니다.

## 실행 흐름

```mermaid
flowchart LR
    A[작업 브랜치] -->|PR · squash| B[develop · CI]
    B -->|릴리스 PR · merge commit| C[main · CI]
    C --> D[OIDC 임시 AWS 권한]
    D --> E[ECR 이미지와 소스 저장]
    E --> S[SSM 설정 버전 선택·고정]
    S --> F[백업 · API 교체 · HTTPS 확인]
    F --> G[S3 웹 게시 · CloudFront 갱신]
    G --> H[공개 도메인 확인]
```

[Application CI](../../.github/workflows/ci.yml)가 [재사용 CD 워크플로](../../.github/workflows/cd.yml)를 호출합니다. [CD 조합기](../../deploy/cd.py)는 최신 main 여부를 빌드 전과 운영 변경 직전에 다시 확인합니다. 새 main에 밀린 실행은 배포하지 않습니다. 운영 작업은 `production-deploy` concurrency로 직렬화하고 실행 중인 배포를 새 커밋 때문에 취소하지 않습니다.

백엔드 이미지는 커밋 전체 SHA 태그로 발행하고 실제 배포는 ECR digest를 고정합니다. 소스는 `git archive`로 만들며 해시를 대조합니다. 인증 정보·개발 환경 파일·DB 덤프는 이 아카이브에 들어가지 않습니다.

[호스트 실행기](../../deploy/cd_release.py)는 현재 릴리스가 예상 SHA와 일치하는지 배포 잠금 안에서 검사합니다. 새 코드 SHA를 배포할 때는 고정된 SSM parameter를 한 번 조회해 응답의 값과 버전을 함께 선택합니다. 그 설정을 검증하고 기존 코드·설정의 운영 백업을 완료한 뒤, [교체 엔진](container-deployment.md)으로 새 이미지와 선택한 설정을 한 번에 적용합니다. PostgreSQL 컨테이너·볼륨·데이터를 교체하거나 개발 시드를 재실행하지 않습니다.

설정 원본은 [SSM 설정 관리](ssm-configuration.md)의 전체 SecureString JSON입니다. **SSM에 새 버전을 저장한 뒤 `develop → main`을 병합하면 코드와 설정이 같은 blue-green 교체에 들어갑니다.** 선택 시점은 Git 병합 시점이 아니라 호스트 코드 배포가 SSM을 조회하는 시점입니다. 조회 이후 SSM에 더 새 버전이 생겨도 진행 중인 배포에는 섞이지 않습니다. 조회·복호화·형식 검증 실패를 기존 설정이나 다른 버전으로 대체하지 않습니다.

코드 배포도 설정 전용 배포의 허용 변경 범위를 따릅니다. DB·인증 비밀·네트워크·공유 파일 변경은 별도 운영 절차로 처리합니다. 현재 runtime 설정과 활성 슬롯의 일치를 먼저 확인하며, 미완료 작업이나 적용본 불일치가 있으면 새 변경을 시작하지 않습니다. 코드 변경 없이 설정만 바꾸려면 기존 `Production configuration` workflow에서 정확한 버전을 지정합니다.

[프런트 게시기](../../deploy/cd_frontend.py)는 불변 assets를 먼저 올리고 HTML을 마지막에 게시합니다. 기존 assets는 유지하며, 변경할 일반 파일은 복구용 스냅샷을 확보합니다. CloudFront 무효화 완료 후 실제 HTTPS 응답의 HTML 해시와 탐색 경로를 확인합니다.

## 실패와 복구

- API 교체 실패는 기존 엔진의 검증·복구·롤백 경계를 따릅니다. 코드와 설정의 이전·후보 snapshot을 보관하고, 복구 완료 시 슬롯·runtime 입력·현재 소스 링크가 같은 이전 조합인지 확인합니다. 모호한 상태는 강제로 덮어쓰지 않고 실패로 남깁니다.
- 웹 게시 실패 시 이전 파일·메타데이터를 복원하고 CloudFront 및 실제 응답을 확인합니다. 프런트 복원이 확인되면 API도 직전 SHA와 그때의 설정으로 복귀합니다. 롤백·중단 복구에서는 SSM 최신값을 다시 읽지 않습니다.
- 프런트 복원까지 실패하면 새 API를 임의로 되돌리지 않고 관리자 확인이 필요한 실패를 남깁니다.
- 웹 복구 스냅샷과 영수증은 실패 시 비공개 artifact bucket의 `artifacts/cd/<SHA>/recovery/<run-id>-<attempt>.tar.gz`에 보존합니다. 증거 업로드 실패도 로컬 자료를 삭제하거나 원래 복구 시도를 중단하지 않습니다. S3 versioning의 이전 버전도 유지합니다.
- 수동 취소·runner 중단·SSM 응답 유실은 성공으로 간주하지 않습니다. 명령 ID와 호스트 `status`를 확인한 뒤 재실행합니다.
- **DB migration은 이전 앱과 호환되는 변경이어야 합니다.** 앱 롤백은 DB downgrade가 아닙니다. 호환되지 않는 스키마 변경은 백업·복구 및 별도 배포 계획이 필요합니다.

동일 SHA 재실행은 실제 이미지와 소스를 다시 확인합니다. 이미지·자료가 다르거나 호스트 journal에 미완료 작업이 있으면 중단합니다. main push의 앱·배포 정적 검사를 다시 실행하려면 main의 `Application CI`를 재실행합니다. 이 실행에서는 E2E를 수행하지 않습니다. 현재 main이 바뀐 과거 실행은 자동 배포하지 않습니다.

동일 SHA의 코드 CD 재실행은 SSM을 다시 조회하거나 새 설정을 적용하지 않습니다. 설정만 바꾸려면 `Production configuration`에서 버전을 지정합니다. 두 workflow는 같은 `production-deploy` concurrency와 호스트 잠금을 사용합니다.

코드·설정 전환 중에는 `runtime_dir/state/code-config-pending.json`과 root 전용 `private/config-<digest>.json` snapshot을 보관합니다. runtime JSON·현재 소스 링크·활성 슬롯의 변경을 한 파일 작업으로 끝낼 수 없으므로, 각 단계에서 중단돼도 저장한 이전·후보 조합을 검증해 복구합니다. 이 기록이 남으면 새 코드 배포·설정 전용 변경·일반 release·백업을 시작하지 않습니다.

호스트의 관리자 세션에서 다음 명령으로 중단된 코드·설정 전환을 복구합니다. SSM을 다시 조회하지 않으며 저장한 snapshot만 사용합니다. 현재 소스 링크가 복구 명령을 지원하지 않는 이전 버전을 가리키면, 해당 배포에서 이미 검증한 후보 checkout의 실행기를 사용합니다.

```bash
sudo python3.13 /opt/sku-dreamon/current/deploy/cd_release.py \
  --config /etc/sku-dreamon/cd.json --action recover
```

복구 후 이전 코드·설정으로 안정화됐는지 확인하고 새 배포를 시작합니다. 실패 복구가 끝나 pending 기록을 지운 뒤의 새 시도는 수정된 SSM 최신 버전을 선택할 수 있습니다. DB migration은 자동 downgrade하지 않습니다. 복구에 필요한 파일이 없거나 적용본이 이전·후보 어느 쪽과도 맞지 않으면 기록을 지우지 않고 중단합니다.

## GitHub와 AWS 설정

저장소 변수 `PRODUCTION_CD_ENABLED=true`가 CD를 활성화합니다. `production` environment의 배포 허용 브랜치는 `main`만 설정합니다. 릴리스 시점의 승인은 main 대상 PR의 리뷰·필수 검사로 관리합니다.

| production 환경 변수 | 용도 |
| --- | --- |
| `AWS_REGION` | 배포 리전 |
| `AWS_ROLE_ARN` | GitHub OIDC 전용 배포 역할 |
| `ECR_REPOSITORY_URL` | API 이미지 저장소 |
| `ARTIFACT_BUCKET` | 암호화된 배포 소스 저장소 |
| `FRONTEND_BUCKET` | 비공개 웹 원본 저장소 |
| `CLOUDFRONT_DISTRIBUTION_ID` | 웹 배포 대상 |
| `DEPLOY_INSTANCE_ID` | SSM 관리 서버 |
| `DEPLOY_SSM_DOCUMENT` | 제한된 운영 배포 명령 문서 |
| `SITE_URL` | 정식 웹 HTTPS 주소 |
| `API_BASE_URL` | HTTPS API 기본 주소, `/api/v1` 포함 |

배포 역할의 trust는 해당 저장소의 `production` environment와 `sts.amazonaws.com` audience로 제한합니다. 권한은 지정한 ECR 저장소, S3 배포 경로·웹 원본, CloudFront distribution, 한 서버와 [전용 SSM 문서](../../deploy/ssm-production-release.json)로 제한합니다. GitHub에는 AWS 장기 액세스 키·DB 암호·AI 키를 등록하지 않습니다. 기존 서버의 instance role과 root 전용 런타임 설정을 사용합니다.

EC2에는 기존 설정 배포와 같은 root 0600 `/etc/sku-dreamon/ssm-config.json`과 지정 parameter 읽기·복호화 권한이 필요합니다. 새 코드 배포에서 이 원본이 없거나 조회에 실패하면 배포를 중단합니다. GitHub 배포 역할에 SecureString 값의 읽기 권한을 추가하지 않습니다.

처음 연결할 때 검증된 `deploy/cd_release.py`를 root 소유 `/opt/sku-dreamon/operations/cd_release.py`에 설치합니다. 이후 SSM은 현재 릴리스에 실행기가 있으면 그 파일을 사용하고, 없을 때만 최초 설치본을 사용합니다. SSM 문서 버전 1과 CLI 입력 계약은 함께 관리합니다. 명령 파라미터의 환경변수 보간을 지원하는 SSM Agent가 필요합니다.

**기존 운영 환경의 첫 전환에는 한 번의 bootstrap 릴리스가 필요합니다.** 구 실행기는 이 기능을 포함한 새 소스를 받아도 새 CD 실행기로 넘기지 않으므로, 기능을 처음 배포할 때는 기존 적용 설정을 사용합니다. 그 릴리스가 완료돼 새 실행기가 현재 소스가 된 다음 코드 배포부터 SSM 설정을 함께 적용합니다. 첫 전환 직후 설정을 적용하려면 기존 설정 전용 workflow를 사용합니다. 이 제한을 우회하려고 검증하지 않은 실행기를 교체하거나 배포 중 잠금을 넘기지 않습니다.

root 0600 `/etc/sku-dreamon/cd.json`에는 다음 메타데이터를 공급합니다. 실제 운영값은 공개 저장소에 넣지 않습니다.

```json
{
  "region": "example-region-1",
  "artifact_bucket": "example-private-artifacts",
  "ecr_repository_url": "123456789012.dkr.ecr.example-region-1.amazonaws.com/example/api",
  "runtime_config": "/etc/sku-dreamon/runtime.json",
  "releases_dir": "/opt/sku-dreamon/releases",
  "current_link": "/opt/sku-dreamon/current"
}
```

## 검증과 기록

`deploy/tests`는 이벤트·검사 gate, 호스트 소스 검증·경쟁·실패 복구, 프런트 부분 게시·복원과 변경 불가 assets를 검사합니다. 정적 검사는 실제 OIDC·SSM·ECR·CloudFront 실행 성공을 대신하지 않습니다. 최초 설정은 실제 main CI/CD 실행과 공개 도메인의 배포 SHA 확인까지 수행하고, 운영 식별자가 포함된 상세 기록은 비공개 작업 디렉터리에 둡니다.

GitHub의 `Production CD / Deploy production` job은 SSM 명령 ID와 최종 상태를 남깁니다. 기존 [운영 백업](production-backups.md)과 만료 감시는 CD와 독립적으로 계속 실행됩니다.
