"""Excel 원본에서 학수번호별 카탈로그를 재현 가능하게 만드는지 검사한다."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import pytest

from scripts.build_course_catalog import build, read_courses


def workbook(rows: list[tuple[str, str, str]]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets>'
            '<sheet name="Sheet1" r:id="rId1"/></sheets></workbook>',
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships><Relationship Id="rId1" '
            'Target="worksheets/sheet1.xml"/></Relationships>',
        )
        all_rows = [("교과목명", "학수번호", "개설학과(부)"), *rows]
        body = "".join(
            f'<row r="{index}">'
            + "".join(
                f'<c r="{column}{index}" t="inlineStr"><is>'
                f"<t>{escape(value)}</t></is></c>"
                for column, value in zip("ABC", row, strict=True)
            )
            + "</row>"
            for index, row in enumerate(all_rows, 1)
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main"><sheetData>' + body + "</sheetData></worksheet>",
        )
    return buffer.getvalue()


def manifest_file(
    directory: Path,
    periods: list[tuple[int, str, list[tuple[str, str, str]]]],
) -> Path:
    assets = []
    for index, (year, term, rows) in enumerate(periods):
        payload = workbook(rows)
        filename = f"{index}.xlsx"
        (directory / filename).write_bytes(payload)
        assets.append(
            {
                "kind": "course_list",
                "actual_format": "xlsx",
                "status": "registered",
                "year": year,
                "term_key": term,
                "relative_path": filename,
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    path = directory / "manifest.json"
    path.write_text(json.dumps({"assets": assets}), encoding="utf-8")
    return path


def test_catalog_merges_codes_and_keeps_old_names_as_aliases(tmp_path: Path) -> None:
    path = manifest_file(
        tmp_path,
        [
            (2020, "first", [("과거이름", "001A", "A학과")]),
            (2026, "first", [("새이름", "001A", "B학과")]),
            (2026, "summer", [("여름이름", "001A", "B학과")]),
        ],
    )
    catalog, report = build(path)
    assert catalog["courses"] == [
        {
            "code": "001A",
            "name": "여름이름",
            "aliases": ["과거이름", "새이름"],
            "departments": ["A학과", "B학과"],
        }
    ]
    assert report["counts"]["codes_with_multiple_names"] == 1


def test_equal_names_with_different_codes_remain_separate(tmp_path: Path) -> None:
    path = manifest_file(
        tmp_path,
        [(2026, "second", [("과목", "001A", "A학과"), ("과목", "002B", "B학과")])],
    )
    catalog, report = build(path)
    assert [course["code"] for course in catalog["courses"]] == ["001A", "002B"]
    assert report["counts"]["names_shared_by_multiple_codes"] == 1


def test_latest_period_name_conflicts_are_deterministic(tmp_path: Path) -> None:
    rows = [("나", "001", "B학과"), ("가", "001", "A학과")]
    path = manifest_file(tmp_path, [(2026, "winter", rows)])
    first, report = build(path)
    path = manifest_file(tmp_path, [(2026, "winter", list(reversed(rows)))])
    second, _ = build(path)
    assert first == second
    assert first["courses"][0]["name"] == "가"
    assert first["courses"][0]["aliases"] == ["나"]
    assert report["counts"]["codes_with_conflicting_names_in_latest_period"] == 1


def test_xlsx_preserves_string_codes_and_normalizes_whitespace() -> None:
    rows = read_courses(workbook([(" 이름\u00a0 공백 ", "0001", "공통학과")]))
    assert rows[0]["code"] == "0001"
    assert rows[0]["name"] == "이름 공백"


def test_modified_workbook_is_rejected(tmp_path: Path) -> None:
    path = manifest_file(tmp_path, [(2026, "second", [("과목", "001", "학과")])])
    (tmp_path / "0.xlsx").write_bytes(b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        build(path)


@pytest.mark.parametrize("row", [("이름", "", "학과"), ("", "001", "학과")])
def test_missing_course_identity_is_rejected(row: tuple[str, str, str]) -> None:
    with pytest.raises(ValueError, match="Missing course code/name"):
        read_courses(workbook([row]))
