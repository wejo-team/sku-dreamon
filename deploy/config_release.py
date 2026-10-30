"""고정된 SSM 설정으로 현재 이미지만 교체하고 실패·중단 시 이전 설정을 복구한다."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from cd_release import CDRelease, Config, engine, read_json, run, trusted
from config import APP_KEYS, REVISION, Runtime, atomic_write, environment
from ssm_config import Source, SourceError

PENDING = "config-pending.json"
SHA = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
# 1차는 AI·요청 제한·실행 시간만 변경한다. 나머지도 SSM 원본에 보관하되
# DB·인증·네트워크·공유 파일 변경은 기존의 별도 운영 절차를 거친다.
MUTABLE_KEYS = frozenset(
    key
    for key in APP_KEYS
    if key.startswith("AI_")
    or key.startswith("LANGSMITH_")
    or key == "OPENAI_API_KEY"
    or key in {"READINESS_TIMEOUT_SECONDS", "SHUTDOWN_TIMEOUT_SECONDS"}
    or (key.startswith("AUTH_") and key.endswith("_LIMIT"))
)


class ConfigError(Exception):
    """설정 내용과 하위 예외를 노출하지 않는 고정 오류 코드."""


def encoded(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n"


def env_hash(values: dict[str, str]) -> str:
    return hashlib.sha256(environment(values, raw=True).encode()).hexdigest()


def identity(record: dict[str, Any]) -> dict[str, str]:
    result = {
        key: record[key] for key in ("sha", "image", "env_hash", "config_revision")
    }
    if (
        not SHA.fullmatch(result["sha"])
        or not DIGEST.fullmatch(result["env_hash"])
        or not REVISION.fullmatch(result["config_revision"])
    ):
        raise ConfigError("invalid_release_identity")
    return result


class ConfigRelease:
    def __init__(
        self,
        config: Config,
        source_path: Path,
        *,
        runner=run,
        engine_factory=engine,
        source_factory=Source.read,
    ) -> None:
        self.cd = CDRelease(config, runner=runner, engine_factory=engine_factory)
        self.config = config
        self.source_path = source_path
        self.source_factory = source_factory
        self.pending = self.cd.root / "state" / PENDING

    @contextmanager
    def configuration_engine(self, checkout: Path) -> Iterator[Any]:
        with self.cd.engine_factory(self.config, checkout) as release:
            release.configuration_operation = True
            try:
                with release.lock():
                    yield release
            finally:
                release.configuration_operation = False

    @staticmethod
    def active(release) -> dict[str, Any]:
        slot = release.state.get("active")
        if slot not in ("app_blue", "app_green"):
            raise ConfigError("active_release_required")
        return release.state["slots"][slot]

    def summary(self, release) -> dict[str, Any]:
        result = self.cd.summary(release)
        active = self.active(release)
        identity(active)
        previous = release.state["slots"].get(release.state.get("previous"), {})
        if previous:
            identity(previous)
        return {
            **result,
            "config_phase": "pending"
            if self.pending.exists() or self.pending.is_symlink()
            else "idle",
            "active_env_hash": active["env_hash"],
            "active_config_revision": active["config_revision"],
            "previous_env_hash": previous.get("env_hash"),
            "previous_config_revision": previous.get("config_revision"),
        }

    def status(self) -> dict[str, Any]:
        with self.cd.lock():
            checkout = self.cd.checkout(self.cd.current_sha())
            with self.configuration_engine(checkout) as release:
                return self.summary(release)

    def snapshot(self, value: dict[str, Any]) -> str:
        contents = encoded(value)
        digest = hashlib.sha256(contents.encode()).hexdigest()
        path = self.snapshot_path(digest)
        if path.exists() or path.is_symlink():
            trusted(path, private=True)
            if path.read_text() != contents:
                raise ConfigError("snapshot_changed")
        else:
            atomic_write(path, contents)
        return digest

    def snapshot_path(self, digest: str) -> Path:
        if not isinstance(digest, str) or not DIGEST.fullmatch(digest):
            raise ConfigError("invalid_snapshot")
        return self.cd.root / "private" / f"config-{digest}.json"

    def read_snapshot(self, digest: str) -> dict[str, Any]:
        path = self.snapshot_path(digest)
        value = read_json(path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ConfigError("snapshot_changed")
        return value

    def publish(self, value: dict[str, Any], allowed: tuple[dict, dict]) -> None:
        if read_json(self.config.runtime_config) not in allowed:
            raise ConfigError("runtime_changed")
        atomic_write(self.config.runtime_config, encoded(value))

    def clear_pending(self) -> None:
        contents = self.pending.read_text()
        self.pending.unlink()
        try:
            self.cd.sync_directory(self.pending.parent)
        except OSError:
            # 삭제 내구성을 확인하지 못했으면 다음 작업을 막는 복구 기록을
            # 다시 남긴다. 실패한 fsync를 완료로 취급하지 않는다.
            atomic_write(self.pending, contents)
            raise

    def runtime_matches(self, value: dict[str, Any], record: dict[str, Any]) -> None:
        if (
            env_hash(value["app_env"]) != record["env_hash"]
            or value["config_revision"] != record["config_revision"]
        ):
            raise ConfigError("runtime_does_not_match_active_release")

    def check_expected(
        self, release, sha: str, digest: str, revision: str
    ) -> dict[str, str]:
        current = identity(self.active(release))
        if (
            current["sha"] != sha
            or current["env_hash"] != digest
            or current["config_revision"] != revision
            or self.cd.current_sha() != sha
        ):
            raise ConfigError("current_configuration_changed")
        return current

    @staticmethod
    def check_changes(old: dict[str, str], new: dict[str, str]) -> None:
        if any(
            old.get(key) != new.get(key)
            for key in (old.keys() | new.keys()) - MUTABLE_KEYS
        ):
            raise ConfigError("setting_requires_separate_procedure")

    def undo(self, release) -> None:
        """복구는 항상 이 작업 전의 설정으로 돌아간다. 불확실하면 journal을 보존한다."""
        transaction = read_json(self.pending)
        if transaction.get("version") != 1:
            raise ConfigError("invalid_configuration_transaction")
        old = self.read_snapshot(transaction["old_snapshot"])
        new = self.read_snapshot(transaction["new_snapshot"])
        before, after = transaction["before"], transaction["after"]
        self.runtime_matches(old, before)
        self.runtime_matches(new, after)
        if self.cd.current_sha() != before["sha"] or before["sha"] != after["sha"]:
            raise ConfigError("recovery_release_changed")
        if read_json(self.config.runtime_config) not in (old, new):
            raise ConfigError("runtime_changed")
        release.runtime = Runtime.parse(old, release.checkout)
        release.load()
        pending = release.state.get("transaction")
        if pending:
            records = release.state["slots"]
            if (
                pending.get("migration") is not None
                or identity(records[pending["old"]]) not in (before, after)
                or identity(records[pending["target"]]) not in (before, after)
                or identity(records[pending["old"]])
                == identity(records[pending["target"]])
            ):
                raise ConfigError("recovery_transaction_changed")
            self.undo_engine(release, pending, before)
        current = identity(self.active(release))
        if current == after and current != before:
            previous = release.state["slots"].get(release.state.get("previous"), {})
            if identity(previous) != before:
                raise ConfigError("recovery_target_changed")
            release.rollback()
        if identity(self.active(release)) != before:
            raise ConfigError("recovery_target_changed")
        release.reconcile()
        release.ready(release.state["active"], attempts=1)
        release.smoke(release.state["active"])
        self.publish(old, (old, new))
        release.compose_environment()
        self.clear_pending()

    def undo_engine(self, release, transaction: dict, before: dict) -> None:
        """전환 후 후보 장애에서는 후보 회복을 기다리지 않고 구 경로를 복원한다."""
        records = release.state["slots"]
        if identity(records[transaction["old"]]) == before and transaction["stage"] in {
            "config_intent",
            "reload_pending",
            "draining",
            "cleanup",
        }:
            release.mount()
            release.verify_host()
            postgres = release.container("postgres")
            actual_hash = hashlib.sha256(release.active_config.read_bytes()).hexdigest()
            if (
                release.nginx_identity() != transaction["nginx"]
                or not postgres
                or postgres["Id"] != release.state["postgres_id"]
                or not postgres["State"]["Running"]
                or actual_hash
                not in {transaction["old_hash"], transaction.get("new_hash")}
            ):
                raise ConfigError("recovery_runtime_changed")
            if actual_hash == transaction.get("new_hash"):
                old_slot = transaction["old"]
                old_container = release.container(old_slot)
                if old_container is None:
                    raise ConfigError("recovery_previous_container_missing")
                if not old_container["State"]["Running"]:
                    release.verify_app_identity(records[old_slot], old_container)
                    release.compose_environment()
                    release.compose(
                        "up",
                        "--detach",
                        "--no-deps",
                        "--no-recreate",
                        old_slot,
                        slot=old_slot,
                        timeout=180,
                    )
                    release.ready(old_slot)
                release.restore_previous()
        release.recover()

    def change(
        self,
        action: str,
        expected_sha: str,
        expected_env_hash: str,
        expected_revision: str,
        version: int = 0,
    ) -> dict[str, Any]:
        if (
            action not in {"apply", "rollback", "recover"}
            or not SHA.fullmatch(expected_sha)
            or not DIGEST.fullmatch(expected_env_hash)
            or not REVISION.fullmatch(expected_revision)
            or type(version) is not int
            or (version <= 0 if action == "apply" else version != 0)
        ):
            raise ConfigError("invalid_request")
        with self.cd.lock():
            checkout = self.cd.checkout(self.cd.current_sha())
            with self.configuration_engine(checkout) as release:
                before = self.check_expected(
                    release, expected_sha, expected_env_hash, expected_revision
                )
                if action == "recover":
                    if self.pending.exists() or self.pending.is_symlink():
                        try:
                            self.undo(release)
                        except Exception:
                            raise ConfigError(
                                "configuration_recovery_required"
                            ) from None
                    else:
                        release.reconcile()
                    return {**self.summary(release), "operation_status": "recovered"}
                if self.pending.exists() or self.pending.is_symlink():
                    raise ConfigError("configuration_recovery_required")
                release.reconcile()
                old = read_json(self.config.runtime_config)
                self.runtime_matches(old, before)
                new = copy.deepcopy(old)
                if action == "apply":
                    snapshot = self.source_factory(self.source_path).fetch(
                        version, self.cd.runner
                    )
                    new["app_env"] = snapshot.app_env
                    new["config_revision"] = snapshot.revision
                else:
                    previous = release.state["slots"].get(release.state.get("previous"))
                    if (
                        not previous
                        or previous["sha"] != before["sha"]
                        or previous["image"] != before["image"]
                    ):
                        raise ConfigError("previous_configuration_unavailable")
                    path = Path(previous["env_file"])
                    trusted(path, private=True)
                    new["app_env"] = release.read_environment(path)
                    new["config_revision"] = previous["config_revision"]
                    self.runtime_matches(new, previous)
                self.check_changes(old["app_env"], new["app_env"])
                candidate = Runtime.parse(new, checkout)
                if candidate.host_identity != release.runtime.host_identity:
                    raise ConfigError("host_configuration_changed")
                after = {
                    **before,
                    "env_hash": env_hash(new["app_env"]),
                    "config_revision": new["config_revision"],
                }
                if after == before:
                    return {**self.summary(release), "operation_status": "unchanged"}
                journal = {
                    "version": 1,
                    "action": action,
                    "before": before,
                    "after": after,
                    "old_snapshot": self.snapshot(old),
                    "new_snapshot": self.snapshot(new),
                }
                atomic_write(self.pending, encoded(journal))
                release.runtime = candidate
                try:
                    if action == "apply":
                        release.deploy(before["image"], before["sha"], migrate=False)
                    else:
                        release.rollback()
                    if identity(self.active(release)) != after:
                        raise ConfigError("unexpected_configuration_result")
                    release.reconcile()
                    self.publish(new, (old, new))
                    self.clear_pending()
                except Exception:
                    try:
                        if not self.pending.exists():
                            atomic_write(self.pending, encoded(journal))
                        self.undo(release)
                    except Exception:
                        raise ConfigError("configuration_recovery_required") from None
                    raise ConfigError("configuration_failed_restored") from None
                return {
                    **self.summary(release),
                    "operation_status": "applied"
                    if action == "apply"
                    else "rolled_back",
                }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Versioned backend configuration release"
    )
    parser.add_argument("--cd-config", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument(
        "--action", choices=("apply", "rollback", "recover", "status"), required=True
    )
    parser.add_argument("--version", type=int, default=0)
    parser.add_argument("--expected-sha", default="")
    parser.add_argument("--expected-env-hash", default="")
    parser.add_argument("--expected-config-revision", default="")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ConfigError("root_required")
        operation = ConfigRelease(Config.read(args.cd_config), args.source_config)
        result = (
            operation.status()
            if args.action == "status"
            else operation.change(
                args.action,
                args.expected_sha,
                args.expected_env_hash,
                args.expected_config_revision,
                args.version,
            )
        )
        print(json.dumps(result, sort_keys=True))
        return 0
    except Exception as error:  # noqa: BLE001 -- 비밀값을 포함할 수 있는 최종 프로세스 경계.
        code = (
            str(error)
            if type(error) in (ConfigError, SourceError)
            else "configuration_failed"
        )
        if not re.fullmatch(r"[a-z_]{3,64}", code):
            code = "configuration_failed"
        print(json.dumps({"error": code}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
