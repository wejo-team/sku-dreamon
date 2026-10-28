"""E2E 정리 입력의 생성 근거·시드 보호·로컬 대상 제한을 확인한다."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.demo_data import DEV_ACCOUNT_IDS, DEV_TEAM_IDS
from scripts.cleanup_e2e_data import (
    CleanupError,
    Evidence,
    FileHash,
    Manifest,
    Resource,
    file_hash,
    target_identity,
    validate_backup,
    validate_manifest,
)


def evidence_manifest(tmp_path: Path) -> Manifest:
    identity = uuid4()
    path = tmp_path / "resources.json"
    path.write_text(
        json.dumps(
            {"resources": [{"kind": "account", "id": str(identity), "created": True}]}
        )
    )
    return Manifest(
        resources=[
            Resource(
                kind="account",
                id=identity,
                expectedLabel="e2eexample",
                evidence=[
                    Evidence(
                        path=str(path),
                        sha256=file_hash(path),
                        pointer="/resources/0/id",
                        evidenceType="created-resource",
                    )
                ],
            )
        ]
    )


@pytest.mark.parametrize(
    "url",
    [
        "not-a-database-url",
        "postgresql+asyncpg://u:p@db.example.com/wejo_dev",
        "postgresql+asyncpg://u:p@localhost/wejo_test",
        "postgresql+asyncpg://u:p@localhost/wejo_dev?host=remote.example.com",
        "postgresql://u:p@localhost/wejo_dev",
    ],
)
def test_cleanup_rejects_remote_test_or_overridden_database(url: str) -> None:
    with pytest.raises(CleanupError, match="explicit_local_wejo_dev_required"):
        target_identity(url)


def test_target_never_contains_credentials() -> None:
    assert target_identity(
        "postgresql+asyncpg://u:secret@127.0.0.1:55432/wejo_dev"
    ) == ("127.0.0.1:55432/wejo_dev")


def test_created_resource_provenance_is_required(tmp_path: Path) -> None:
    manifest = evidence_manifest(tmp_path)
    validate_manifest(manifest)
    evidence = manifest.resources[0].evidence[0]
    path = Path(evidence.path)
    data = json.loads(path.read_text())
    data["resources"][0]["created"] = False
    path.write_text(json.dumps(data))
    evidence.sha256 = file_hash(path)
    with pytest.raises(CleanupError, match="created_resource_evidence_required"):
        validate_manifest(manifest)


def test_changed_evidence_and_wrong_id_fail(tmp_path: Path) -> None:
    manifest = evidence_manifest(tmp_path)
    evidence = manifest.resources[0].evidence[0]
    Path(evidence.path).write_text("{}")
    with pytest.raises(CleanupError, match="evidence_file_changed"):
        validate_manifest(manifest)
    manifest = evidence_manifest(tmp_path)
    manifest.resources[0].id = uuid4()
    with pytest.raises(CleanupError, match="evidence_id_mismatch"):
        validate_manifest(manifest)


@pytest.mark.parametrize(
    "kind,identity",
    [
        ("account", DEV_ACCOUNT_IDS[0]),
        ("team", DEV_TEAM_IDS[0]),
    ],
)
def test_fixed_seed_resources_are_never_cleanup_candidates(
    tmp_path: Path,
    kind: str,
    identity: object,
) -> None:
    manifest = evidence_manifest(tmp_path)
    resource = manifest.resources[0].model_copy(update={"kind": kind, "id": identity})
    with pytest.raises(CleanupError, match="seed_resource_is_protected"):
        validate_manifest(Manifest(resources=[resource]))


def test_legacy_evidence_requires_exact_json_pointer_and_review(tmp_path: Path) -> None:
    manifest = evidence_manifest(tmp_path)
    evidence = manifest.resources[0].evidence[0]
    evidence.evidenceType = "reviewed-legacy"
    with pytest.raises(CleanupError, match="legacy_evidence_review_required"):
        validate_manifest(manifest)
    evidence.reason = "기존 실행 로그의 생성 응답 UUID와 대조했습니다."
    validate_manifest(manifest)
    evidence.pointer = "/missing/id"
    with pytest.raises(CleanupError, match="invalid_evidence_pointer"):
        validate_manifest(manifest)


def test_backup_must_be_present_unchanged_custom_format(tmp_path: Path) -> None:
    path = tmp_path / "backup.dump"
    path.write_bytes(b"PGDMPtest-fixture")
    backup = FileHash(path=str(path), sha256=file_hash(path))
    validate_backup(backup)
    path.write_bytes(b"changed")
    with pytest.raises(CleanupError, match="backup_file_changed"):
        validate_backup(backup)
    backup.sha256 = file_hash(path)
    with pytest.raises(CleanupError, match="custom_format_pg_dump_required"):
        validate_backup(backup)
