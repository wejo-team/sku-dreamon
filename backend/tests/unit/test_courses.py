"""과목 입력의 정규화·중복·호환성과 CLI 무쓰기 검증을 확인한다."""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from app.cli.courses import run
from app.core.config import Settings
from app.schemas.catalogs import CoursesQuery
from app.schemas.course_import import CourseImport
from app.schemas.profile_write import ProfileWrite
from tests.unit.test_profile_write import payload


def test_omitted_and_explicit_empty_courses_remain_distinguishable() -> None:
    omitted = ProfileWrite.model_validate(payload())
    cleared = ProfileWrite.model_validate(payload() | {"courseCodes": []})
    selected = ProfileWrite.model_validate(payload() | {"courseCodes": [" GE1000 "]})
    assert "course_codes" not in omitted.model_fields_set
    assert "course_codes" in cleared.model_fields_set and cleared.course_codes == []
    assert selected.course_codes == ["GE1000"]


@pytest.mark.parametrize(
    "change",
    [
        {"courseCodes": None},
        {"courseCodes": ["GE1000", " GE1000 "]},
        {"courseCodes": [""]},
        {"courseCodes": ["\x00"]},
        {"courseCodes": ["\ud800"]},
        {"course_codes": []},
    ],
)
def test_invalid_profile_course_input(change: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ProfileWrite.model_validate(payload() | change)


@pytest.mark.parametrize(
    "query",
    [
        {"q": "\x00"},
        {"q": "\ud800"},
        {"q": "a" * 101},
        {"pageSize": 101},
        {"page_size": 10},
    ],
)
def test_invalid_course_query(query: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CoursesQuery.model_validate(query)


def test_import_rejects_duplicate_codes_and_unsupported_fields() -> None:
    course = {"code": "GE1000", "name": "기초 통계", "aliases": [], "departments": []}
    for entries in ([course, course | {"code": " GE1000 "}], [course | {"year": 2026}]):
        with pytest.raises(ValidationError):
            CourseImport.model_validate({"schema_version": "0.1.0", "courses": entries})


async def test_cli_validation_does_not_require_database(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", "not-a-database-url")
    path = tmp_path / "courses.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "courses": [
                    {
                        "code": "GE1000",
                        "name": "기초 통계",
                        "aliases": [],
                        "departments": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert await run(path, apply=False) == {"status": "validated", "courses": 1}


async def test_cli_apply_keeps_validated_database_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "courses.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "0.1.0",
                "courses": [
                    {
                        "code": "GE1000",
                        "name": "기초 통계",
                        "aliases": [],
                        "departments": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings = Settings(
        database_tls_ca_file=tmp_path / "synthetic-ca.pem",
        database_command_timeout_seconds=5,
        _env_file=None,
    )
    database = SimpleNamespace(
        session=Mock(return_value=AsyncMock()),
        engine=SimpleNamespace(dispose=AsyncMock()),
    )
    factory = Mock(return_value=database)
    importer = AsyncMock(return_value={"created": 1, "updated": 0, "unchanged": 0})
    monkeypatch.setattr("app.cli.courses.Settings", Mock(return_value=settings))
    monkeypatch.setattr("app.cli.courses.create_database", factory)
    monkeypatch.setattr("app.cli.courses.import_courses", importer)
    assert await run(path, apply=True) == {
        "status": "imported",
        "created": 1,
        "updated": 0,
        "unchanged": 0,
    }
    assert factory.call_args.kwargs["settings"] is settings
    importer.assert_awaited_once()
    database.engine.dispose.assert_awaited_once()
