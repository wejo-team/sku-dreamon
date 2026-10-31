"""서버 Python 3.13의 Unicode 15.1 기호 집합으로 두 프론트의 정규식을 생성한다.

생성: cd backend && uv run python ../scripts/generate_password_symbols.py
검사: cd backend && uv run python ../scripts/generate_password_symbols.py --check
"""

import argparse
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UNICODE_VERSION = "15.1.0"
TARGETS = (
    Path("frontend/src/features/demo/password-symbols.ts"),
    Path("design-reference/src/features/design-preview/password-symbols.ts"),
)


def render_module() -> str:
    """브라우저의 Unicode 데이터 버전에 좌우되지 않는 코드 포인트 범위를 만든다."""
    if unicodedata.unidata_version != UNICODE_VERSION:
        raise RuntimeError(
            f"Unicode {UNICODE_VERSION}이 필요합니다. "
            "backend의 uv run Python을 사용하세요."
        )
    ranges: list[tuple[int, int]] = []
    start: int | None = None
    for codepoint in range(0x110001):
        included = codepoint < 0x110000 and unicodedata.category(
            chr(codepoint)
        ).startswith(("P", "S"))
        if included and start is None:
            start = codepoint
        elif not included and start is not None:
            ranges.append((start, codepoint - 1))
            start = None
    pattern = "".join(
        f"\\u{{{start:X}}}" + (f"-\\u{{{end:X}}}" if start != end else "")
        for start, end in ranges
    )
    return "\n".join(
        (
            "// 자동 생성: Unicode 15.1.0 문장부호(P)·기호(S). 직접 수정하지 않습니다.",
            "// 생성: cd backend && uv run python "
            "../scripts/generate_password_symbols.py",
            "// 검사: cd backend && uv run python "
            "../scripts/generate_password_symbols.py --check",
            "const passwordSymbolPattern =",
            f"  /[{pattern}]/u;",
            "",
            "export function hasPasswordSymbol(value: string): boolean {",
            "  return passwordSymbolPattern.test(value);",
            "}",
            "",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="파일을 수정하지 않고 비교합니다."
    )
    args = parser.parse_args()
    try:
        expected = render_module()
    except RuntimeError as error:
        print(error, file=sys.stderr)
        return 1
    stale = []
    for relative in TARGETS:
        path = ROOT / relative
        if args.check:
            if not path.is_file() or path.read_text(encoding="utf-8") != expected:
                stale.append(str(relative))
        else:
            path.write_text(expected, encoding="utf-8", newline="\n")
    if stale:
        print(
            "비밀번호 기호 표를 다시 생성하세요: " + ", ".join(stale), file=sys.stderr
        )
        return 1
    print(f"Unicode {UNICODE_VERSION} 기호 표 {'검사' if args.check else '생성'} 완료")
    return 0


if __name__ == "__main__":
    sys.exit(main())
