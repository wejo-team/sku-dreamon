<script setup>
import { computed } from "vue";
import DefaultTheme from "vitepress/theme";
import { useData, withBase } from "vitepress";

const { page, theme } = useData();
const isIndex = computed(() => page.value.relativePath === "index.md");
const revision = computed(() => theme.value.sourceRevision);
const sourceUrl = computed(
  () =>
    `${theme.value.repositoryUrl}/blob/${revision.value ?? "main"}/docs/${page.value.filePath}`,
);
</script>

<template>
  <DefaultTheme.Layout>
    <template #doc-before>
      <section
        v-if="isIndex"
        class="wejo-intro"
        aria-label="WEJO 팀 문서 시작하기"
      >
        <div class="wejo-intro-copy">
          <p class="wejo-eyebrow">WEJO / TEAM HANDBOOK</p>
          <p class="wejo-intro-title">함께 만들고,<br />같은 기준으로.</p>
          <p class="wejo-intro-description">
            기능의 약속부터 개발의 기준까지.<br />지금 필요한 문서에서
            시작하세요.
          </p>
          <a
            class="wejo-start"
            :href="withBase('/development/local-development.html')"
          >
            로컬에서 시작하기 <span aria-hidden="true">↗</span>
          </a>
        </div>
        <div class="wejo-intro-art" aria-hidden="true">
          <div class="wejo-orbit"></div>
          <div class="wejo-paper wejo-paper-back"></div>
          <div class="wejo-paper wejo-paper-front">
            <span class="wejo-paper-mark">w.</span>
            <span class="wejo-paper-line"></span>
            <span class="wejo-paper-line wejo-paper-line-short"></span>
            <span class="wejo-paper-check">✓</span>
          </div>
          <span class="wejo-art-caption">BUILD TOGETHER</span>
        </div>
      </section>
    </template>
    <template #doc-footer-before>
      <div class="wejo-source">
        <span class="wejo-source-label">문서 원본</span>
        <a :href="sourceUrl" target="_blank" rel="noreferrer"
          >docs/{{ page.filePath }}</a
        >
        <a
          v-if="revision"
          class="wejo-revision"
          :href="`${theme.repositoryUrl}/commit/${revision}`"
          target="_blank"
          rel="noreferrer"
          aria-label="이 사이트의 소스 커밋"
          >{{ revision.slice(0, 7) }}</a
        >
      </div>
    </template>
    <template #sidebar-nav-after>
      <a
        class="wejo-wiki-link"
        :href="`${theme.repositoryUrl}/wiki`"
        target="_blank"
        rel="noreferrer"
      >
        GitHub Wiki에서도 보기 <span aria-hidden="true">↗</span>
      </a>
    </template>
  </DefaultTheme.Layout>
</template>
