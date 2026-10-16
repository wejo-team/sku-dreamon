import path from "node:path";

/** Keep Markdown links usable in GitHub, Wiki, and the generated site. */
export function siteLink(href, sourcePath, repositoryUrl, revision) {
  if (!href || /^(?:[a-z][a-z\d+.-]*:|\/\/|#)/i.test(href)) return href;

  const [, pathname, suffix = ""] = href.match(/^([^?#]*)(.*)$/);
  if (!pathname) return href;

  const target = pathname.startsWith("/")
    ? path.posix.join("docs", decodeURIComponent(pathname))
    : path.posix.normalize(
        path.posix.join(
          "docs",
          path.posix.dirname(sourcePath),
          decodeURIComponent(pathname),
        ),
      );

  if (target !== "docs" && !target.startsWith("docs/")) {
    if (target === ".." || target.startsWith("../")) {
      throw new Error(`Link escapes the repository: ${sourcePath} -> ${href}`);
    }
    const encodedPath = target.split("/").map(encodeURIComponent).join("/");
    return `${repositoryUrl}/blob/${revision}/${encodedPath}${suffix}`;
  }

  return pathname.replace(/(^|\/)README\.md$/, "$1index.md") + suffix;
}
