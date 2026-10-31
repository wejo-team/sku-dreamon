"""개발 시드가 운영 주소를 거부하고 유효한 다양한 프로필을 만드는지 검사한다."""

from pathlib import Path

import pytest

from scripts.seed_content import profile_input
from scripts.seed_dev_data import academic_paths, validate_target


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+asyncpg://user:pass@db.example.com/wejo_dev",
        "postgresql+asyncpg://user:pass@localhost/wejo_prod",
        "postgresql+asyncpg://user:pass@127.0.0.1/wejo_test",
    ],
)
def test_seed_rejects_nonlocal_or_nondev_target(url: str) -> None:
    with pytest.raises(ValueError, match="wejo_dev"):
        validate_target(url)


def test_profiles_cover_catalogs_and_optional_states() -> None:
    from app.rules.catalogs import FieldCode, RoleCode, SkillCode

    profiles = [profile_input(i, 1) for i in range(300)]
    assert len({p.real_name for p in profiles}) == 300
    assert {c for p in profiles for c in p.field_codes} == set(FieldCode)
    assert {c for p in profiles for c in p.role_codes} == set(RoleCode)
    assert {c for p in profiles for c in p.skill_codes} == set(SkillCode)
    assert {p.experience_state for p in profiles} == {"provided", "none", "unspecified"}
    assert any(p.portfolio is None for p in profiles)
    assert any(p.portfolio is not None for p in profiles)
    assert any(p.academic_unit_id is None for p in profiles)


def test_academics_preserve_document_hierarchy_and_namesakes() -> None:
    paths = academic_paths()
    assert sum(len(path) == 1 for path in paths) == 6
    assert sum(len(path) == 2 for path in paths) == 31
    assert ("인문사회과학대학", "군사학과") in paths
    assert ("미래융합대학", "군사학과") in paths
    assert ("미래융합대학", "자유전공학부", "AI소프트웨어전공") in paths
    assert not any("전공 미배정" in path for path in paths)
    assert all(len(path) == 1 or path[:-1] in paths for path in paths)


def test_profiles_have_stable_visible_test_identifiers() -> None:
    profiles = [profile_input(i, 1) for i in range(300)]
    for i, profile in enumerate(profiles):
        assert profile.real_name.endswith(f" [테스트 P{i + 1:03d}]")
        assert len(profile.real_name) <= 50
        if profile.portfolio:
            assert str(profile.portfolio.url).startswith("https://example.com/")


def test_legacy_profile_baseline_is_frozen_and_new_content_preserves_choices() -> None:
    import hashlib
    import json

    from scripts.seed_content import legacy_profile_input

    legacy = [legacy_profile_input(i, 1) for i in range(300)]
    assert all("course_codes" not in p.model_fields_set for p in legacy)
    # 신규 선택 필드의 기본값은 구 시드가 실제 제공했던 본문에 추가하지 않는다.
    serialized = json.dumps(
        [p.model_dump(mode="json", exclude_unset=True) for p in legacy],
        ensure_ascii=False,
        sort_keys=True,
    )
    # 변경 전 생성 함수의 실제 300개 출력. 비교 기준 변경은 명시적 검토가 필요하다.
    assert hashlib.sha256(serialized.encode()).hexdigest() == (
        "80a4713c3c59d00c2f2962db3ebf3ec7b84a68533db09d7bffca7964e6d2e42f"
    )
    for i, old in enumerate(legacy):
        new = profile_input(i, 1)
        excluded = {"real_name", "experience_body", "introduction", "portfolio"}
        assert new.model_dump(exclude=excluded) == old.model_dump(exclude=excluded)
        if old.portfolio:
            assert new.portfolio and new.portfolio.url == old.portfolio.url
            assert new.portfolio.title and "가상 프로젝트" in new.portfolio.title
        if new.experience_body:
            assert "가상 교내 프로젝트" in new.experience_body


def test_team_names_are_unique_labeled_and_use_fictional_project_content() -> None:
    from scripts.seed_content import team_content

    content = [team_content(i, "가상 공모전") for i in range(100)]
    assert len({name for name, _ in content}) == 100
    for i, (name, body) in enumerate(content):
        assert name.endswith(f" [테스트 T{i + 1:03d}]")
        assert len(name) <= 40
        assert "가상 프로젝트 팀" in body
        assert len(body) <= 1000


@pytest.mark.parametrize(
    ("arguments", "refresh", "apply"),
    [
        ([], False, False),
        (["--refresh-content"], True, False),
        (["--refresh-content", "--apply"], True, True),
    ],
)
def test_refresh_cli_is_explicit_and_dry_run_by_default(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    arguments: list[str],
    refresh: bool,
    apply: bool,
) -> None:
    from scripts import seed_dev_data as seed

    seen = []

    async def observe_run(
        *,
        apply: bool,
        users_only: bool,
        refresh: bool,
        rebuild_teams: bool,
        check: bool,
    ) -> dict[str, object]:
        seen.append((apply, users_only, refresh, rebuild_teams, check))
        return {"validation": {"quality": {"passed": True}}}

    monkeypatch.setattr(seed, "run", observe_run)
    report = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv", ["seed_dev_data", *arguments, "--report", str(report)]
    )
    seed.main()
    assert seen == [(apply, False, refresh, False, False)]
    assert report.is_file()
