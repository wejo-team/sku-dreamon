<script setup>
import { computed } from "vue";
import DefaultTheme from "vitepress/theme";
import { useData, withBase } from "vitepress";

const { page, theme } = useData();
const revision = computed(() => theme.value.sourceRevision);
const breadcrumbs = computed(() => {
  const parts = (page.value.filePath ?? "").split("/").filter(Boolean);
  return [
    { text: "docs", link: "/" },
    ...parts.map((text, index) => ({
      text,
      link:
        index < parts.length - 1
          ? `/${parts
              .slice(0, index + 1)
              .map(encodeURIComponent)
              .join("/")}/`
          : undefined,
    })),
  ];
});
const sourceUrl = computed(
  () =>
    `${theme.value.repositoryUrl}/blob/${revision.value ?? "main"}/docs/${page.value.filePath}`,
);
</script>

<template>
  <DefaultTheme.Layout>
    <template #doc-before>
      <nav v-if="page.filePath" class="wejo-breadcrumbs" aria-label="문서 위치">
        <ol>
          <li v-for="item in breadcrumbs" :key="item.text">
            <a v-if="item.link" :href="withBase(item.link)">{{ item.text }}</a>
            <span v-else aria-current="page">{{ item.text }}</span>
          </li>
        </ol>
      </nav>
    </template>
    <template #doc-footer-before>
      <div v-if="page.filePath" class="wejo-source">
        <span>원본</span>
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
        GitHub Wiki에서 보기 <span aria-hidden="true">↗</span>
      </a>
    </template>
  </DefaultTheme.Layout>
</template>
