"""소유한 격리 Docker 환경에서 동일 코드 설정 교체·실패 복구를 수동 검증한다.

root·로컬 Docker·합성 loopback mount가 필요하다. AWS와 모델 제공자는 호출하지
않으며 SSM 응답만 합성한다. 기존 운영 호스트에서 실행하지 않는다.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from container_e2e import BLUE_SHA, ROOT, CheckFailed, Harness

sys.path.insert(0, str(ROOT / "deploy"))

from cd_release import Config  # noqa: E402
from config import atomic_write  # noqa: E402
from config_release import ConfigError, ConfigRelease  # noqa: E402

PARAMETER = "/synthetic/config-container/backend"
REGION = "ap-northeast-2"


class ConfigurationHarness(Harness):
    def build_images(self) -> None:
        self.phase = "build_production_images"
        self.images["product_blue"] = self.build(
            "product-blue", "backend/Dockerfile", ROOT, f"RELEASE_SHA={BLUE_SHA}"
        )
        self.images["nginx"] = self.build("nginx", "deploy/nginx/Dockerfile", ROOT)
        self.images["postgres"] = self.build(
            "postgres", "deploy/postgres/Dockerfile", ROOT
        )
        self.docker("pull", "certbot/certbot:v5.8.0", timeout=180)
        self.images["certbot"] = self.docker(
            "image", "inspect", "certbot/certbot:v5.8.0", "--format", "{{.Id}}"
        )
        self.mark("production_images_built_without_model_fixture")

    def initial_release(self) -> None:
        self.phase = "initial_production_release"
        self.values["app_env"]["AI_REQUESTS_PER_HOUR"] = "20"
        self.write_config()
        self.release(
            "deploy",
            "--image",
            self.images["product_blue"],
            "--sha",
            BLUE_SHA,
            "--migrate",
            timeout=300,
        )
        self.pg_id = self.container("postgres")["Id"]
        self.nginx_id = self.container("nginx")["Id"]
        self.docker(
            "exec",
            self.pg_id,
            "psql",
            "-U",
            "postgres",
            "-d",
            "dep03_e2e",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            "CREATE TABLE public.config_fixture(value text); "
            "INSERT INTO public.config_fixture VALUES ('synthetic-preserved');",
        )
        self.mark("initial_production_image_migration_tls_and_https")

    def setup_configuration(self) -> None:
        self.phase = "prepare_configuration_runner"
        releases = self.temporary / "releases"
        checkout = releases / BLUE_SHA
        checkout.mkdir(parents=True)
        shutil.copytree(
            ROOT / "deploy",
            checkout / "deploy",
            ignore=shutil.ignore_patterns("tests", "test-results", "__pycache__"),
        )
        current = self.temporary / "current"
        current.symlink_to(checkout)
        source = self.temporary / "ssm-config.json"
        atomic_write(
            source, json.dumps({"region": REGION, "parameter_name": PARAMETER})
        )
        cd_path = self.temporary / "cd.json"
        atomic_write(
            cd_path,
            json.dumps(
                {
                    "region": REGION,
                    "artifact_bucket": "synthetic-artifacts",
                    "ecr_repository_url": (
                        "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/synthetic-app"
                    ),
                    "runtime_config": str(self.config),
                    "releases_dir": str(releases),
                    "current_link": str(current),
                }
            ),
        )
        self.snapshots = {
            1: {**self.values["app_env"], "AI_REQUESTS_PER_HOUR": "21"},
            2: {
                **self.values["app_env"],
                "AI_REASONING_EFFORT": "invalid-synthetic-value",
            },
        }
        self.source_calls: list[int] = []

        def synthetic_ssm(arguments: list[str], *, timeout: int = 60) -> bytes:
            # 이 callable에는 SSM get-parameter 외 외부 명령을 허용하지 않는다.
            if arguments[:4] != ["aws", "ssm", "get-parameter", "--name"]:
                raise CheckFailed("unexpected synthetic AWS operation")
            name, version_text = arguments[4].rsplit(":", 1)
            version = int(version_text)
            assert name == PARAMETER and version in self.snapshots and timeout == 60
            assert "--with-decryption" in arguments
            self.source_calls.append(version)
            return json.dumps(
                {
                    "Parameter": {
                        "Name": PARAMETER,
                        "Type": "SecureString",
                        "Value": json.dumps(self.snapshots[version]),
                        "Version": version,
                        "Selector": f":{version}",
                        "DataType": "text",
                        "ARN": (
                            f"arn:aws:ssm:{REGION}:123456789012:parameter{PARAMETER}"
                        ),
                    }
                }
            ).encode()

        self.operation_runner = ConfigRelease(
            Config.read(cd_path), source, runner=synthetic_ssm
        )
        self.original_runtime = json.loads(self.config.read_text())
        self.original_status = self.operation_runner.status()

    def change(self, action: str, version: int = 0) -> dict[str, Any]:
        before = self.operation_runner.status()
        return self.operation_runner.change(
            action,
            before["active_sha"],
            before["active_env_hash"],
            before["active_config_revision"],
            version,
        )

    def observe(self, requests_per_hour: str) -> tuple[str, str]:
        status = self.operation_runner.status()
        assert status["phase"] == "stable" and status["config_phase"] == "idle"
        assert status["active_sha"] == BLUE_SHA
        journal = json.loads((self.runtime / "state/release.json").read_text())
        slot = journal["active"]
        actual = self.container(slot)
        values = dict(item.split("=", 1) for item in actual["Config"]["Env"])
        assert values["AI_REQUESTS_PER_HOUR"] == requests_per_hour
        assert actual["Image"] == self.images["product_blue"]
        assert actual["State"]["Running"]
        code, headers, _ = self.http("/api/v1/health")
        assert code == 200 and headers["x-release-id"] == BLUE_SHA
        assert headers["x-release-slot"] == slot
        assert self.container("postgres")["Id"] == self.pg_id
        assert self.container("nginx")["Id"] == self.nginx_id
        assert "synthetic-preserved" in self.docker(
            "exec",
            self.pg_id,
            "psql",
            "-U",
            "postgres",
            "-d",
            "dep03_e2e",
            "-Atc",
            "SELECT value FROM public.config_fixture",
        )
        return slot, actual["Id"]

    def configuration_checks(self) -> None:
        self.phase = "same_code_configuration_apply"
        old_slot, old_container = self.observe("20")
        applied = self.change("apply", 1)
        slot, container = self.observe("21")
        assert applied["operation_status"] == "applied"
        assert slot != old_slot and container != old_container
        assert json.loads(self.config.read_text())["app_env"] == self.snapshots[1]
        self.mark("same_image_and_sha_new_setting_applied_with_db_and_nginx_preserved")

        self.phase = "same_version_idempotence"
        assert self.change("apply", 1)["operation_status"] == "unchanged"
        assert self.observe("21") == (slot, container)
        self.mark("repeated_exact_version_does_not_replace_container")

        self.phase = "manual_configuration_rollback"
        reads = list(self.source_calls)
        assert self.change("rollback")["operation_status"] == "rolled_back"
        self.observe("20")
        assert json.loads(self.config.read_text()) == self.original_runtime
        assert self.source_calls == reads
        self.mark("rollback_restores_prior_runtime_and_environment_without_ssm")

        self.phase = "invalid_candidate_setting_restoration"
        try:
            self.change("apply", 2)
        except ConfigError as error:
            assert str(error) == "configuration_failed_restored"
        else:
            raise CheckFailed("invalid setting unexpectedly applied")
        self.observe("20")
        assert json.loads(self.config.read_text()) == self.original_runtime
        current = self.operation_runner.status()
        assert current["active_env_hash"] == self.original_status["active_env_hash"]
        assert (
            current["active_config_revision"]
            == self.original_status["active_config_revision"]
        )
        assert not (self.runtime / "state/config-pending.json").exists()
        self.mark(
            "invalid_app_setting_fails_readiness_and_restores_previous_configuration"
        )

        self.phase = "post_commit_interruption_recovery"
        # 앱 전환을 실제로 끝낸 직후 runtime 게시 직전 프로세스 중단을 모사한다.
        publish = self.operation_runner.publish

        def interrupt(value, allowed):
            raise KeyboardInterrupt

        self.operation_runner.publish = interrupt
        try:
            self.change("apply", 1)
        except KeyboardInterrupt:
            pass
        else:
            raise CheckFailed("synthetic interruption did not occur")
        finally:
            self.operation_runner.publish = publish
        assert self.operation_runner.status()["config_phase"] == "pending"
        reads = list(self.source_calls)
        assert self.change("recover")["operation_status"] == "recovered"
        self.observe("20")
        assert json.loads(self.config.read_text()) == self.original_runtime
        assert self.source_calls == reads
        self.mark("interrupted_commit_recovers_prior_container_and_runtime_without_ssm")


def main() -> int:
    if os.geteuid() != 0:
        print(
            "Configuration container E2E requires an isolated root Docker host.",
            file=sys.stderr,
        )
        return 1
    report = ROOT / "deploy/test-results/config-container-e2e.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="config-container-") as temporary:
        harness = ConfigurationHarness(Path(temporary))
        success = False
        failure = None
        try:
            harness.observations.update(
                {
                    "docker_version": harness.docker(
                        "info", "--format", "{{.ServerVersion}}"
                    ),
                    "compose_version": harness.docker("compose", "version", "--short"),
                    "python_version": sys.version.split()[0],
                    "source_hashes": {
                        name: hashlib.sha256(
                            (ROOT / "deploy" / name).read_bytes()
                        ).hexdigest()
                        for name in (
                            "config.py",
                            "release.py",
                            "cd_release.py",
                            "config_release.py",
                            "ssm_config.py",
                            "tests/config_container_e2e.py",
                        )
                    },
                }
            )
            harness.build_images()
            harness.observations["image_ids"] = dict(harness.images)
            harness.prepare_runtime()
            harness.bootstrap()
            harness.initial_release()
            harness.setup_configuration()
            harness.configuration_checks()
            success = True
        except Exception as error:  # noqa: BLE001 -- 합성 설정도 오류 원문에 출력하지 않는다.
            failure = type(error).__name__
            print(f"FAIL {harness.phase}: {harness.operation} ({failure})", flush=True)
        finally:
            diagnostics = harness.safe_diagnostics()
            phase = harness.phase
            harness.cleanup()
            report.write_text(
                json.dumps(
                    {
                        "success": success,
                        "checks": harness.checks,
                        "failure_category": failure,
                        "phase": phase,
                        "state": diagnostics,
                        "observations": harness.observations,
                        "elapsed_seconds": round(time.monotonic() - started, 2),
                    },
                    indent=2,
                )
                + "\n"
            )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
