# 운영 자동 배포

작업 브랜치의 PR은 `develop`에 통합하고, 배포할 때 `develop → main` 릴리스 PR을 병합합니다. `develop`과 PR에서는 CI만 실행합니다. 운영 CD는 **main push의 동일 커밋**에 대한 `Frontend`, `Backend`, `Validate docs`가 성공한 뒤 실행합니다. 브랜치·병합 방식은 [팀 작업 흐름](workflow.md)이 원본입니다.

## 실행 흐름

```mermaid
flowchart LR
    A[작업 브랜치] -->|PR · squash| B[develop · CI]
    B -->|릴리스 PR · merge commit| C[main · CI]
    C --> D[OIDC 임시 AWS 권한]
    D --> E[ECR 이미지와 소스 저장]
    E --> F[백업 · API 교체 · HTTPS 확인]
    F --> G[S3 웹 게시 · CloudFront 갱신]
    G --> H[공개 도메인 확인]
```

[Application CI](../../.github/workflows/ci.yml)가 [재사용 CD 워크플로](../../.github/workflows/cd.yml)를 호출합니다. [CD 조합기](../../deploy/cd.py)는 최신 main 여부를 빌드 전과 운영 변경 직전에 다시 확인합니다. 새 main에 밀린 실행은 배포하지 않습니다. 운영 작업은 `production-deploy` concurrency로 직렬화하고 실행 중인 배포를 새 커밋 때문에 취소하지 않습니다.

백엔드 이미지는 커밋 전체 SHA 태그로 발행하고 실제 배포는 ECR digest를 고정합니다. 소스는 `git archive`로 만들며 해시를 대조합니다. 인증 정보·개발 환경 파일·DB 덤프는 이 아카이브에 들어가지 않습니다.

[호스트 실행기](../../deploy/cd_release.py)는 현재 릴리스가 예상 SHA와 일치하는지 배포 잠금 안에서 검사합니다. 운영 백업 성공 후 기존 [교체 엔진](container-deployment.md)을 사용합니다. PostgreSQL 컨테이너·볼륨·데이터와 런타임 비밀값을 교체하거나 개발 시드를 재실행하지 않습니다.

코드 변경 없이 백엔드 설정만 바꾸려면 [SSM 설정 관리와 재배포](ssm-configuration.md)의 별도 workflow를 사용합니다. 코드 CD는 마지막으로 적용이 완료된 runtime 설정과 활성 슬롯의 일치를 검사하며, SSM 최신값을 자동으로 가져오지 않습니다. 설정 작업의 중단 기록이나 적용본 불일치가 있으면 코드 CD도 거부하고 먼저 설정 복구를 요구합니다.

[프런트 게시기](../../deploy/cd_frontend.py)는 불변 assets를 먼저 올리고 HTML을 마지막에 게시합니다. 기존 assets는 유지하며, 변경할 일반 파일은 복구용 스냅샷을 확보합니다. CloudFront 무효화 완료 후 실제 HTTPS 응답의 HTML 해시와 탐색 경로를 확인합니다.

## 실패와 복구

- API 교체 실패는 기존 엔진의 검증·복구·롤백 경계를 따릅니다. 모호한 상태는 강제로 덮어쓰지 않고 실패로 남깁니다.
- 웹 게시 실패 시 이전 파일·메타데이터를 복원하고 CloudFront 및 실제 응답을 확인합니다. 프런트 복원이 확인되면 API도 직전 SHA로 복귀합니다.
- 프런트 복원까지 실패하면 새 API를 임의로 되돌리지 않고 관리자 확인이 필요한 실패를 남깁니다.
- 웹 복구 스냅샷과 영수증은 실패 시 비공개 artifact bucket의 `artifacts/cd/<SHA>/recovery/<run-id>-<attempt>.tar.gz`에 보존합니다. 증거 업로드 실패도 로컬 자료를 삭제하거나 원래 복구 시도를 중단하지 않습니다. S3 versioning의 이전 버전도 유지합니다.
- 수동 취소·runner 중단·SSM 응답 유실은 성공으로 간주하지 않습니다. 명령 ID와 호스트 `status`를 확인한 뒤 재실행합니다.
- **DB migration은 이전 앱과 호환되는 변경이어야 합니다.** 앱 롤백은 DB downgrade가 아닙니다. 호환되지 않는 스키마 변경은 백업·복구 및 별도 배포 계획이 필요합니다.

동일 SHA 재실행은 실제 이미지와 소스를 다시 확인합니다. 이미지·자료가 다르거나 호스트 journal에 미완료 작업이 있으면 중단합니다. 모든 CI 검사를 다시 실행하려면 main의 `Application CI`를 재실행합니다. 현재 main이 바뀐 과거 실행은 자동 배포하지 않습니다.

동일 SHA의 코드 CD 재실행은 설정 재배포를 대신하지 않습니다. 설정 교체는 `Production configuration`에서 버전을 지정하며, 두 workflow는 같은 `production-deploy` concurrency와 호스트 잠금을 사용합니다.

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

처음 연결할 때 검증된 `deploy/cd_release.py`를 root 소유 `/opt/sku-dreamon/operations/cd_release.py`에 설치합니다. 이후 SSM은 현재 릴리스에 실행기가 있으면 그 파일을 사용하고, 없을 때만 최초 설치본을 사용합니다. SSM 문서 버전 1과 CLI 입력 계약은 함께 관리합니다. 명령 파라미터의 환경변수 보간을 지원하는 SSM Agent가 필요합니다.

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
