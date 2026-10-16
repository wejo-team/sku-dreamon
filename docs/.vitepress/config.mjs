import { execFileSync } from "node:child_process";
import { defineConfig } from "vitepress";
import { siteLink } from "./links.mjs";

const repositoryUrl = "https://github.com/wejo-team/wejo-app";
const base = "/wejo-app/";

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
  title: "WEJO Docs",
  description:
    "WEJO 팀의 기능 명세와 개발 가이드. 필요한 문서부터, 같은 기준으로 함께 만듭니다.",
  base,
  cleanUrls: false,
  lastUpdated: true,
  head: [
    [
      "link",
      { rel: "icon", type: "image/svg+xml", href: `${base}wejo-mark.svg` },
    ],
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
    logo: { src: "/wejo-mark.svg", alt: "" },
    siteTitle: "WEJO Docs",
    nav: [
      { text: "시작하기", link: "/", activeMatch: "^/(?:index)?$" },
      {
        text: "개발 가이드",
        link: "/development/",
        activeMatch: "^/development/",
      },
      { text: "기능 명세", link: "/specs/", activeMatch: "^/specs/" },
      { text: "템플릿", link: "/templates/", activeMatch: "^/templates/" },
    ],
    sidebar: [
      {
        text: "먼저 읽기",
        items: [
          { text: "문서 인덱스", link: "/" },
          { text: "로컬 실행", link: "/development/local-development" },
          { text: "팀 작업 흐름", link: "/development/workflow" },
          { text: "에이전트 안내", link: "/agent-guide" },
        ],
      },
      {
        text: "개발 가이드",
        collapsed: false,
        items: [
          { text: "개발 인덱스", link: "/development/" },
          { text: "구조와 스캐폴딩", link: "/development/architecture" },
          { text: "작성·Git 컨벤션", link: "/development/conventions" },
          { text: "프론트엔드", link: "/development/frontend" },
          { text: "백엔드·비동기 DB", link: "/development/backend" },
          { text: "테스트·CI", link: "/development/testing" },
          { text: "문서 관리", link: "/development/documentation" },
        ],
      },
      {
        text: "명세와 템플릿",
        items: [
          { text: "기능 명세 인덱스", link: "/specs/" },
          { text: "템플릿 인덱스", link: "/templates/" },
          { text: "기능 명세 템플릿", link: "/templates/spec" },
        ],
      },
    ],
    socialLinks: [
      { icon: "github", link: repositoryUrl, ariaLabel: "WEJO GitHub 저장소" },
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
