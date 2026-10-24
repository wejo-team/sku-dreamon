"""확인된 공고 JSON을 검증하고 명시적 --apply 요청에만 DB에 등록한다."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from app.core.config import Settings
from app.core.db.session import create_database
from app.schemas.contest_import import ContestImport
from app.services.contest_import import import_contest


class InputUnavailable(Exception):
    """입력 파일을 읽지 못했음을 원문 없이 표시한다."""


class DatabaseImportError(Exception):
    """드라이버별 예외를 CLI의 안전한 DB 실패 계약으로 바꾼다."""


async def run(path: Path, *, apply: bool) -> dict[str, str]:
    try:
        source = await asyncio.to_thread(path.read_bytes)
    except OSError as error:
        raise InputUnavailable from error
    data = ContestImport.model_validate_json(source)
    if not apply:
        return {"status": "validated"}
    database = create_database(str(Settings().database_url))
    try:
        async with database.session() as session:
            contest_id = await import_contest(session, data)
        return {"status": "created", "contestId": str(contest_id)}
    except Exception as error:
        # 연결 전 실패는 SQLAlchemyError가 아닌 OSError·asyncpg 오류일 수 있다.
        # CLI에서는 DB 단계의 내부 예외·접속 정보를 그대로 출력하지 않는다.
        raise DatabaseImportError from error
    finally:
        await database.engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="확인된 공고 JSON을 검증·등록합니다.")
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true", help="검증 후 DB에 신규 저장")
    args = parser.parse_args()
    try:
        result = asyncio.run(run(args.path, apply=args.apply))
    except ValidationError as error:
        # 입력 원문·접속 정보는 출력하지 않고 수정 위치만 안내한다.
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
