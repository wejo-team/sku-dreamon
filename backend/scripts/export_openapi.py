"""Export the API contract without loading local settings or starting the app."""

import argparse
import json
import sys
from pathlib import Path

from pydantic import PostgresDsn

from app.core.config import Settings
from app.factory import create_app

DEFAULT_OUTPUT = Path(__file__).resolve().parents[2] / "contracts" / "openapi.json"


def render_openapi() -> str:
    # An explicit value wins over environment variables; no .env or lifespan is used.
    settings = Settings(
        database_url=PostgresDsn(
            "postgresql+asyncpg://unused:unused@127.0.0.1:1/unused"
        ),
        _env_file=None,
    )
    schema = create_app(settings).openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Check without writing")
    args = parser.parse_args()
    output: Path = args.output
    content = render_openapi()

    if args.check:
        if not output.is_file() or output.read_bytes() != content.encode("utf-8"):
            print(
                f"OpenAPI snapshot is missing or stale: {output}\n"
                "Run `uv run python -m scripts.export_openapi` in backend/ "
                "and regenerate frontend API types.",
                file=sys.stderr,
            )
            return 1
        print(f"OpenAPI snapshot is current: {output}")
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8", newline="\n")
    print(f"Exported OpenAPI snapshot: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
