"""Check source Markdown links without writing files (stdlib only)."""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit


class ValidationError(ValueError):
    """A source document contains an unsupported or broken local link."""


def prose_parts(markdown: str) -> list[tuple[bool, str]]:
    """Separate block code so examples are not checked as document links."""
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


class DocsChecker:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.docs = self.root / "docs"
        self.contents: dict[Path, str] = {}
        for path in sorted(self.docs.rglob("*.md")):
            if path.is_symlink() or not path.resolve().is_relative_to(
                self.docs.resolve()
            ):
                raise ValidationError(f"symlinked document is not supported: {path}")
            self.contents[path] = path.read_text(encoding="utf-8")
        if self.docs / "README.md" not in self.contents:
            raise ValidationError("docs/README.md is required as the document index")

    def check_target(self, target: str, source: Path, *, image: bool = False) -> None:
        target = html.unescape(target)
        parsed = urlsplit(target)
        if parsed.scheme == "mailto" or (
            parsed.scheme in {"https", "http"} and parsed.netloc
        ):
            return
        if parsed.scheme or parsed.netloc:
            raise ValidationError(f"{source}: unsupported link scheme: {target}")
        decoded = unquote(parsed.path)
        if "\\" in decoded or "\x00" in decoded:
            raise ValidationError(f"{source}: invalid local path: {target}")
        if decoded.startswith("/"):
            raise ValidationError(
                f"{source}: use a relative path or full HTTPS URL: {target}"
            )
        destination = (source.parent / decoded).resolve() if decoded else source
        if not destination.is_relative_to(self.root):
            raise ValidationError(f"{source}: link escapes repository: {target}")
        if not destination.exists():
            raise ValidationError(f"{source}: missing link target: {target}")
        if image:
            if not destination.is_file():
                raise ValidationError(f"{source}: image target must be a file: {target}")
            return
        if destination.is_dir() and (destination / "README.md") in self.contents:
            destination /= "README.md"
        if destination in self.contents:
            if parsed.fragment and unquote(parsed.fragment) not in heading_anchors(
                self.contents[destination]
            ):
                raise ValidationError(f"{source}: missing heading anchor: {target}")

    def check_prose(self, text: str, source: Path, image_refs: set[str]) -> None:
        # Protect code examples without splitting a surrounding Markdown link
        # whose label itself contains code, such as [the `config` file](...).
        text = re.sub(r"(`+).*?\1(?!`)", "\x00CODE\x00", text)
        # Raw HTML local links need an HTML parser; reject them rather than ship
        # silently broken links. Markdown links and images are supported.
        for match in re.finditer(r"(?:href|src)=[\"']([^\"']+)[\"']", text):
            target = match[1]
            if not target.startswith(("https://", "http://", "mailto:", "#")):
                raise ValidationError(
                    f"{source}: use Markdown for local HTML links: {target}"
                )

        reference = re.match(r"^( {0,3}\[([^\]]+)\]:\s*)(<[^>]*>|\S+)(.*)$", text)
        if reference:
            _, label, destination, _ = reference.groups()
            angle = destination.startswith("<")
            target = destination[1:-1] if angle else destination
            self.check_target(
                target, source, image=label.strip().casefold() in image_refs
            )
            return

        # Parse balanced destination parentheses (URLs may contain parentheses).
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
                    raise ValidationError(f"{source}: unclosed angle link destination")
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
            self.check_target(target, source, image=match[0].startswith("!"))
            cursor = end

    def check_document(self, source: Path) -> None:
        markdown = self.contents[source]
        parts = prose_parts(markdown)
        image_refs: set[str] = set()
        for editable, text in parts:
            if editable:
                for match in re.finditer(r"!\[([^\]]+)\](?:\[([^\]]*)\])?", text):
                    image_refs.add((match[2] or match[1]).strip().casefold())
        for editable, text in parts:
            if editable:
                self.check_prose(text, source, image_refs)

    def check(self) -> int:
        for source in self.contents:
            self.check_document(source)
        return len(self.contents)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        count = DocsChecker(Path(__file__).resolve().parents[1]).check()
    except (ValidationError, OSError) as error:
        parser.exit(1, f"Documentation source validation failed: {error}\n")
    print(f"Validated links and anchors in {count} source Markdown documents.")


if __name__ == "__main__":
    main()
