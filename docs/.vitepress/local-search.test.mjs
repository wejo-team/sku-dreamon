// 실제 파일 감시와 개발 서버의 virtual 모듈을 거쳐 검색 색인 갱신을 검사한다.
import assert from "node:assert/strict";
import {
  mkdtemp,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { createServer } from "vitepress";
import MiniSearch from "minisearch";
import { patchSearchClient, patchSource } from "./patch-local-search.mjs";

const root = fileURLToPath(new URL("../../", import.meta.url));

test("검색 패치는 중복 적용을 피하고 예상하지 못한 소스를 거부한다", async () => {
  assert.throws(() => patchSource("unrecognized module"), /대상이 변경/);
  assert.throws(
    () => patchSource("/* wejo-local-search-182 */\nunchanged"),
    /패치가 다릅니다/,
  );
  const directory = path.join(root, "node_modules/vitepress/dist/node");
  const modules = await Promise.all(
    (await readdir(directory))
      .filter((name) => name.endsWith(".js"))
      .map((name) => readFile(path.join(directory, name), "utf8")),
  );
  const sources = modules.filter((source) =>
    source.includes('const LOCAL_SEARCH_INDEX_ID = "@localSearchIndex";'),
  );
  assert.equal(sources.length, 1);
  assert.equal(patchSource(sources[0]), sources[0]);
  const client = await readFile(
    path.join(
      root,
      "node_modules/vitepress/dist/client/theme-default/components/VPLocalSearchBox.vue",
    ),
    "utf8",
  );
  assert.equal(patchSearchClient(client), client);
  assert.throws(() => patchSearchClient("unexpected component"), /대상이 변경/);
});

test(
  "파일 감시로 제목·파일 추가/삭제·검색 제외·연속 편집이 반영된다",
  { timeout: 30_000 },
  async () => {
    await mkdir(path.join(root, ".bugbash"), { recursive: true });
    const directory = await mkdtemp(path.join(root, ".bugbash/search-test-"));
    let server;
    try {
      await mkdir(path.join(directory, ".vitepress"));
      await writeFile(
        path.join(directory, ".vitepress/config.mjs"),
        `
export default { themeConfig: { search: { provider: "local", options: {
  async _render(source, env, md) {
    if (source.includes("Slowuniquesearch")) await new Promise(resolve => setTimeout(resolve, 250));
    const html = md.render(source, env);
    return env.frontmatter?.search === false ? "" : html;
  }
} } } };\n`,
      );
      const source = path.join(directory, "index.md");
      await writeFile(source, "# Initialuniquesearch\n\nOriginal content.\n");
      server = await createServer(directory, { host: "127.0.0.1", port: 0 });
      await server.listen();
      const url = `http://127.0.0.1:${server.httpServer.address().port}`;
      // 먼저 로드해 Vite가 캐시하는 virtual 모듈도 갱신되는지 확인한다.
      await fetch(`${url}/@localSearchIndex`);
      const index = async () => {
        const response = await fetch(`${url}/@localSearchIndexroot`);
        assert.equal(response.status, 200);
        const module = await response.text();
        const serialized = JSON.parse(
          module.split("\n")[0].slice("export default ".length),
        );
        return MiniSearch.loadJSON(serialized, {
          fields: ["title", "titles", "text"],
          storeFields: ["title", "titles"],
        });
      };
      const expectIndex = async (present, absent = []) => {
        let current;
        for (let attempt = 0; attempt < 200; attempt++) {
          current = await index();
          if (
            (!present || current.search(present).length > 0) &&
            absent.every((query) => current.search(query).length === 0)
          )
            return;
          await delay(25);
        }
        if (present)
          assert.notEqual(current.search(present).length, 0, present);
        for (const query of absent)
          assert.equal(current.search(query).length, 0, query);
      };
      const update = async (markdown) => {
        // Chokidar의 같은 파일 이벤트 합치기 간격 밖에서 다음 편집을 전달한다.
        await delay(100);
        await writeFile(source, markdown);
      };
      await expectIndex("Initialuniquesearch");
      await update(
        "# Initialuniquesearch\n\nEdited content.\n\n## Addeduniquesearch\n\nNew content.\n",
      );
      await expectIndex("Addeduniquesearch");
      await update("# Replaceduniquesearch\n\nCurrent content.\n");
      await expectIndex("Replaceduniquesearch", [
        "Initialuniquesearch",
        "Addeduniquesearch",
      ]);
      await update(
        "---\nsearch: false\n---\n# Replaceduniquesearch\n\nHidden from search.\n",
      );
      await expectIndex(null, ["Replaceduniquesearch"]);
      const added = path.join(directory, "added.md");
      await writeFile(added, "# Newfileuniquesearch\n\nNew document.\n");
      await expectIndex("Newfileuniquesearch");
      await rm(added);
      await expectIndex(null, ["Newfileuniquesearch"]);
      await update("# Restoreduniquesearch\n\nVisible again.\n");
      await expectIndex("Restoreduniquesearch");
      // 실제 watcher가 첫 편집을 받은 뒤 느린 renderer가 끝나기 전에 다시 편집한다.
      let onChange;
      const changed = new Promise((resolve) => {
        onChange = (file) => {
          if (file === source) resolve();
        };
        server.watcher.on("change", onChange);
      });
      await update("# Slowuniquesearch\n\nSlow render.\n");
      try {
        await Promise.race([
          changed,
          delay(5000, undefined, { ref: false }).then(() => {
            throw new Error("Markdown change event was not observed");
          }),
        ]);
      } finally {
        server.watcher.off("change", onChange);
      }
      await delay(50);
      await update("# Latestuniquesearch\n\nLatest content.\n");
      await expectIndex("Latestuniquesearch", [
        "Slowuniquesearch",
        "Restoreduniquesearch",
      ]);
      await delay(350);
      await expectIndex("Latestuniquesearch", [
        "Slowuniquesearch",
        "Restoreduniquesearch",
      ]);
      // 같은 ID를 다시 색인해도 이전 내용이 제거되고 duplicate ID 오류가 없다.
      await update(
        "# Latestuniquesearch\n\nChanged body without renaming heading.\n",
      );
      await expectIndex("Changed");
    } finally {
      await server?.close();
      await rm(directory, { recursive: true, force: true });
    }
  },
);
