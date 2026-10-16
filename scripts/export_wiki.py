"""Validate docs and export a flat, deterministic GitHub Wiki (stdlib only)."""

from __future__ import annotations

import argparse
import html
import re
import shutil
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit


class ExportError(ValueError):
    """A document cannot be published without changing or breaking a link."""


def prose_parts(markdown: str) -> list[tuple[bool, str]]:
    """Separate block code so examples are never rewritten."""
    parts: list[tuple[bool, str]] = []
    fence: str | None = None
    for line in markdown.splitlines(keepends=True):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence:
            parts.append((False, line))
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence):
                fence = None
        elif marker:
            fence = marker[1]
            parts.append((False, line))
        elif line.startswith(("    ", "\t")):
            parts.append((False, line))
        else:
            parts.append((True, line))
    return parts


def heading_anchors(markdown: str) -> set[str]:
    """GitHub-style anchors for ordinary ATX/setext headings and HTML ids."""
    anchors: set[str] = set()
    counts: dict[str, int] = {}
    prose = "".join(
        text if editable else "\n" for editable, text in prose_parts(markdown)
    )
    headings = re.findall(r"^ {0,3}#{1,6}\s+(.+?)\s*#*\s*$", prose, re.MULTILINE)
    headings += re.findall(r"^([^\n]+)\n {0,3}(?:=+|-+)\s*$", prose, re.MULTILINE)
    for heading in headings:
        heading = re.sub(r"!?\[([^\]]+)\]\([^)]*\)", r"\1", heading)
        heading = re.sub(r"<[^>]+>", "", html.unescape(heading)).lower()
        slug = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(f"{slug}-{count}" if count else slug)
    anchors.update(re.findall(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', prose))
    return anchors


class WikiExporter:
    def __init__(self, root: Path, repository: str, ref: str) -> None:
        self.root = root.resolve()
        self.docs = self.root / "docs"
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ExportError("repository must be owner/name")
        if not re.fullmatch(r"[A-Za-z0-9._/-]+", ref):
            raise ExportError("ref contains unsupported URL characters")
        self.repository = repository
        self.ref = quote(ref, safe="")
        self.base = f"https://github.com/{repository}"
        self.pages: dict[Path, str] = {}
        self.contents: dict[Path, str] = {}
        used = {"_sidebar", "_footer"}
        for path in sorted(self.docs.rglob("*.md")):
            if path.is_symlink() or not path.resolve().is_relative_to(
                self.docs.resolve()
            ):
                raise ExportError(f"symlinked document is not supported: {path}")
            relative = path.relative_to(self.docs)
            slug = (
                "Home"
                if relative.as_posix() == "README.md"
                else re.sub(r"[^\w-]+", "-", "-".join(relative.with_suffix("").parts))
            )
            if not slug or slug.casefold() in used:
                raise ExportError(f"Wiki page name collision: {relative} → {slug}")
            used.add(slug.casefold())
            self.pages[path] = slug
            self.contents[path] = path.read_text(encoding="utf-8")
        if self.docs / "README.md" not in self.pages:
            raise ExportError("docs/README.md is required for the Wiki home page")

    def source_url(self, path: Path, *, image: bool = False) -> str:
        relative = quote(path.relative_to(self.root).as_posix(), safe="/")
        if image:
            return f"https://raw.githubusercontent.com/{self.repository}/{self.ref}/{relative}"
        view = "tree" if path.is_dir() else "blob"
        return f"{self.base}/{view}/{self.ref}/{relative}"

    def rewrite_target(self, target: str, source: Path, *, image: bool = False) -> str:
        target = html.unescape(target)
        parsed = urlsplit(target)
        if parsed.scheme == "mailto" or (
            parsed.scheme in {"https", "http"} and parsed.netloc
        ):
            return target
        if parsed.scheme or parsed.netloc:
            raise ExportError(f"{source}: unsupported link scheme: {target}")
        decoded = unquote(parsed.path)
        if "\\" in decoded or "\x00" in decoded:
            raise ExportError(f"{source}: invalid local path: {target}")
        if decoded.startswith("/"):
            raise ExportError(
                f"{source}: use a relative path or full HTTPS URL: {target}"
            )
        destination = (source.parent / decoded).resolve() if decoded else source
        if not destination.is_relative_to(self.root):
            raise ExportError(f"{source}: link escapes repository: {target}")
        if not destination.exists():
            raise ExportError(f"{source}: missing link target: {target}")
        if destination.is_dir() and (destination / "README.md") in self.pages:
            destination /= "README.md"
        if destination in self.pages and not image:
            if parsed.fragment and unquote(parsed.fragment) not in heading_anchors(
                self.contents[destination]
            ):
                raise ExportError(f"{source}: missing heading anchor: {target}")
            path = f"{self.base}/wiki/{quote(self.pages[destination])}"
        else:
            if image and not destination.is_file():
                raise ExportError(f"{source}: image target must be a file: {target}")
            path = self.source_url(destination, image=image)
        return urlunsplit((*urlsplit(path)[:3], parsed.query, parsed.fragment))

    def rewrite_prose(self, text: str, source: Path, image_refs: set[str]) -> str:
        # Protect code examples without splitting a surrounding Markdown link
        # whose label itself contains code, such as [the `config` file](...).
        code: list[str] = []

        def hide_code(match: re.Match[str]) -> str:
            code.append(match[0])
            return f"\x00CODE{len(code) - 1}\x00"

        def restore_code(value: str) -> str:
            return re.sub(
                r"\x00CODE(\d+)\x00", lambda match: code[int(match[1])], value
            )

        text = re.sub(r"(`+).*?\1(?!`)", hide_code, text)
        # Raw HTML local links need an HTML parser; reject them rather than ship
        # silently broken Wiki links. Markdown links and images are supported.
        for match in re.finditer(r"(?:href|src)=[\"']([^\"']+)[\"']", text):
            target = match[1]
            if not target.startswith(("https://", "http://", "mailto:", "#")):
                raise ExportError(
                    f"{source}: use Markdown for local HTML links: {target}"
                )

        reference = re.match(r"^( {0,3}\[([^\]]+)\]:\s*)(<[^>]*>|\S+)(.*)$", text)
        if reference:
            prefix, label, destination, suffix = reference.groups()
            angle = destination.startswith("<")
            target = destination[1:-1] if angle else destination
            rewritten = self.rewrite_target(
                target, source, image=label.strip().casefold() in image_refs
            )
            return restore_code(
                prefix
                + (f"<{rewritten}>" if angle else rewritten)
                + suffix
                + ("\n" if text.endswith("\n") else "")
            )

        # Parse balanced destination parentheses (URLs may contain parentheses).
        result: list[str] = []
        cursor = 0
        pattern = re.compile(r"(?<!!)\[([^\]\n]*)\]\(|!\[([^\]\n]*)\]\(")
        for match in pattern.finditer(text):
            if match.start() < cursor:
                continue
            start = match.end()
            end = start
            angle = start < len(text) and text[start] == "<"
            if angle:
                end = text.find(">", start + 1)
                if end < 0:
                    raise ExportError(f"{source}: unclosed angle link destination")
                target = text[start + 1 : end]
                end += 1
            else:
                depth = 0
                while end < len(text):
                    char = text[end]
                    if char == "(" and (end == 0 or text[end - 1] != "\\"):
                        depth += 1
                    elif char == ")" and (end == 0 or text[end - 1] != "\\"):
                        if depth == 0:
                            break
                        depth -= 1
                    elif char.isspace() and depth == 0:
                        break
                    end += 1
                target = text[start:end]
            rewritten = self.rewrite_target(
                target, source, image=match[0].startswith("!")
            )
            result.extend(
                [text[cursor:start], f"<{rewritten}>" if angle else rewritten]
            )
            cursor = end
        result.append(text[cursor:])
        return restore_code("".join(result))

    def render(self, source: Path) -> str:
        markdown = self.contents[source]
        parts = prose_parts(markdown)
        image_refs: set[str] = set()
        for editable, text in parts:
            if editable:
                for match in re.finditer(r"!\[([^\]]+)\](?:\[([^\]]*)\])?", text):
                    image_refs.add((match[2] or match[1]).strip().casefold())
        body = "".join(
            self.rewrite_prose(text, source, image_refs) if editable else text
            for editable, text in parts
        )
        relative = quote(source.relative_to(self.root).as_posix(), safe="/")
        banner = (
            f"> 자동 게시 문서 · [원본]({self.source_url(source)}) · "
            f"[수정 제안]({self.base}/edit/main/{relative})\n"
            "> Wiki에서 직접 수정하지 말고 원본 문서의 PR로 변경해 주세요.\n\n"
        )
        return banner + body.rstrip() + "\n"

    def export(self) -> int:
        rendered = {
            f"{slug}.md": self.render(path) for path, slug in self.pages.items()
        }
        sidebar = [f"[문서 홈]({self.base}/wiki/Home)", ""]
        for path, slug in self.pages.items():
            if slug == "Home":
                continue
            heading = re.search(r"^#\s+(.+)$", self.contents[path], re.MULTILINE)
            title = heading[1] if heading else path.stem
            title = title.replace("[", "\\[").replace("]", "\\]")
            sidebar.append(f"- [{title}]({self.base}/wiki/{quote(slug)})")
        rendered["_Sidebar.md"] = "\n".join(sidebar) + "\n"
        rendered["_Footer.md"] = (
            f"문서 원본: [{self.repository}/docs]({self.base}/tree/main/docs) · "
            f"게시 기준: [{self.ref[:12]}]({self.base}/commit/{self.ref})\n"
        )
        output = self.root / ".wiki-build"
        if output.is_symlink():
            raise ExportError(".wiki-build must not be a symlink")
        if output.exists():
            shutil.rmtree(output)
        output.mkdir()
        for filename, content in rendered.items():
            (output / filename).write_text(content, encoding="utf-8", newline="\n")
        return len(self.pages)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default="wejo-team/wejo-app")
    parser.add_argument(
        "--ref", default="main", help="Commit SHA used for source links"
    )
    args = parser.parse_args()
    try:
        count = WikiExporter(
            Path(__file__).resolve().parents[1], args.repository, args.ref
        ).export()
    except (ExportError, OSError) as error:
        parser.exit(1, f"Wiki export failed: {error}\n")
    print(f"Validated and exported {count} docs pages to .wiki-build/")


if __name__ == "__main__":
    main()
