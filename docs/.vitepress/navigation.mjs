import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

function escapeLabel(text) {
  const entities = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  };
  return text.replace(/[&<>"']/g, (character) => entities[character]);
}

function firstHeading(source) {
  let fence;
  let frontmatter = source.startsWith("---\n") || source.startsWith("---\r\n");

  for (const [index, line] of source.split(/\r?\n/).entries()) {
    if (frontmatter) {
      if (index > 0 && /^(---|\.\.\.)\s*$/.test(line)) frontmatter = false;
      continue;
    }
    const marker = line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if (marker) {
      if (!fence) fence = marker[1];
      else if (
        marker[1][0] === fence[0] &&
        marker[1].length >= fence.length &&
        !marker[2].trim()
      )
        fence = undefined;
      continue;
    }
    if (fence) continue;
    const heading = line.match(/^ {0,3}#[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$/);
    if (heading) return heading[1];
  }
}

function pageItem(directory, filename, relativeDirectory) {
  const source = readFileSync(path.join(directory, filename), "utf8");
  const relativePath = [...relativeDirectory, filename];
  const route = relativePath.map(encodeURIComponent).join("/");

  return {
    text: escapeLabel(firstHeading(source) ?? filename.replace(/\.md$/, "")),
    link: `/${route.replace(/(^|\/)README\.md$/, "$1").replace(/\.md$/, "")}`,
  };
}

function folderItems(directory, relativeDirectory = []) {
  const entries = readdirSync(directory, { withFileTypes: true })
    .filter((entry) => !entry.name.startsWith(".") && entry.name !== "public")
    .sort((left, right) =>
      left.name < right.name ? -1 : left.name > right.name ? 1 : 0,
    );
  const files = entries
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .sort((left, right) =>
      left.name === "README.md" ? -1 : right.name === "README.md" ? 1 : 0,
    )
    .map((entry) => pageItem(directory, entry.name, relativeDirectory));
  const folders = entries
    .filter((entry) => entry.isDirectory())
    .map((entry) => ({
      text: escapeLabel(`${entry.name}/`),
      collapsed: false,
      items: folderItems(path.join(directory, entry.name), [
        ...relativeDirectory,
        entry.name,
      ]),
    }))
    .filter((folder) => folder.items.length > 0);

  return [...files, ...folders];
}

/** Build navigation from the same folders teammates see in the repository. */
export function createSidebar(docsDirectory) {
  const items = folderItems(docsDirectory);
  const rootPages = items.filter((item) => item.link);
  const folders = items.filter((item) => item.items);

  return [
    ...(rootPages.length ? [{ text: "docs/", items: rootPages }] : []),
    ...folders,
  ];
}
