"""통합 과목 JSON을 검증하고 --apply 요청에만 원장을 적재한다."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings
from app.core.db.session import create_database
from app.schemas.course_import import CourseImport
from app.services.courses import import_courses


class InputUnavailable(Exception):
    """입력 파일을 읽지 못했음을 원문 없이 표시한다."""


class DatabaseImportError(Exception):
    """DB 단계 실패를 접속 정보 없이 표시한다."""


async def run(path: Path, *, apply: bool) -> dict[str, str | int]:
    try:
        source = await asyncio.to_thread(path.read_bytes)
    except OSError as error:
        raise InputUnavailable from error
    data = CourseImport.model_validate_json(source)
    if not apply:
        return {"status": "validated", "courses": len(data.courses)}
    settings = Settings()
    database = create_database(str(settings.database_url), settings=settings)
    try:
        async with database.session() as session:
            counts = await import_courses(session, data)
        return {"status": "imported", **counts}
    except Exception as error:
        # 드라이버 오류에 포함될 수 있는 접속 정보를 출력하지 않는다.
        raise DatabaseImportError from error
    finally:
        async with asyncio.timeout(settings.shutdown_timeout_seconds):
            await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="통합 과목 JSON을 검증·적재합니다.")
    parser.add_argument("path", type=Path)
    parser.add_argument(
        "--apply", action="store_true", help="검증 후 DB에 신규·갱신 저장"
    )
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.path, apply=args.apply))
    except ValidationError as error:
        locations = [
            ".".join(map(str, item["loc"])) or "document" for item in error.errors()
        ]
        print(
            json.dumps({"error": "INVALID_INPUT", "fields": locations}), file=sys.stderr
        )
        return 2
    except (InputUnavailable, ValueError):
        print('{"error": "INPUT_UNAVAILABLE"}', file=sys.stderr)
        return 2
    except DatabaseImportError:
        print('{"error": "DATABASE_ERROR"}', file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
