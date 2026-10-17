import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vitepress";
import { siteLink } from "./links.mjs";
import { createSidebar } from "./navigation.mjs";

const repositoryUrl = "https://github.com/wejo-team/sku-dreamon";
const base = "/sku-dreamon/";

function sourceRevision() {
  const sha = process.env.GITHUB_SHA;
  if (sha && /^[a-f\d]{40}$/i.test(sha)) return sha;
  try {
    return execFileSync("git", ["rev-parse", "HEAD"], {
      encoding: "utf8",
    }).trim();
  } catch {
    return undefined;
  }
}

const revision = sourceRevision();

export default defineConfig({
  lang: "ko-KR",
  title: "서경드림온 문서",
  description:
    "공모전으로 학생들의 꿈과 잠재력을 밝히고 도전을 이어가는 서경드림온의 기능 명세와 개발 가이드입니다.",
  base,
  cleanUrls: false,
  lastUpdated: true,
  head: [
    ["meta", { name: "theme-color", content: "#087f72" }],
  ],
  rewrites: (file) => file.replace(/(^|\/)README\.md$/, "$1index.md"),
  markdown: {
    config(md) {
      const renderLink = md.renderer.rules.link_open;
      md.renderer.rules.link_open = (tokens, index, options, env, renderer) => {
        const token = tokens[index];
        const href = token.attrGet("href");
        if (href) {
          token.attrSet(
            "href",
            siteLink(href, env.relativePath, repositoryUrl, revision ?? "main"),
          );
        }
        return renderLink(tokens, index, options, env, renderer);
      };
    },
  },
  themeConfig: {
    siteTitle: "서경드림온 문서",
    nav: [{ text: "문서 인덱스", link: "/", activeMatch: "^/(?:index)?$" }],
    sidebar: createSidebar(fileURLToPath(new URL("../", import.meta.url))),
    socialLinks: [
      { icon: "github", link: repositoryUrl, ariaLabel: "서경드림온 GitHub 저장소" },
    ],
    search: {
      provider: "local",
      options: {
        locales: {
          root: {
            translations: {
              button: { buttonText: "문서 검색", buttonAriaLabel: "문서 검색" },
              modal: {
                displayDetails: "상세 내용 표시",
                resetButtonTitle: "검색어 지우기",
                backButtonTitle: "검색 닫기",
                noResultsText: "검색 결과가 없습니다",
                footer: {
                  selectText: "선택",
                  selectKeyAriaLabel: "Enter",
                  navigateText: "이동",
                  navigateUpKeyAriaLabel: "위쪽 화살표",
                  navigateDownKeyAriaLabel: "아래쪽 화살표",
                  closeText: "닫기",
                  closeKeyAriaLabel: "Escape",
                },
              },
            },
          },
        },
      },
    },
    editLink: {
      pattern: `${repositoryUrl}/edit/main/docs/:path`,
      text: "GitHub에서 수정 제안",
    },
    lastUpdated: {
      text: "문서 수정",
      formatOptions: {
        dateStyle: "medium",
        timeStyle: "short",
        timeZone: "Asia/Seoul",
      },
    },
    outline: { label: "이 페이지에서", level: [2, 3] },
    docFooter: { prev: "이전 문서", next: "다음 문서" },
    sidebarMenuLabel: "문서 목록",
    returnToTopLabel: "맨 위로",
    darkModeSwitchLabel: "테마",
    lightModeSwitchTitle: "밝은 테마로 전환",
    darkModeSwitchTitle: "어두운 테마로 전환",
    skipToContentLabel: "본문으로 건너뛰기",
    notFound: {
      code: "404",
      title: "문서를 찾을 수 없어요",
      quote: "문서 인덱스에서 필요한 내용을 다시 찾아보세요.",
      linkLabel: "문서 인덱스로 이동",
      linkText: "문서 인덱스로",
    },
    sourceRevision: revision,
    repositoryUrl,
  },
});
