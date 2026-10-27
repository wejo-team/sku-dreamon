// VitePress 1.6.4의 개발 검색 갱신 결함을 고친다. 안정판 갱신 시 #182와 함께 제거한다.
import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const marker = "/* wejo-local-search-182 */";
const clientMarker = "/* wejo-local-search-state-182 */";

export function patchSearchClient(source) {
  const state = `const searchIndexData = shallowRef(localSearchIndex)

// hmr
if (import.meta.hot) {
  import.meta.hot.accept('/@localSearchIndex', (m) => {
    if (m) {
      searchIndexData.value = m.default
    }
  })
}`;
  const shared = `${clientMarker}
${state.replace("shallowRef(localSearchIndex)", "searchIndexRef(localSearchIndex)")}`;
  if (source.includes(clientMarker)) {
    if (!source.includes(shared))
      throw new Error(
        "VitePress 검색창 패치가 다릅니다. npm ci 후 다시 적용하세요.",
      );
    return source;
  }
  const start = `<script lang="ts" setup>\nimport localSearchIndex from '@localSearchIndex'`;
  if (source.split(start).length !== 2 || source.split(state).length !== 2) {
    throw new Error(
      "VitePress 검색창 패치 대상이 변경되었습니다. #182를 재검토하세요.",
    );
  }
  // 검색창을 닫아도 HMR 최신 값을 보존하고 다시 열 때 같은 ref를 사용한다.
  return source.replace(state, "").replace(
    start,
    `<script lang="ts">
import localSearchIndex from '@localSearchIndex'
import { shallowRef as searchIndexRef } from 'vue'
${shared}
</script>

<script lang="ts" setup>`,
  );
}

export function patchSource(source) {
  const replacements = [
    [
      "  const indexByLocales = /* @__PURE__ */ new Map();",
      `  ${marker}
  const indexedSections = new Map();
  const indexingFiles = new Map();
  const indexByLocales = /* @__PURE__ */ new Map();`,
    ],
    [
      "  async function indexFile(page) {\n    const file = path$1.join(siteConfig.srcDir, page);",
      `  function indexFile(page) {
    const file = path$1.resolve(siteConfig.srcDir, page);
    const previous = indexingFiles.get(file) || Promise.resolve();
    const current = previous.catch(() => {}).then(() => replaceFile(file));
    indexingFiles.set(file, current);
    return current.finally(() => {
      if (indexingFiles.get(file) === current) indexingFiles.delete(file);
    });
  }
  async function replaceFile(file) {
    const page = slash(path$1.relative(siteConfig.srcDir, file));`,
    ],
    [
      "    const index = getIndexByLocale(locale);\n    const html = await render(file);",
      "    const index = getIndexByLocale(locale);\n    const documents = [];\n    const html = await render(file);",
    ],
    [
      '      const id = anchor ? [fileId, anchor].join("#") : fileId;\n      index.add({',
      '      const id = anchor ? [fileId, anchor].join("#") : fileId;\n      documents.push({',
    ],
    [
      "        titles: titles.slice(0, -1)\n      });\n    }\n  }\n  async function scanForBuild()",
      `        titles: titles.slice(0, -1)
      });
    }
    const previous = indexedSections.get(file);
    if (previous) previous.index.discardAll(previous.ids);
    index.addAll(documents);
    indexedSections.set(file, { index, ids: documents.map(({ id }) => id) });
  }
  async function scanForBuild()`,
    ],
    [
      "      server.moduleGraph.onFileChange(LOCAL_SEARCH_INDEX_REQUEST_PATH);",
      `      const timestamp = Date.now();
      const seen = new Set();
      for (const [id, module] of server.moduleGraph.idToModuleMap) {
        if (id.startsWith(LOCAL_SEARCH_INDEX_REQUEST_PATH)) {
          server.moduleGraph.invalidateModule(module, seen, timestamp, true);
        }
      }`,
    ],
    [
      "            path: mod.url,\n            timestamp: Date.now(),",
      "            path: importer.url,\n            timestamp,",
    ],
    [
      "        updates: [\n          {\n            acceptedPath: mod.url,",
      `        updates: [...mod.importers].filter((importer) => importer.acceptedHmrDeps.has(mod)).map((importer) => (
          {\n            acceptedPath: mod.url,`,
    ],
    [
      '            type: "js-update"\n          }\n        ]',
      '            type: "js-update"\n          }\n        ))',
    ],
    [
      "      server = _server;\n      await scanForBuild();",
      `      server = _server;
      const onFileAddedOrRemoved = (file) => {
        if (file.endsWith(".md")) {
          indexFile(file).then(onIndexUpdated).catch((error) => {
            server.config.logger.error(String(error));
          });
        }
      };
      server.watcher.on("add", onFileAddedOrRemoved).on("unlink", onFileAddedOrRemoved);
      await scanForBuild();`,
    ],
  ];
  // 예전 초안·부분 적용 상태를 같은 marker만으로 정상이라고 취급하지 않는다.
  if (source.includes(marker)) {
    const valid = replacements.every(
      ([, after]) => source.split(after).length === 2,
    );
    if (!valid)
      throw new Error(
        "VitePress 검색 패치가 다릅니다. npm ci 후 다시 적용하세요.",
      );
    return source;
  }
  for (const [before, after] of replacements) {
    if (source.split(before).length !== 2) {
      throw new Error(
        "VitePress 검색 패치 대상이 변경되었습니다. #182를 재검토하세요.",
      );
    }
    source = source.replace(before, after);
  }
  // Vite 6의 import-analysis도 HMR에서 사용하는 절대 virtual ID를 해석해야 한다.
  const resolve = "      if (id.startsWith(LOCAL_SEARCH_INDEX_ID)) {";
  if (source.split(resolve).length !== 3) {
    throw new Error("VitePress 검색 resolve 대상이 변경되었습니다.");
  }
  return source.replaceAll(
    resolve,
    "      if (id.startsWith(LOCAL_SEARCH_INDEX_REQUEST_PATH)) return id;\n" +
      resolve,
  );
}

export async function patchLocalSearch(root) {
  const directory = path.join(root, "node_modules/vitepress");
  const metadata = JSON.parse(
    await readFile(path.join(directory, "package.json"), "utf8"),
  );
  if (metadata.version !== "1.6.4") {
    throw new Error(
      "VitePress 버전이 바뀌었습니다. #182 패치 제거 또는 재검토가 필요합니다.",
    );
  }
  const chunks = path.join(directory, "dist/node");
  const candidates = [];
  for (const name of await readdir(chunks)) {
    if (!name.endsWith(".js")) continue;
    const file = path.join(chunks, name);
    const source = await readFile(file, "utf8");
    if (source.includes('const LOCAL_SEARCH_INDEX_ID = "@localSearchIndex";')) {
      candidates.push({ file, source });
    }
  }
  if (candidates.length !== 1)
    throw new Error("VitePress 검색 모듈을 하나로 찾을 수 없습니다.");
  const { file, source } = candidates[0];
  const patched = patchSource(source);
  const clientFile = path.join(
    directory,
    "dist/client/theme-default/components/VPLocalSearchBox.vue",
  );
  const client = await readFile(clientFile, "utf8");
  const patchedClient = patchSearchClient(client);
  if (patched !== source) await writeFile(file, patched);
  if (patchedClient !== client) await writeFile(clientFile, patchedClient);
}

if (
  process.argv[1] &&
  path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  await patchLocalSearch(fileURLToPath(new URL("../../", import.meta.url)));
}
