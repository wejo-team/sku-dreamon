"""개발 시드가 운영 주소를 거부하고 유효한 다양한 프로필을 만드는지 검사한다."""

import pytest

from scripts.seed_dev_data import academic_paths, profile_input, validate_target


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
