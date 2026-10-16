"""Check the built documentation's local links and assets (stdlib only)."""

from __future__ import annotations

import argparse
import posixpath
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit


class Document(HTMLParser):
    def __init__(self, text: str) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: set[str] = set()
        self.references: list[str] = []
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if anchor := values.get("id"):
            self.anchors.add(anchor)
        if tag == "a" and (anchor := values.get("name")):
            self.anchors.add(anchor)
        if source := values.get("src"):
            self.references.append(source)
        if tag in {"a", "link"} and (href := values.get("href")):
            self.references.append(href)


def check_site(directory: Path, base: str = "/wejo-app/") -> list[str]:
    """Return errors for references that would break in the deployed subpath."""
    if not base.startswith("/") or not base.endswith("/") or ".." in base.split("/"):
        raise ValueError("base must be an absolute URL path ending with '/'")
    root = directory.resolve()
    if not (root / "index.html").is_file():
        return [f"missing site entry point: {root / 'index.html'}"]

    documents = {
        path.resolve(): Document(path.read_text(encoding="utf-8"))
        for path in sorted(root.rglob("*.html"))
        if path.is_file() and path.resolve().is_relative_to(root)
    }
    errors: list[str] = []
    for source, document in documents.items():
        relative_source = source.relative_to(root).as_posix()
        source_url = f"https://docs.invalid{base}{relative_source}"
        for reference in sorted(set(document.references)):
            parsed = urlsplit(reference)
            # External URLs, data URLs and mail links do not belong to this build.
            if parsed.scheme or parsed.netloc:
                continue
            resolved = urlsplit(urljoin(source_url, reference))
            path = posixpath.normpath(unquote(resolved.path))
            prefix = base.rstrip("/")
            context = f"{relative_source}: {reference}"
            if prefix and path != prefix and not path.startswith(f"{prefix}/"):
                errors.append(f"{context}: URL is outside site base {base}")
                continue

            target = root / path[len(prefix) :].lstrip("/")
            candidates = [target]
            if target.is_dir() or resolved.path.endswith("/"):
                candidates = [target / "index.html"]
            elif target.suffix == "":
                candidates.extend([target.with_suffix(".html"), target / "index.html"])
            target = next(
                (candidate for candidate in candidates if candidate.is_file()), target
            )
            if not target.resolve().is_relative_to(root) or not target.is_file():
                errors.append(f"{context}: missing local file")
                continue

            fragment = unquote(resolved.fragment).split(":~:text=", 1)[0]
            if fragment and target.suffix == ".html":
                target_document = documents.get(target.resolve())
                if target_document is None or (
                    fragment not in target_document.anchors
                    and fragment.lower() != "top"
                ):
                    errors.append(f"{context}: missing HTML anchor #{fragment}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("docs/.vitepress/dist"))
    parser.add_argument("--base", default="/wejo-app/")
    args = parser.parse_args()
    errors = check_site(args.directory, args.base)
    if errors:
        for error in errors:
            print(error)
        print(f"Documentation site validation failed: {len(errors)} error(s).")
        return 1
    print("Documentation site links, fragments and referenced assets are valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
