"""단일 호스트의 앱 교체를 기록하고 Nginx worker 종료 뒤 이전 앱을 정리한다."""

from __future__ import annotations

import argparse
import base64
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from config import IMAGE, SHA, ReleaseError, Runtime, atomic_write, environment

SLOTS = ("app_blue", "app_green")
WORKERS = r"""for p in /proc/[0-9]*; do
 if [ -r "$p/cmdline" ] && tr '\000' ' ' < "$p/cmdline" | grep -q '^nginx: worker process'; then
  awk '{print $1 ":" $22}' "$p/stat" || exit 1
 fi
done"""


def fingerprint(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        raise ReleaseError("runtime configuration is unavailable") from None


def execute(arguments: list[str], timeout: float = 60) -> str:
    """stderr와 인수를 오류에 포함하지 않아 런타임 비밀값을 숨긴다."""
    try:
        result = subprocess.run(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=True,
            env={
                key: os.environ[key]
                for key in ("PATH", "HOME", "LANG")
                if key in os.environ
            },
        )
    except (OSError, subprocess.SubprocessError):
        raise ReleaseError("bounded host operation failed") from None
    return result.stdout


class Release:
    def __init__(self, runtime: Runtime, checkout: Path) -> None:
        self.runtime = runtime
        self.checkout = checkout
        self.root = runtime.root
        self.journal = self.root / "state" / "release.json"
        self.active_config = self.root / "nginx" / "active.conf"
        self.state: dict[str, Any] = {
            "version": 1,
            "phase": "empty",
            "active": None,
            "previous": None,
            "slots": {},
            "transaction": None,
        }

    def load(self) -> None:
        if self.journal.exists():
            from config import private_path

            private_path(self.journal)
            try:
                self.state = json.loads(self.journal.read_text())
            except (OSError, ValueError):
                raise ReleaseError("release journal is invalid") from None
            if self.state.get("version") != 1:
                raise ReleaseError("unsupported release journal")

    @contextmanager
    def lock(self) -> Iterator[None]:
        state_dir = self.root / "state"
        state_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            state_dir / "release.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600
        )
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReleaseError(
                    "another release operation holds the host lock"
                ) from None
            self.load()
            yield
        finally:
            os.close(descriptor)

    def save(self) -> None:
        atomic_write(
            self.journal, json.dumps(self.state, sort_keys=True, indent=2) + "\n"
        )

    def docker(self, *arguments: str, timeout: float = 60) -> str:
        return execute(
            ["docker", "--host", "unix:///var/run/docker.sock", *arguments], timeout
        )

    def compose(
        self, *arguments: str, slot: str | None = None, timeout: float = 120
    ) -> str:
        profile = slot.removeprefix("app_") if slot else "tools"
        return self.docker(
            "compose",
            "--project-directory",
            str(self.checkout / "deploy"),
            "--env-file",
            str(self.root / "private" / "compose.env"),
            "--project-name",
            self.runtime.project,
            "-f",
            str(self.checkout / "deploy" / "compose.production.yaml"),
            "--profile",
            profile,
            *arguments,
            timeout=timeout,
        )

    def compose_environment(self) -> None:
        # 모든 슬롯은 각 릴리스의 불변 파일을 참조한다. 새 config로 구 앱을 재생성하지 않는다.
        slots = self.state["slots"]
        fallback = next(iter(slots.values()), None)
        if fallback is None:
            env_file = self.runtime.immutable_environment(
                self.runtime.app_env, "unassigned"
            )
            fallback = {
                "image": self.runtime.images["nginx"],
                "env_file": str(env_file),
                "budgets": asdict(self.runtime.budgets),
            }
        values = dict(self.runtime.compose)
        values.update(
            {
                "RUNTIME_DIR": str(self.root),
                "API_HOST": self.runtime.api_host,
                "POSTGRES_DATA_DIR": str(self.runtime.data_dir),
                "POSTGRES_FILESYSTEM_UUID": self.runtime.filesystem_uuid,
                "POSTGRES_IMAGE": self.runtime.images["postgres"],
                "NGINX_IMAGE": self.runtime.images["nginx"],
                "CERTBOT_IMAGE": self.runtime.images["certbot"],
                "POSTGRES_ENV_FILE": str(
                    self.runtime.immutable_environment(
                        self.runtime.postgres_env, "postgres"
                    )
                ),
                "MIGRATION_ENV_FILE": str(
                    self.runtime.immutable_environment(
                        self.runtime.migration_env, "migrate"
                    )
                ),
                "MIGRATION_IMAGE": slots.get(self.state.get("target"), fallback)[
                    "image"
                ],
            }
        )
        for slot in SLOTS:
            record = slots.get(slot, fallback)
            prefix = slot.upper()
            values[f"{prefix}_IMAGE"] = record["image"]
            values[f"{prefix}_ENV_FILE"] = record["env_file"]
            values[f"{prefix}_UVICORN_GRACE_SECONDS"] = str(
                record["budgets"]["uvicorn"]
            )
            values[f"{prefix}_STOP_GRACE_SECONDS"] = str(record["budgets"]["stop"])
        atomic_write(self.root / "private" / "compose.env", environment(values))

    def inspect(self, identity: str, kind: str = "container") -> dict[str, Any]:
        try:
            values = json.loads(self.docker("inspect", "--type", kind, identity))
            if len(values) != 1:
                raise ValueError
            return values[0]
        except (ValueError, TypeError, IndexError):
            raise ReleaseError("container identity is unavailable") from None

    def container(self, service: str) -> dict[str, Any] | None:
        identities = self.compose(
            "ps",
            "--all",
            "--quiet",
            service,
            slot=service if service in SLOTS else None,
        ).split()
        if not identities:
            return None
        if len(identities) != 1:
            raise ReleaseError("unexpected service replica count")
        return self.inspect(identities[0])

    def nginx_identity(self) -> dict[str, str]:
        container = self.container("nginx")
        if not container or not container["State"]["Running"]:
            raise ReleaseError("Nginx must be running")
        return {
            "id": container["Id"],
            "started": container["State"]["StartedAt"],
            "master": self.docker(
                "exec", container["Id"], "cat", "/proc/1/stat"
            ).split()[21],
        }

    def workers(self, expected: dict[str, str]) -> list[str]:
        if self.nginx_identity() != expected:
            raise ReleaseError("Nginx container or master changed during drain")
        return sorted(self.docker("exec", expected["id"], "sh", "-ec", WORKERS).split())

    def mount(self) -> None:
        execute(
            [
                "sh",
                str(self.checkout / "deploy" / "postgres" / "check-mount.sh"),
                str(self.runtime.mount_path),
                self.runtime.filesystem_uuid,
                str(self.runtime.data_dir),
            ],
            15,
        )

    def verify_slot(self, slot: str) -> dict[str, Any]:
        record = self.state["slots"][slot]
        container = self.container(slot)
        if (
            not container
            or not container["State"]["Running"]
            or container["Image"] != record["image_id"]
        ):
            raise ReleaseError("app image or running identity differs from the journal")
        if container["Config"]["Image"] != record["image"]:
            raise ReleaseError("app immutable image reference differs from the journal")
        expected = fingerprint(Path(record["env_file"]))
        if expected != record["env_hash"]:
            raise ReleaseError("immutable app configuration changed")
        for name, digest in record["asset_hashes"].items():
            if fingerprint(self.root / "private" / name) != digest:
                raise ReleaseError(
                    "shared app file changed outside a release procedure"
                )
        environment_values = dict(
            item.split("=", 1) for item in container["Config"]["Env"] if "=" in item
        )
        # 제품 timeout의 실제 입력까지 확인해야 설정 감소 후에도 구 슬롯 예산이 보존된다.
        for key, value in record["timeout_env"].items():
            if environment_values.get(key) != value:
                raise ReleaseError("actual app timeouts differ from the release record")
        settings = json.loads(
            self.docker(
                "exec",
                container["Id"],
                "python",
                "-c",
                "import json; from app.core.config import Settings; s=Settings(_env_file=None); "
                "print(json.dumps({'AI_TIMEOUT_SECONDS': s.ai_timeout_seconds, "
                "'AI_CLEANUP_TIMEOUT_SECONDS': s.ai_cleanup_timeout_seconds, "
                "'SHUTDOWN_TIMEOUT_SECONDS': s.shutdown_timeout_seconds}))",
                timeout=15,
            )
        )
        if any(
            float(settings[key]) != float(value)
            for key, value in record["timeout_env"].items()
        ):
            raise ReleaseError(
                "product runtime timeout settings differ from the release record"
            )
        return container

    def ready(self, slot: str, attempts: int = 12) -> None:
        self.verify_slot(slot)
        nginx = self.nginx_identity()
        for attempt in range(attempts):
            try:
                response = self.docker(
                    "exec",
                    nginx["id"],
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "10",
                    "-H",
                    f"Host: {self.runtime.api_host}",
                    "-H",
                    "X-Forwarded-For: 127.0.0.1",
                    "-H",
                    "X-Forwarded-Proto: https",
                    f"http://{slot}:8000/api/v1/ready",
                    timeout=12,
                )
                if json.loads(response) == {"status": "ready"}:
                    return
            except (ReleaseError, ValueError):
                pass
            if attempt + 1 < attempts:
                time.sleep(1)
        raise ReleaseError("candidate did not become production ready")

    def smoke(self, slot: str) -> None:
        nginx = self.nginx_identity()
        host = self.runtime.api_host
        response = (
            self.docker(
                "exec",
                nginx["id"],
                "curl",
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "10",
                "--http1.1",
                "-H",
                "Connection: close",
                "--cacert",
                f"/etc/letsencrypt/live/{host}/fullchain.pem",
                "--resolve",
                f"{host}:443:127.0.0.1",
                "--dump-header",
                "-",
                f"https://{host}/api/v1/health",
                timeout=12,
            )
            .lower()
            .splitlines()
        )
        if (
            f"x-release-id: {self.state['slots'][slot]['sha']}" not in response
            or f"x-release-slot: {slot}" not in response
        ):
            raise ReleaseError("HTTPS traffic did not reach the expected release")

    def reconcile(self) -> None:
        if self.state["transaction"] or self.state["phase"] not in {
            "stable",
            "bootstrap",
        }:
            raise ReleaseError("unfinished release requires explicit recover")
        if fingerprint(self.active_config) != self.state["config_hash"]:
            raise ReleaseError("active Nginx configuration drifted")
        self.nginx_identity()
        postgres = self.container("postgres")
        if not postgres or not postgres["State"]["Running"]:
            raise ReleaseError("PostgreSQL must already be running")
        if self.state.get("postgres_id") != postgres["Id"]:
            raise ReleaseError("PostgreSQL identity drifted")
        active = self.state["active"]
        if active:
            self.verify_slot(active)
        for slot in SLOTS:
            actual = self.container(slot)
            if slot != active and actual and actual["State"]["Running"]:
                raise ReleaseError("inactive slot is unexpectedly running")

    def render(self, slot: str | None, destination: Path, worker_seconds: int) -> None:
        args = [
            sys.executable,
            str(self.checkout / "deploy" / "nginx" / "render.py"),
            "--host",
            self.runtime.api_host,
            "--drain-seconds",
            str(worker_seconds),
            "--output",
            str(destination),
        ]
        if slot:
            args += [
                "--slot",
                slot,
                "--release",
                self.state["slots"][slot]["sha"],
                "--tls",
            ]
        execute(args, 15)

    def bootstrap(self) -> None:
        if self.state["phase"] != "empty":
            raise ReleaseError("bootstrap is only valid for an empty journal")
        self.mount()
        for relative in (
            "nginx/candidates",
            "state/certbot",
            "acme/letsencrypt",
            "acme/webroot",
            "acme/work",
            "acme/logs",
        ):
            (self.root / relative).mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.root / "acme" / "webroot").chmod(0o755)
        self.compose_environment()
        for service in ("postgres", "nginx", *SLOTS):
            if self.container(service):
                raise ReleaseError("bootstrap refuses preexisting unmanaged containers")
        self.render(None, self.active_config, self.runtime.budgets.drain)
        self.state.update(
            phase="bootstrap_pending", config_hash=fingerprint(self.active_config)
        )
        self.save()
        self.compose(
            "up", "--detach", "--no-recreate", "postgres", "nginx", timeout=180
        )
        self.nginx_identity()
        self.wait_postgres()
        postgres = self.container("postgres")
        if not postgres or not postgres["State"]["Running"]:
            raise ReleaseError("PostgreSQL bootstrap failed")
        self.state.update(phase="bootstrap", postgres_id=postgres["Id"])
        self.save()

    def wait_postgres(self) -> None:
        for attempt in range(60):
            try:
                self.compose(
                    "exec",
                    "--no-TTY",
                    "postgres",
                    "pg_isready",
                    "--host",
                    "127.0.0.1",
                    "--username",
                    "postgres",
                    timeout=5,
                )
                return
            except ReleaseError:
                if attempt < 59:
                    time.sleep(1)
        raise ReleaseError("PostgreSQL TCP startup did not complete")

    def image_record(self, image: str, sha: str) -> dict[str, Any]:
        if not IMAGE.fullmatch(image) or not SHA.fullmatch(sha):
            raise ReleaseError(
                "release requires an immutable image and full commit SHA"
            )
        inspected = self.inspect(image, "image")
        if (inspected.get("Config", {}).get("Labels") or {}).get(
            "org.opencontainers.image.revision"
        ) != sha:
            raise ReleaseError("image revision does not match the requested release")
        if image.startswith("sha256:"):
            valid = inspected["Id"] == image
        else:
            valid = image in (inspected.get("RepoDigests") or [])
        if not valid:
            raise ReleaseError("image digest does not match the requested release")
        env_file = self.runtime.immutable_environment(self.runtime.app_env, "app")
        return {
            "image": image,
            "image_id": inspected["Id"],
            "sha": sha,
            "env_file": str(env_file),
            "env_hash": fingerprint(env_file),
            "config_revision": self.runtime.config_revision,
            "budgets": asdict(self.runtime.budgets),
            "asset_hashes": {
                name: fingerprint(self.root / "private" / name)
                for name in ("db-ca.crt", "password-blocklist.txt")
            },
            "timeout_env": {
                key: self.runtime.app_env.get(key, default)
                for key, default in (
                    ("AI_TIMEOUT_SECONDS", "90"),
                    ("AI_CLEANUP_TIMEOUT_SECONDS", "5"),
                    ("SHUTDOWN_TIMEOUT_SECONDS", "10"),
                )
            },
        }

    def deploy(self, image: str, sha: str, migrate: bool = False) -> None:
        self.mount()
        self.reconcile()
        old = self.state["active"]
        if old:
            # DB 이동과 CSRF key rotation은 동시 구/신 요청의 호환성을 깨므로 별도 절차가 필요하다.
            prior_env = self.read_environment(
                Path(self.state["slots"][old]["env_file"])
            )
            for key in ("DATABASE_URL", "CSRF_SIGNING_KEY"):
                if prior_env.get(key) != self.runtime.app_env.get(key):
                    raise ReleaseError(
                        "DB target or CSRF key rotation requires a separate procedure"
                    )
        slot = "app_green" if old == "app_blue" else "app_blue"
        record = self.image_record(image, sha)
        self.begin(slot, record, migrate)

    def rollback(self) -> None:
        self.mount()
        self.reconcile()
        previous = self.state["previous"]
        if previous not in SLOTS or previous == self.state["active"]:
            raise ReleaseError("no compatible previous release is recorded")
        # production readiness는 코드에 고정된 호환 revision을 검사한다. downgrade는 없다.
        self.begin(previous, self.state["slots"][previous], False)

    def begin(self, slot: str, record: dict[str, Any], migrate: bool) -> None:
        old = self.state["active"]
        prior_target = self.state["slots"].get(slot)
        self.state["slots"][slot] = record
        self.state["target"] = slot
        old_budgets = self.state["slots"][old]["budgets"] if old else record["budgets"]
        budgets = {
            key: max(value, old_budgets[key])
            for key, value in record["budgets"].items()
        }
        candidate = (
            self.root
            / "nginx"
            / "candidates"
            / f"{slot}-{record['sha']}-{time.time_ns()}.conf"
        )
        backup = candidate.with_suffix(".previous")
        atomic_write(backup, self.active_config.read_text())
        transaction = {
            "target": slot,
            "old": old,
            "stage": "prepared",
            "candidate": str(candidate),
            "backup": str(backup),
            "old_hash": self.state["config_hash"],
            "workers": [],
            "nginx": self.nginx_identity(),
            "budgets": budgets,
            "prior_previous": self.state["previous"],
            "migration": {
                "name": f"{self.runtime.project}-migrate-{time.time_ns()}",
                "status": "requested",
            }
            if migrate
            else None,
            "prior_target": prior_target,
        }
        self.state.update(phase="pending", transaction=transaction)
        self.save()
        self.compose_environment()
        try:
            if migrate:
                self.migrate(transaction)
            self.compose(
                "up",
                "--detach",
                "--no-deps",
                "--force-recreate",
                slot,
                slot=slot,
                timeout=180,
            )
            transaction["stage"] = "candidate_started"
            self.save()
            self.ready(slot)
            self.render(slot, candidate, budgets["drain"])
            self.test_config(candidate)
            transaction.update(
                stage="config_intent",
                new_hash=fingerprint(candidate),
                workers=self.workers(transaction["nginx"]),
            )
            self.save()
            atomic_write(self.active_config, candidate.read_text())
            transaction["stage"] = "reload_pending"
            self.save()
            self.reload_and_drain()
        except ReleaseError:
            # config 설치 여부가 모호한 구간은 recover가 hash와 실제 worker를 대조한다.
            self.state["phase"] = "failed"
            self.save()
            raise

    def test_config(self, candidate: Path) -> None:
        relative = candidate.relative_to(self.root / "nginx")
        self.docker(
            "exec",
            self.nginx_identity()["id"],
            "nginx",
            "-t",
            "-c",
            f"/etc/nginx/runtime/{relative}",
            timeout=15,
        )

    def reload_and_drain(self) -> None:
        transaction = self.state["transaction"]
        slot = transaction["target"]
        nginx = transaction["nginx"]
        # reload 명령 직후 중단해도 현재 모든 worker를 다시 기록한 뒤 안전하게 재시도한다.
        transaction["workers"] = sorted(
            set(transaction["workers"]) | set(self.workers(nginx))
        )
        transaction["stage"] = "reload_pending"
        transaction["deadline"] = time.time() + transaction["budgets"]["drain"]
        self.save()
        self.docker("exec", nginx["id"], "nginx", "-s", "reload", timeout=15)
        transaction["stage"] = "draining"
        self.save()
        try:
            self.ready(slot, attempts=1)
            self.smoke(slot)
        except ReleaseError:
            self.restore_previous()
            raise ReleaseError(
                "post-switch smoke failed; previous routing restored"
            ) from None
        self.drain(transaction)
        self.finish()

    def drain(self, transaction: dict[str, Any], *, recovering: bool = False) -> None:
        remaining = min(
            transaction["budgets"]["drain"],
            max(0, transaction["deadline"] - time.time()),
        )
        deadline = time.monotonic() + remaining
        while True:
            workers = set(self.workers(transaction["nginx"]))
            if time.monotonic() >= deadline:
                transaction["failure"] = "worker_drain_deadline_exceeded"
                self.state["last_failure"] = transaction["failure"]
                self.save()
                if not recovering or workers.intersection(transaction["workers"]):
                    raise ReleaseError(
                        "drain deadline passed; graceful completion is unproven"
                    )
            if not workers.intersection(transaction["workers"]):
                return
            time.sleep(min(0.5, max(0, deadline - time.monotonic())))

    def stop(self, slot: str) -> None:
        self.verify_slot(slot)
        self.compose(
            "stop",
            "--timeout",
            str(self.state["slots"][slot]["budgets"]["stop"]),
            slot,
            slot=slot,
            timeout=self.state["slots"][slot]["budgets"]["stop"] + 15,
        )
        container = self.container(slot)
        self.verify_stopped(container)

    @staticmethod
    def verify_stopped(container: dict[str, Any] | None) -> None:
        if (
            not container
            or container["State"]["Running"]
            or container["State"].get("ExitCode") not in (0, None)
            or container["State"].get("OOMKilled")
        ):
            raise ReleaseError("app did not complete graceful stop")

    def finish(self) -> None:
        transaction = self.state["transaction"]
        old = transaction["old"]
        transaction["stage"] = "cleanup"
        self.save()
        if old:
            actual = self.container(old)
            if actual and actual["State"]["Running"]:
                self.stop(old)
            else:
                self.verify_stopped(actual)
        self.state.update(
            active=transaction["target"],
            previous=old,
            config_hash=transaction["new_hash"],
            phase="stable",
            transaction=None,
        )
        self.state.pop("target", None)
        self.save()

    def restore_previous(self) -> None:
        transaction = self.state["transaction"]
        old = transaction["old"]
        if not old:
            raise ReleaseError(
                "first release failed after switch; explicit recover required"
            )
        self.ready(old, attempts=1)
        self.test_config(Path(transaction["backup"]))
        transaction["workers"] = sorted(
            set(transaction["workers"]) | set(self.workers(transaction["nginx"]))
        )
        transaction["stage"] = "restore_intent"
        self.save()
        atomic_write(self.active_config, Path(transaction["backup"]).read_text())
        self.docker(
            "exec", transaction["nginx"]["id"], "nginx", "-s", "reload", timeout=15
        )
        transaction.update(
            stage="restore_draining",
            deadline=time.time() + transaction["budgets"]["drain"],
        )
        self.save()
        self.smoke(old)
        self.drain(transaction)
        actual = self.container(transaction["target"])
        if actual and actual["State"]["Running"]:
            self.stop(transaction["target"])
        transaction["stage"] = "restored"
        self.state["phase"] = "failed"
        self.save()

    def recover(self) -> None:
        self.mount()
        if self.state.get("certificate"):
            self.recover_certificate()
            return
        transaction = self.state["transaction"]
        if not transaction:
            if self.state["phase"] == "bootstrap_pending":
                # bootstrap 중간 실패에도 DB는 재생성하지 않고 기존 컨테이너만 시작한다.
                self.compose_environment()
                self.compose(
                    "up", "--detach", "--no-recreate", "postgres", "nginx", timeout=180
                )
                self.nginx_identity()
                self.wait_postgres()
                self.state.update(
                    phase="bootstrap", postgres_id=self.container("postgres")["Id"]
                )
                self.save()
                return
            self.reconcile()
            return
        if self.nginx_identity() != transaction["nginx"]:
            raise ReleaseError(
                "Nginx identity changed; manual reconciliation is required"
            )
        postgres = self.container("postgres")
        if not postgres or postgres["Id"] != self.state["postgres_id"]:
            raise ReleaseError(
                "PostgreSQL identity changed; manual reconciliation is required"
            )
        actual_hash = fingerprint(self.active_config)
        stage = transaction["stage"]
        self.reconcile_migration(transaction)
        if actual_hash not in {transaction["old_hash"], transaction.get("new_hash")}:
            raise ReleaseError(
                "unknown active configuration; recovery refuses to overwrite it"
            )
        if stage in {"prepared", "candidate_started"} or (
            stage == "config_intent" and actual_hash == transaction["old_hash"]
        ):
            # 전환 전 실패한 migration은 사람이 DB 상태를 확인한 후 별도 release로 재시도한다.
            actual = self.container(transaction["target"])
            if actual and actual["State"]["Running"]:
                self.stop(transaction["target"])
            self.restore_target_record(transaction)
            self.state.update(
                phase="stable" if transaction["old"] else "bootstrap", transaction=None
            )
            self.state.pop("target", None)
            self.save()
            return
        if stage in {"restore_intent", "restore_draining", "restored"}:
            if stage != "restored":
                self.restore_previous()
            self.restore_target_record(transaction)
            self.state.update(phase="stable", transaction=None)
            self.state.pop("target", None)
            self.save()
            return
        if actual_hash != transaction.get("new_hash"):
            raise ReleaseError(
                "journal and routing disagree; manual reconciliation is required"
            )
        self.verify_slot(transaction["target"])
        self.test_config(Path(transaction["candidate"]))
        if stage in {"config_intent", "reload_pending"}:
            self.reload_and_drain()
        elif stage in {"draining", "cleanup"}:
            self.ready(transaction["target"], attempts=1)
            self.smoke(transaction["target"])
            self.drain(transaction, recovering=True)
            self.finish()
        else:
            raise ReleaseError("unknown recovery phase")

    def migration_container(self, migration: dict[str, Any]) -> dict[str, Any] | None:
        identities = self.docker(
            "container",
            "ls",
            "--all",
            "--quiet",
            "--filter",
            f"name=^/{migration['name']}$",
        ).split()
        if not identities:
            return None
        if len(identities) != 1:
            raise ReleaseError("ambiguous migration identity")
        container = self.inspect(identities[0])
        record = self.state["slots"][self.state["transaction"]["target"]]
        if (
            container["Image"] != record["image_id"]
            or migration.get("id", container["Id"]) != container["Id"]
        ):
            raise ReleaseError("migration container identity differs from the journal")
        return container

    def migrate(self, transaction: dict[str, Any]) -> None:
        migration = transaction["migration"]
        migration["status"] = "starting"
        self.save()
        # 이름을 먼저 기록하므로 CLI 종료와 관계없이 실제 job을 찾을 수 있다.
        self.compose(
            "run",
            "--detach",
            "--name",
            migration["name"],
            "--no-deps",
            "migrate",
            timeout=30,
        )
        deadline = time.monotonic() + 300
        while True:
            container = self.migration_container(migration)
            if not container:
                raise ReleaseError("migration container is unavailable")
            migration["id"] = container["Id"]
            migration["status"] = (
                "running" if container["State"]["Running"] else "exited"
            )
            self.save()
            if not container["State"]["Running"]:
                if container["State"].get("ExitCode") != 0 or container["State"].get(
                    "OOMKilled"
                ):
                    raise ReleaseError(
                        "migration failed; explicit recovery is required"
                    )
                migration["status"] = "complete"
                self.save()
                return
            if time.monotonic() >= deadline:
                raise ReleaseError(
                    "migration is still running; recovery must observe its exit"
                )
            time.sleep(1)

    def reconcile_migration(self, transaction: dict[str, Any]) -> None:
        migration = transaction.get("migration")
        if not migration:
            return
        container = self.migration_container(migration)
        if container and container["State"]["Running"]:
            raise ReleaseError(
                "migration is still running; no retry or new deployment is allowed"
            )
        if container:
            migration["status"] = (
                "complete" if container["State"].get("ExitCode") == 0 else "failed"
            )
            migration["id"] = container["Id"]
            self.save()
        elif migration["status"] != "requested":
            raise ReleaseError(
                "started migration disappeared; manual reconciliation is required"
            )

    def restore_target_record(self, transaction: dict[str, Any]) -> None:
        if transaction["prior_target"] is None:
            self.state["slots"].pop(transaction["target"], None)
        else:
            self.state["slots"][transaction["target"]] = transaction["prior_target"]
        self.state["previous"] = transaction["prior_previous"]

    def certificate(
        self,
        mode: str,
        email: str | None = None,
        server: str | None = None,
        ca_file: Path | None = None,
    ) -> None:
        self.mount()
        self.reconcile()
        if mode == "issue" and self.state["phase"] != "bootstrap":
            raise ReleaseError("initial certificate issuance requires HTTP bootstrap")
        if mode != "issue" and self.state["phase"] != "stable":
            raise ReleaseError("certificate renewal requires a stable HTTPS release")
        if mode == "issue" and (
            not email or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email)
        ):
            raise ReleaseError("initial certificate issuance requires an email address")
        options: list[str] = []
        if server:
            parsed = urlsplit(server)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ReleaseError("ACME server must be an exact HTTPS URL")
            options.extend(["--server", server])
        run_options: list[str] = []
        if ca_file:
            from config import private_path

            private_path(ca_file)
            run_options = [
                "--volume",
                f"{ca_file.resolve()}:/run/config/acme-ca.crt:ro",
                "--env",
                "REQUESTS_CA_BUNDLE=/run/config/acme-ca.crt",
            ]
        command = (
            [
                "certonly",
                "--webroot",
                "--webroot-path",
                "/var/www/acme",
                "--cert-name",
                self.runtime.api_host,
                "--domain",
                self.runtime.api_host,
                "--agree-tos",
                "--email",
                email or "",
            ]
            if mode == "issue"
            else ["renew"]
        )
        command.extend(
            [
                "--non-interactive",
                "--deploy-hook",
                "/bin/sh /opt/certbot/mark-installed.sh",
                *options,
            ]
        )
        if mode == "dry-run":
            command.append("--dry-run")
        certificate = {
            "mode": mode,
            "stage": "starting",
            "prior_phase": self.state["phase"],
            "name": f"{self.runtime.project}-certificate-{time.time_ns()}",
            "nginx": self.nginx_identity(),
            "workers": [],
            "old_marker": self.certificate_marker(),
            "budgets": self.state["slots"][self.state["active"]]["budgets"]
            if self.state["active"]
            else asdict(self.runtime.budgets),
        }
        self.state.update(phase="certificate_pending", certificate=certificate)
        self.save()
        try:
            self.compose(
                "run",
                "--detach",
                "--name",
                certificate["name"],
                *run_options,
                "--no-deps",
                "certbot",
                *command,
                timeout=30,
            )
            certificate["stage"] = "running"
            self.save()
            self.wait_certificate(certificate)
            self.apply_certificate(certificate)
        except ReleaseError:
            self.state["phase"] = "certificate_failed"
            self.save()
            raise

    def certificate_marker(self) -> str | None:
        marker = self.root / "state" / "certbot" / "installed"
        if not marker.exists():
            return None
        value = marker.read_text().strip()
        if not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ReleaseError("certificate installation marker is invalid")
        return value

    def certificate_container(
        self, certificate: dict[str, Any]
    ) -> dict[str, Any] | None:
        identities = self.docker(
            "container",
            "ls",
            "--all",
            "--quiet",
            "--filter",
            f"name=^/{certificate['name']}$",
        ).split()
        if not identities:
            return None
        if len(identities) != 1:
            raise ReleaseError("ambiguous certificate job identity")
        container = self.inspect(identities[0])
        if (
            container["Config"]["Image"] != self.runtime.images["certbot"]
            or certificate.get("id", container["Id"]) != container["Id"]
        ):
            raise ReleaseError("certificate job identity differs from the journal")
        return container

    def wait_certificate(self, certificate: dict[str, Any]) -> None:
        deadline = time.monotonic() + 300
        while True:
            container = self.certificate_container(certificate)
            if not container:
                raise ReleaseError("certificate job is unavailable")
            certificate["id"] = container["Id"]
            self.save()
            if not container["State"]["Running"]:
                if container["State"].get("ExitCode") != 0 or container["State"].get(
                    "OOMKilled"
                ):
                    certificate["stage"] = "job_failed"
                    self.save()
                    raise ReleaseError(
                        "certificate job failed; active routing was preserved"
                    )
                certificate["stage"] = "issued"
                self.save()
                return
            if time.monotonic() >= deadline:
                raise ReleaseError(
                    "certificate job is still running; explicit recovery is required"
                )
            time.sleep(1)

    @staticmethod
    def leaf_digest(content: str) -> str:
        match = re.search(
            r"-----BEGIN CERTIFICATE-----\s*(.*?)\s*-----END CERTIFICATE-----",
            content,
            re.DOTALL,
        )
        if not match:
            raise ReleaseError("certificate leaf is unavailable")
        try:
            der = base64.b64decode("".join(match.group(1).split()), validate=True)
        except ValueError:
            raise ReleaseError("certificate leaf is invalid") from None
        return hashlib.sha256(der).hexdigest()

    def verify_certificate(self) -> None:
        host = self.runtime.api_host
        fullchain = self.root / "acme" / "letsencrypt" / "live" / host / "fullchain.pem"
        expected = self.leaf_digest(fullchain.read_text())
        for attempt in range(12):
            try:
                response = self.docker(
                    "exec",
                    self.nginx_identity()["id"],
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "10",
                    "--http1.1",
                    "-H",
                    "Connection: close",
                    "--cacert",
                    f"/etc/letsencrypt/live/{host}/fullchain.pem",
                    "--resolve",
                    f"{host}:443:127.0.0.1",
                    "--output",
                    "/dev/null",
                    "--write-out",
                    "%{certs}",
                    f"https://{host}/api/v1/health",
                    timeout=12,
                )
                if self.leaf_digest(response) == expected:
                    return
            except ReleaseError:
                pass
            if attempt < 11:
                time.sleep(0.5)
        raise ReleaseError("HTTPS is not serving the installed certificate")

    def apply_certificate(self, certificate: dict[str, Any]) -> None:
        marker = self.certificate_marker()
        if certificate["mode"] == "dry-run" or marker == certificate["old_marker"]:
            if certificate["mode"] == "dry-run" and marker != certificate["old_marker"]:
                raise ReleaseError(
                    "dry-run unexpectedly changed the installed certificate"
                )
            if certificate["mode"] == "issue" and marker is None:
                raise ReleaseError(
                    "initial certificate issuance produced no installation event"
                )
            self.clear_certificate(certificate)
            return
        chain = (
            self.root
            / "acme"
            / "letsencrypt"
            / "live"
            / self.runtime.api_host
            / "fullchain.pem"
        )
        key = chain.with_name("privkey.pem")
        if not marker or marker != fingerprint(chain) or not key.is_file():
            raise ReleaseError("certificate files differ from the installation event")
        if certificate["prior_phase"] == "bootstrap":
            # 첫 앱의 후보 전체 설정을 검사할 때 HTTPS를 활성화한다.
            self.state["certificate_digest"] = marker
            self.clear_certificate(certificate)
            return
        if self.nginx_identity() != certificate["nginx"]:
            raise ReleaseError("Nginx identity changed during certificate replacement")
        candidate = (
            self.root
            / "nginx"
            / "candidates"
            / f"certificate-{certificate['name']}.conf"
        )
        atomic_write(candidate, self.active_config.read_text())
        self.test_config(candidate)
        certificate["workers"] = sorted(
            set(certificate["workers"]) | set(self.workers(certificate["nginx"]))
        )
        certificate["stage"] = "reload_pending"
        certificate["deadline"] = time.time() + certificate["budgets"]["drain"]
        self.save()
        self.docker(
            "exec", certificate["nginx"]["id"], "nginx", "-s", "reload", timeout=15
        )
        certificate["stage"] = "draining"
        self.save()
        self.smoke(self.state["active"])
        self.verify_certificate()
        self.drain(certificate)
        self.state["certificate_digest"] = marker
        self.clear_certificate(certificate)

    def clear_certificate(self, certificate: dict[str, Any]) -> None:
        self.state.update(phase=certificate["prior_phase"])
        self.state.pop("certificate", None)
        self.save()

    def recover_certificate(self) -> None:
        certificate = self.state["certificate"]
        if self.nginx_identity() != certificate["nginx"]:
            raise ReleaseError(
                "Nginx identity changed; manual certificate reconciliation is required"
            )
        if fingerprint(self.active_config) != self.state["config_hash"]:
            raise ReleaseError("routing drifted during certificate renewal")
        container = self.certificate_container(certificate)
        if container and container["State"]["Running"]:
            raise ReleaseError(
                "certificate job is still running; renewal retry is blocked"
            )
        if certificate["stage"] in {"starting", "running", "job_failed"}:
            if not container and certificate["stage"] != "starting":
                raise ReleaseError(
                    "certificate job disappeared; manual reconciliation is required"
                )
            if not container or container["State"].get("ExitCode") != 0:
                self.state["last_failure"] = "certificate_job_failed"
                self.clear_certificate(certificate)
                return
            certificate["stage"] = "issued"
            self.save()
        if certificate["stage"] == "draining":
            self.smoke(self.state["active"])
            self.verify_certificate()
            self.drain(certificate, recovering=True)
            self.state["certificate_digest"] = self.certificate_marker()
            self.clear_certificate(certificate)
            return
        self.apply_certificate(certificate)

    @staticmethod
    def read_environment(path: Path) -> dict[str, str]:
        try:
            return dict(
                line.split("=", 1) for line in path.read_text().splitlines() if line
            )
        except (OSError, ValueError):
            raise ReleaseError("immutable app environment is invalid") from None

    def status(self) -> dict[str, Any]:
        return {
            "phase": self.state["phase"],
            "last_failure": self.state.get("last_failure"),
            "active": self.state["active"],
            "previous": self.state["previous"],
            "releases": {
                slot: {
                    key: record[key] for key in ("sha", "image_id", "config_revision")
                }
                for slot, record in self.state["slots"].items()
            },
            "pending": self.state["transaction"]["stage"]
            if self.state["transaction"]
            else self.state.get("certificate", {}).get("stage"),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Recoverable single-host app release")
    parser.add_argument("--config", required=True, type=Path)
    actions = parser.add_subparsers(dest="action", required=True)
    deploy = actions.add_parser("deploy")
    deploy.add_argument("--image", required=True)
    deploy.add_argument("--sha", required=True)
    deploy.add_argument("--migrate", action="store_true")
    for name in ("bootstrap", "rollback", "recover", "status"):
        actions.add_parser(name)
    certificate = actions.add_parser("certificate")
    certificate.add_argument("mode", choices=("issue", "renew", "dry-run"))
    certificate.add_argument("--email")
    certificate.add_argument("--server")
    certificate.add_argument("--ca-file", type=Path)
    arguments = parser.parse_args()
    try:
        checkout = Path(__file__).resolve().parent.parent
        runtime = Runtime.read(arguments.config, checkout)
        release = Release(runtime, checkout)
        with release.lock():
            if arguments.action == "deploy":
                release.deploy(arguments.image, arguments.sha, arguments.migrate)
            elif arguments.action == "certificate":
                release.certificate(
                    arguments.mode, arguments.email, arguments.server, arguments.ca_file
                )
            elif arguments.action == "status":
                print(json.dumps(release.status(), sort_keys=True))
            else:
                getattr(release, arguments.action)()
        return 0
    except (ReleaseError, OSError):
        # subprocess 원문·환경·SQL·인증서를 출력하지 않는다.
        print(
            "Release blocked. Inspect the safe status and recover the pending phase.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
