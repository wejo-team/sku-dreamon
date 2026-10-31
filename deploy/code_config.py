"""코드와 설정의 같은 전환을 기록하고 저장한 쌍으로만 실패·중단을 복구한다."""

from __future__ import annotations

import copy
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from cd_release import CDError, read_json, trusted
from config import atomic_write
from config_release import ConfigError, ConfigRelease, encoded, env_hash, identity

PENDING = "code-config-pending.json"


class CodeConfiguration(ConfigRelease):
    """설정 전용 작업의 비공개 snapshot·게시·검증 함수를 공유한다."""

    def __init__(self, cd, source_path: Path, source_factory=None) -> None:
        self.cd = cd
        self.config = cd.config
        self.source_path = source_path
        self.source_factory = source_factory
        self.pending = cd.root / "state" / PENDING

    @contextmanager
    def code_engine(self, checkout: Path, snapshot: str | None = None) -> Iterator[Any]:
        config = self.config
        if snapshot is not None:
            self.read_snapshot(snapshot)
            config = replace(config, runtime_config=self.snapshot_path(snapshot))
        with self.cd.engine_factory(config, checkout) as release:
            release.code_configuration_operation = True
            try:
                with release.lock():
                    yield release
            finally:
                release.code_configuration_operation = False

    def select(self, release, action: str) -> tuple[dict, dict, dict, dict]:
        """SSM 조회는 새 SHA 배포에만 한 번 수행하며 rollback은 슬롯 파일을 읽는다."""
        old = read_json(self.config.runtime_config)
        before = identity(self.active(release))
        self.runtime_matches(old, before)
        new = copy.deepcopy(old)
        if action == "deploy":
            source = (self.source_factory or release.configuration_source)(
                self.source_path
            )
            snapshot = source.fetch_latest(self.cd.runner)
            new["app_env"] = snapshot.app_env
            new["config_revision"] = snapshot.revision
            keys = release.configuration_app_keys
            mutable = frozenset(
                key
                for key in keys
                if key.startswith(("AI_", "LANGSMITH_"))
                or key == "OPENAI_API_KEY"
                or key in {"READINESS_TIMEOUT_SECONDS", "SHUTDOWN_TIMEOUT_SECONDS"}
                or (key.startswith("AUTH_") and key.endswith("_LIMIT"))
            )
            self.check_changes(old["app_env"], new["app_env"], mutable)
        else:
            record = release.state["slots"][release.state["previous"]]
            path = Path(record["env_file"])
            trusted(path, private=True)
            new["app_env"] = release.read_environment(path)
            new["config_revision"] = record["config_revision"]
            self.runtime_matches(new, record)
        after = {
            "env_hash": env_hash(new["app_env"]),
            "config_revision": new["config_revision"],
        }
        return old, new, before, after

    def start(
        self, action: str, old: dict, new: dict, before: dict, after: dict
    ) -> dict:
        journal = {
            "version": 1,
            "action": action,
            "engine_sha": after["sha"] if action == "deploy" else before["sha"],
            "before": before,
            "after": after,
            "old_snapshot": self.snapshot(old),
            "new_snapshot": self.snapshot(new),
        }
        atomic_write(self.pending, encoded(journal))
        return journal

    def journal(self) -> tuple[dict, dict, dict]:
        journal = read_json(self.pending)
        if (
            journal.get("version") != 1
            or journal.get("action") not in {"deploy", "rollback"}
            or journal.get("engine_sha")
            != journal["after" if journal["action"] == "deploy" else "before"]["sha"]
            or journal["before"]["sha"] == journal["after"]["sha"]
        ):
            raise ConfigError("invalid_code_configuration_transaction")
        for key in ("before", "after"):
            identity(journal[key])
        old = self.read_snapshot(journal["old_snapshot"])
        new = self.read_snapshot(journal["new_snapshot"])
        self.runtime_matches(old, journal["before"])
        self.runtime_matches(new, journal["after"])
        if self.cd.current_sha() not in {
            journal["before"]["sha"],
            journal["after"]["sha"],
        } or read_json(self.config.runtime_config) not in (old, new):
            raise ConfigError("code_configuration_state_changed")
        return journal, old, new

    def finish(self, release, old: dict, new: dict, after: dict) -> None:
        if identity(self.active(release)) != after:
            raise ConfigError("unexpected_code_configuration_result")
        release.reconcile()
        self.publish(new, (old, new))
        self.cd.publish(
            after["sha"], allowed={self.journal()[0]["before"]["sha"], after["sha"]}
        )
        self.clear_pending()

    def undo(self) -> None:
        """migration 확인은 기존 엔진에 맡기고 전환 전 코드·설정 쌍을 복원한다."""
        journal, old, new = self.journal()
        before, after = journal["before"], journal["after"]
        checkout = self.cd.checkout(journal["engine_sha"])
        with self.code_engine(checkout, journal["old_snapshot"]) as release:
            self.runtime_matches(old, before)
            transaction = release.state.get("transaction")
            if transaction:
                records = release.state["slots"]
                if (
                    identity(records[transaction["old"]]) != before
                    or identity(records[transaction["target"]]) != after
                ):
                    raise ConfigError("recovery_transaction_changed")
                release.reconcile_migration(transaction)
                self.undo_engine(release, transaction, before)
            current = identity(self.active(release))
            if current == after:
                previous = release.state["slots"].get(release.state.get("previous"))
                if previous is None or identity(previous) != before:
                    raise ConfigError("recovery_target_changed")
                release.rollback()
            if identity(self.active(release)) != before:
                raise ConfigError("recovery_target_changed")
            release.reconcile()
            release.ready(release.state["active"], attempts=1)
            release.smoke(release.state["active"])
            self.publish(old, (old, new))
            release.compose_environment()
            self.cd.publish(before["sha"], allowed={before["sha"], after["sha"]})
            self.clear_pending()

    def recover(self) -> dict[str, Any]:
        with self.cd.lock():
            if self.pending.exists() or self.pending.is_symlink():
                try:
                    self.undo()
                except Exception:  # noqa: BLE001 -- 비밀값이 섞인 복구 오류 원문을 숨긴다.
                    raise CDError("code_configuration_recovery_required") from None
            else:
                with self.code_engine(
                    self.cd.checkout(self.cd.current_sha())
                ) as release:
                    self.cd.stable(release)
                    release.reconcile()
        return self.cd.status()
