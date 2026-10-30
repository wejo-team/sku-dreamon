# 운영 PostgreSQL·런타임 백업

[배포 계획](../development-plans/deployment-foundation.md#poc-mvp-recovery)의 실제 데이터 MVP를 위한 최소 백업 실행 경로입니다. [백업 명령](../../deploy/backup.py)은 PostgreSQL custom dump와 복구 설정 archive를 기존 비공개 S3 버킷에 따로 업로드합니다. 이 문서는 명령·단위 검증을 설명하며, 실제 AWS 업로드·최초 복원·알림 수신의 성공 기록을 대신하지 않습니다.

## 보관 내용과 완료 판정

각 실행은 `backups/<project>/<UTC시각-임의ID>/` 아래에 새 객체를 만듭니다.

| 객체 | 내용 |
| --- | --- |
| `database.dump` | 실행 중 DB의 일관된 custom-format `pg_dump`. 역할 생성·운영 파일은 포함하지 않음 |
| `runtime.tar.gz` | 아래 허용한 DB·CSRF 비밀값, TLS·ACME 상태와 배포 journal. OpenAI 키는 제외 |
| `manifest.json` | 두 객체의 경로·크기·SHA-256, 시작/완료 시각, 활성 release SHA. 두 객체의 업로드·HEAD 검증 뒤 마지막에 게시 |

업로드는 AWS CLI의 HTTPS·SHA-256 전송 checksum과 명시적인 `--sse aws:kms`를 사용합니다. 객체 크기·사용자 metadata SHA-256·SSE-KMS 응답을 다시 확인합니다. metadata 비교는 원격 파일 전체를 내려받아 hash를 재계산한 검사가 아니며, 첫 복원에서는 다운로드한 파일 자체의 SHA-256도 manifest와 대조해야 합니다. AWS 관리형 S3 KMS 키를 기본으로 사용하며 지정한 customer-managed key도 지원합니다. [AWS CLI cp](https://docs.aws.amazon.com/cli/latest/reference/s3/cp.html), [SSE-KMS와 권한](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html)

manifest까지 검증한 경우에만 `runtime_dir/state/backup-last-success.json`을 원자적으로 교체합니다. dump·archive·업로드·검증 실패는 nonzero 종료이며 새 성공 표식을 기록하지 않습니다. 실패한 실행의 부분 S3 객체는 그대로 남으며, 기존 성공 표식을 실패 시각으로 바꾸지 않습니다. manifest의 `restored:false`는 업로드와 복원 검증을 구분합니다.

S3 객체·버전·사용자 데이터 삭제, lifecycle 설정, 보존 기간 만료는 구현하지 않습니다. 운영 정책 확정 전 자동 삭제를 추가하지 않으며, 이 스크립트는 변경 불가능한 보관 기간을 강제하지 않습니다. 실제 RPO는 마지막 성공 dump 시점과 수행 주기·실패에 따라 달라지며 일 1회 timer가 하루치 손실 한도를 보장하지 않습니다.

## 실행 경계

root로 실행하고 [컨테이너 운영](container-deployment.md)의 root 전용 runtime JSON을 읽습니다. `release.py`와 같은 `state/release.lock`을 비차단 독점 잠금으로 사용하고, journal이 `stable`이며 진행 중 전환·인증서 작업이 없을 때만 실행합니다. dump부터 원격 업로드와 완료 표식까지 잠금을 유지하므로 그동안 새 배포는 시작할 수 없습니다. 일반 앱 트래픽과 DB 쓰기는 계속 가능합니다.

[SSM 설정 재배포](ssm-configuration.md)의 `state/config-pending.json`이 남아 있으면 백업을 거부합니다. 컨테이너와 runtime 입력의 서로 다른 설정을 정상 백업으로 기록하지 않도록 먼저 설정 `recover`를 완료합니다.

Compose project·service label이 맞는 실행 중 PostgreSQL 컨테이너가 정확히 하나여야 합니다. journal의 컨테이너 ID, `PGDATA`, 실제 writable bind source를 대조하고 기존 UUID·mountpoint·실제 장치 검사를 수행합니다. capture 후 같은 대상을 다시 확인합니다. 임의 DB URL·다른 컨테이너·다른 mount로 fallback하지 않습니다.

현재 Debian 기반 PostgreSQL 이미지의 `timeout`으로 컨테이너 안의 dump도 최대 29분 뒤 종료 요청하고 추가 30초 뒤 강제 정리합니다. DB 잠금 대기는 30초로 제한하며 시간 초과는 실패입니다. Docker 클라이언트만 종료되고 dump가 무제한 남는 경로를 피합니다.

런타임 archive는 다음 항목만 읽습니다.

- 명시한 root 전용 `runtime.json` → archive의 `configuration/runtime.json`.
- `runtime_dir/private`의 DB CA·CA 키·서버 인증서/키·DB 관리자/앱/migration 비밀번호·차단 목록·`compose.env`, 알려진 불변 env 파일. 선택적으로 차단 목록 출처 JSON과 라이선스.
- `runtime_dir/acme/letsencrypt` 전체. account·archive·live·renewal 등을 보존하고 내부 상대 symlink만 그대로 저장합니다. 외부/절대 symlink는 거부합니다.
- `runtime_dir/nginx`, `state/release.json`, `state/certbot`의 복구 상태.

PGDATA, 원시 로그, Certbot work/cache/webroot, 설정 작업의 `private/config-<digest>.json` snapshot, 미지의 private 파일, 열린 `.lock` 파일은 포함하지 않습니다. snapshot은 호스트의 중단 복구용이며 전체 비밀값을 포함합니다. 디렉터리 밖 symlink를 따라 읽거나 원시 장치를 archive하지 않습니다. capture 동안 파일 크기·변경 시각 변화가 보이면 실패합니다. 생성한 임시 dump·archive는 root 전용 `runtime_dir/backup-staging`에 두고 정상 종료·처리한 실패 시 제거합니다. 호스트 전원 장애·SIGKILL 뒤 잔여 임시 파일은 관리자가 별도 확인합니다.

`OPENAI_API_KEY`의 원본은 [SSM 설정 관리](ssm-configuration.md)를 연결한 이후에는 **앱 설정 전체가 담긴 SecureString JSON의 해당 버전**입니다. archive의 runtime JSON과 각 env 파일에서는 키 값만 `__REHYDRATE_OPENAI_API_KEY_FROM_SSM__`으로 바꾸며, 원본 런타임 파일은 수정하지 않습니다. DB 비밀번호·CSRF·CA 키는 복구에 필요하므로 암호화 archive에 보존합니다. manifest의 `openai_key_redacted`로 모델 키 제외 여부를 확인합니다. parameter 경로·설정 버전·복구 역할의 읽기/KMS 권한은 비공개 운영 기록에서 관리합니다. 연결 전 백업은 기존 개별 OpenAI key parameter의 경로·버전 기록을 유지합니다.

## 호스트 설치

Python 3.13+, Docker, AWS CLI v2가 필요합니다. EC2 instance role에는 정해진 `backups/` prefix의 `s3:PutObject`·`s3:GetObject`와 KMS 사용 권한이 필요합니다. multipart에는 `kms:GenerateDataKey`·`kms:Decrypt`가 필요하며, 운영 bucket의 public access 차단·TLS 강제·versioning은 기반 설정에서 확인합니다. SNS를 사용하면 지정 topic에만 `sns:Publish`를 추가합니다. 정적 access key를 넣지 않습니다.

관리자가 `/etc/sku-dreamon/backup.env`를 root 0600으로 준비합니다. 아래 값은 가상 예시입니다.

```dotenv
BACKUP_BUCKET=example-private-operations-bucket
BACKUP_REGION=ap-northeast-2
# 선택: 같은 리전의 실제 운영 알림 topic. 수신자의 구독 확인은 별도입니다.
BACKUP_SNS_TOPIC_ARN=arn:aws:sns:ap-northeast-2:123456789012:example-operations
# 선택: customer-managed key를 쓰는 경우에만 설정합니다.
# BACKUP_KMS_KEY_ID=arn:aws:kms:ap-northeast-2:123456789012:key/00000000-0000-0000-0000-000000000000
```

`/opt/sku-dreamon/current`는 검증한 배포 소스를 가리키도록 운영자가 관리합니다. 다음 명령은 해당 checkout에서 실행합니다.

```bash
sudo install -o root -g root -m 0644 deploy/systemd/sku-dreamon-backup.service /etc/systemd/system/
sudo install -o root -g root -m 0644 deploy/systemd/sku-dreamon-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start sku-dreamon-backup.service
sudo systemctl status sku-dreamon-backup.service
# 최초 실제 업로드와 격리 복원을 확인한 뒤 정기 실행을 켭니다.
sudo systemctl enable --now sku-dreamon-backup.timer
sudo systemctl list-timers sku-dreamon-backup.timer
```

timer는 매일 UTC 18:15, 한국시간 다음 날 03:15부터 최대 15분 분산 실행합니다. `Persistent=true`로 정지 중 놓친 실행을 다음 기동 때 보완합니다. root 전용 환경을 이미 주입한 수동 실행은 `sudo python3.13 deploy/backup.py --config /etc/sku-dreamon/runtime.json`입니다. 환경 파일을 shell로 `source`할 필요가 없습니다.

실패 알림은 event·고정 실패 코드·UTC 시각만 보냅니다. stderr·SQL·키·런타임 JSON·컨테이너 inspect 원문은 로그나 SNS에 출력하지 않습니다. topic 미설정·미확인 구독·알림 자체 실패는 수신을 보장하지 않습니다. 서비스가 아예 실행되지 않거나 호스트가 내려간 경우의 **백업 장기 누락 감시**는 외부 감시에서 추가해야 합니다.

## 최초 복원 확인

실제 사용자 레코드를 만들기 전에 migration이 끝난 빈 운영 DB에서 첫 백업을 만들고, 별도 격리 PostgreSQL에서 복원합니다. 가짜 사용자·공고·시연 seed를 운영에 넣지 않습니다.

1. manifest와 두 객체를 접근 제한 경로에 내려받고 SHA-256·크기를 대조합니다. runtime archive에는 실제 비밀값이 있으므로 공개 artifact·일반 개발 환경에 풀지 않습니다.
2. 앱·release 검증 전에 `runtime.json`과 journal의 각 슬롯 `config_revision`에 대응하는 **SSM bundle의 정확한 버전**에서 OpenAI 키를 읽어 해당 JSON·raw env에만 비공개로 채웁니다. 활성·이전 슬롯이 서로 다른 키 버전을 사용할 수 있으므로 최신 키 하나로 모든 파일을 채우지 않습니다. 연결 전 설정 revision은 기존 개별 parameter 기록을 사용합니다. 키를 stdout·명령 인자·로그에 남기지 않습니다. journal의 env hash와 파일명은 원래 키를 포함한 원본 env에 대응하므로 **각 파일의 동일한 키를 복구해야** 일치합니다. 필요한 버전·키를 구할 수 없거나 제공자에서 폐기했다면 journal을 조작하지 말고 별도의 설정 revision·키 회전 절차로 재구성합니다. sentinel을 실제 API 키로 사용하거나 그 상태를 운영 준비 완료로 판단하지 않습니다.
3. 별도 DB/컨테이너에서 `dreamon_migration`·`dreamon_app` 역할과 필요한 TLS·소유권을 준비합니다. 역할은 dump에 없으므로 [초기 역할 설정](../../deploy/postgres/init-roles.sh)과 비공개 비밀번호의 복구 경로를 사용합니다.
4. 격리 DB에 `pg_restore --exit-on-error`를 실행하고 Alembic revision·테이블·역할/권한·기본 조회를 확인합니다. 운영 데이터 경로나 운영 DB를 복원 대상으로 쓰지 않습니다. `--create`는 archive의 DB 이름을 사용하므로 대상 DB 지정만으로 격리를 보장하지 않습니다. DB만 복원하는 시험에는 실제 모델 키·호출이 필요하지 않습니다.
5. 시험 대상·실행 시각·원본 backup ID·검증 결과를 접근 제한 운영 기록에 남깁니다. 실제 사용자 데이터가 생긴 이후의 복원 연습은 별도 개인정보 접근/보존 경계로 수행합니다.

루트 EBS의 `DeleteOnTermination=false`와 암호화는 계속 확인하지만 S3 백업·격리 복원을 대신하지 않습니다. [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html), [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html)

## 로컬 검증

```bash
python3.13 -m unittest discover -s deploy/tests -p 'test_backup.py' -v
```

임시 합성 파일과 가짜 Docker/AWS 명령 경계로 잘못된 컨테이너·mount, 전환 중 capture, 외부 symlink, dump/업로드 실패와 성공 표식, archive 범위, 비밀값 없는 실패 출력을 검사합니다. 실제 S3·SNS 호출·DB dump·복원은 수행하지 않습니다.
