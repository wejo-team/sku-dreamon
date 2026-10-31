#!/usr/bin/env python3
"""수집 장부의 Excel을 학수번호별 공통 교과목 카탈로그로 변환한다.

네트워크·학생 수강 이력·PDF 본문을 사용하지 않으며 교수명은 출력하지 않는다.
학수번호는 사용자가 정한 통합 키이며 학기·연도는 출처 보고서에만 남긴다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TypedDict
from zipfile import ZipFile

NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
TERM_ORDER = {"first": 1, "summer": 2, "second": 3, "winter": 4}
REQUIRED_COLUMNS = {"학수번호", "교과목명", "개설학과(부)"}


class CourseRow(TypedDict):
    code: str
    name: str
    department: str
    sheet: str
    row: int


class Observation(CourseRow):
    year: int
    term: str
    source_id: str


class Course(TypedDict):
    code: str
    name: str
    aliases: list[str]
    departments: list[str]


class Catalog(TypedDict):
    schema_version: str
    courses: list[Course]


class Source(TypedDict):
    source_id: str
    year: int
    term: str
    term_label: str | None
    relative_path: str
    sha256: str
    size_bytes: int
    rows: int
    unique_codes: int


class BuildReport(TypedDict):
    generated_at: str
    schema_version: str
    merge_key: str
    representative_name_rule: str
    normalization: str
    inclusion_rule: str
    coverage_status: str
    requested_years: list[int]
    imported_periods: list[dict[str, int | str]]
    counts: dict[str, int]
    sources: list[Source]
    name_variants: list[dict[str, object]]
    latest_period_name_conflicts: list[dict[str, object]]
    department_variants: list[dict[str, object]]
    shared_names: list[dict[str, object]]
    course_provenance: list[dict[str, object]]


def normalize(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).split())


def cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.get("t") == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//x:t", NS))
    value = cell.findtext("x:v", default="", namespaces=NS)
    return strings[int(value)] if cell.get("t") == "s" and value else value


def read_courses(payload: bytes) -> list[CourseRow]:
    records: list[CourseRow] = []
    with ZipFile(BytesIO(payload)) as archive:
        strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings = [
                "".join(node.text or "" for node in item.findall(".//x:t", NS))
                for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))
            ]
        targets = {
            item.get("Id"): item.get("Target", "")
            for item in ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
            if item.get("TargetMode") != "External"
        }
        for sheet in ET.fromstring(archive.read("xl/workbook.xml")).findall(
            "x:sheets/x:sheet", NS
        ):
            target = targets[sheet.get(REL_ID)]
            member = (
                target.lstrip("/")
                if target.startswith("/")
                else posixpath.normpath("xl/" + target)
            )
            headers = None
            for row in ET.fromstring(archive.read(member)).findall(
                "x:sheetData/x:row", NS
            ):
                cells = {
                    re.sub(r"\d", "", cell.get("r", "")): normalize(
                        cell_text(cell, strings)
                    )
                    for cell in row.findall("x:c", NS)
                }
                if not any(cells.values()):
                    continue
                if headers is None:
                    labels = {
                        re.sub(r"\s+", "", text): col for col, text in cells.items()
                    }
                    if REQUIRED_COLUMNS <= labels.keys():
                        headers = labels
                    continue
                code = cells.get(headers["학수번호"], "")
                name = cells.get(headers["교과목명"], "")
                if not code or not name:
                    raise ValueError(
                        f"Missing course code/name: sheet={sheet.get('name')} "
                        f"row={row.get('r')}"
                    )
                records.append(
                    {
                        "code": code,
                        "name": name,
                        "department": cells.get(headers["개설학과(부)"], ""),
                        "sheet": sheet.get("name", ""),
                        "row": int(row.get("r", "0")),
                    }
                )
            if headers is None:
                raise ValueError(f"Required column header missing: {sheet.get('name')}")
    if not records:
        raise ValueError(
            "Workbook has no course rows; empty-query coverage is tracked separately"
        )
    return records


def build(manifest_path: Path) -> tuple[Catalog, BuildReport]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_code: defaultdict[str, list[Observation]] = defaultdict(list)
    sources: list[Source] = []
    seen_sources = set()
    for asset in manifest["assets"]:
        if asset["kind"] != "course_list":
            continue
        if asset["actual_format"] != "xlsx" or asset["status"] != "registered":
            raise ValueError(f"Unverified XLSX asset: {asset['relative_path']}")
        year, term = asset["year"], asset["term_key"]
        if (
            not isinstance(year, int)
            or not 2020 <= year <= 2026
            or term not in TERM_ORDER
        ):
            raise ValueError(f"Unsupported explicit period: {year}/{term}")
        source_key = (year, term, asset["sha256"])
        if source_key in seen_sources:
            continue
        seen_sources.add(source_key)
        path = (manifest_path.parent / asset["relative_path"]).resolve(strict=True)
        if not path.is_relative_to(manifest_path.parent.resolve()):
            raise ValueError("Registered workbook escapes collection directory")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != asset["sha256"]:
            raise ValueError(f"Workbook hash mismatch: {asset['relative_path']}")
        rows = read_courses(payload)
        source_id = f"{year}-{term}-{asset['sha256'][:12]}"
        sources.append(
            {
                "source_id": source_id,
                "year": year,
                "term": term,
                "term_label": asset.get("term_label"),
                "relative_path": asset["relative_path"],
                "sha256": asset["sha256"],
                "size_bytes": len(payload),
                "rows": len(rows),
                "unique_codes": len({row["code"] for row in rows}),
            }
        )
        for row in rows:
            by_code[row["code"]].append(
                {**row, "year": year, "term": term, "source_id": source_id}
            )
    if not sources:
        raise ValueError("No registered course-list workbooks")

    courses: list[Course] = []
    name_variants: list[dict[str, object]] = []
    latest_conflicts: list[dict[str, object]] = []
    department_variants: list[dict[str, object]] = []
    provenance: list[dict[str, object]] = []
    names_to_codes: defaultdict[str, set[str]] = defaultdict(set)
    for code, observations in sorted(by_code.items()):
        latest = max((row["year"], TERM_ORDER[row["term"]]) for row in observations)
        latest_rows = [
            row
            for row in observations
            if (row["year"], TERM_ORDER[row["term"]]) == latest
        ]
        counts = Counter(row["name"] for row in latest_rows)
        name = min(counts, key=lambda value: (-counts[value], value))
        names = sorted({row["name"] for row in observations})
        departments = sorted(
            {row["department"] for row in observations if row["department"]}
        )
        courses.append(
            {
                "code": code,
                "name": name,
                "aliases": [value for value in names if value != name],
                "departments": departments,
            }
        )
        if len(names) > 1:
            name_variants.append({"code": code, "name": name, "names": names})
        if len(counts) > 1:
            latest_conflicts.append(
                {
                    "code": code,
                    "selected_name": name,
                    "name_counts": dict(sorted(counts.items())),
                }
            )
        if len(departments) > 1:
            department_variants.append({"code": code, "departments": departments})
        for value in names:
            names_to_codes[value].add(code)
        provenance.append(
            {
                "code": code,
                "latest_year": latest[0],
                "latest_term": latest_rows[0]["term"],
                "source_ids": sorted({row["source_id"] for row in observations}),
                "representative_source_ids": sorted(
                    {row["source_id"] for row in latest_rows if row["name"] == name}
                ),
            }
        )
    sources.sort(
        key=lambda source: (
            source["year"],
            TERM_ORDER[source["term"]],
            source["sha256"],
        )
    )
    shared_names: list[dict[str, object]] = [
        {"name": name, "codes": sorted(codes)}
        for name, codes in sorted(names_to_codes.items())
        if len(codes) > 1
    ]
    catalog: Catalog = {"schema_version": "0.1.0", "courses": courses}
    report: BuildReport = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "schema_version": "0.1.0",
        "merge_key": "code",
        "representative_name_rule": (
            "Latest academic year/term (first < summer < second < winter); "
            "most frequent name within that period; lexical tie-break. "
            "Other names become aliases."
        ),
        "normalization": (
            "Unicode NFC and whitespace trim/collapse; "
            "no case conversion or semantic rewriting."
        ),
        "inclusion_rule": (
            "All observed course-list rows, including cancelled offerings and rows "
            "without entered syllabi. Catalog membership is not proof of "
            "completion or current offering."
        ),
        "coverage_status": "not_assessed_against_all_portal_options",
        "requested_years": list(range(2020, 2027)),
        "imported_periods": [
            {"year": year, "term": term}
            for year, term in sorted(
                {(source["year"], source["term"]) for source in sources},
                key=lambda item: (item[0], TERM_ORDER[item[1]]),
            )
        ],
        "counts": {
            "workbooks": len(sources),
            "offering_rows": sum(source["rows"] for source in sources),
            "courses": len(courses),
            "codes_with_multiple_names": len(name_variants),
            "codes_with_conflicting_names_in_latest_period": len(latest_conflicts),
            "codes_with_multiple_departments": len(department_variants),
            "names_shared_by_multiple_codes": len(shared_names),
        },
        "sources": sources,
        "name_variants": name_variants,
        "latest_period_name_conflicts": latest_conflicts,
        "department_variants": department_variants,
        "shared_names": shared_names,
        "course_provenance": provenance,
    }
    return catalog, report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    catalog, report = build(args.manifest.resolve(strict=True))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for filename, data in (("courses.json", catalog), ("build-report.json", report)):
        output = args.output_dir / filename
        pending = output.with_suffix(".json.tmp")
        pending.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        pending.replace(output)
    print(
        json.dumps(
            {**report["counts"], "output": str(args.output_dir.resolve())},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
