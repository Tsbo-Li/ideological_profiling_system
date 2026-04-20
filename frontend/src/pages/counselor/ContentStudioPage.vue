<script setup lang="ts">
import { onMounted, ref } from "vue";
import UiCard from "../../components/UiCard.vue";
import { getRecentContentSuggestions } from "../../api/counselor";
import type { ContentOutputSuggestion } from "../../types";

const loading = ref(true);
const drafts = ref<ContentOutputSuggestion[]>([]);
const videoScript = ref(
  "【视频口播 · 占位】结合近期「春招焦虑」热点与班级「夜间高活跃」预警：\n" +
    "1）开场共情 20s；2）三个可执行微习惯各 25s；3）收口引导至学院官方渠道。\n" +
    "实际生成将调用模型并引用热点与预警主题字段。"
);

onMounted(async () => {
  loading.value = true;
  try {
    drafts.value = await getRecentContentSuggestions();
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="page">
    <UiCard title="公众号 / 班会长文草稿">
      <p class="lead">结合近期热点与预警主题的成稿建议（占位数据）。</p>
      <div v-if="loading" class="hint">加载中…</div>
      <div v-else class="drafts">
        <article v-for="d in drafts" :key="d.id" class="draft">
          <header class="dh">
            <h2>{{ d.title }}</h2>
            <span class="meta">{{ d.updatedAt }} · {{ d.tone }}</span>
          </header>
          <p class="aud">{{ d.audienceHint }}</p>
          <ol>
            <li v-for="(line, i) in d.outline" :key="i">{{ line }}</li>
          </ol>
          <ul v-if="d.disclaimers?.length" class="dis">
            <li v-for="(x, i) in d.disclaimers" :key="i">{{ x }}</li>
          </ul>
        </article>
      </div>
    </UiCard>

    <UiCard title="短视频脚本与分镜（可编辑占位）">
      <textarea v-model="videoScript" class="ta" rows="12" spellcheck="false" />
      <p class="hint">后续可对接：热点关键词 + 预警摘要 → 自动分镜 + 口播稿。</p>
    </UiCard>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 960px;
}
.lead {
  margin: 0 0 12px;
  font-size: 13px;
  color: var(--muted);
}
.hint {
  color: var(--muted);
}
.drafts {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.draft {
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(12, 20, 38, 0.45);
}
.dh h2 {
  margin: 0 0 6px;
  font-size: 16px;
}
.meta {
  font-size: 12px;
  color: var(--muted);
}
.aud {
  font-size: 13px;
  color: #cfe4ff;
  margin: 10px 0;
}
.draft ol {
  margin: 0;
  padding-left: 18px;
  color: var(--muted);
  line-height: 1.55;
  font-size: 13px;
}
.dis {
  margin: 12px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: #ffc266;
}
.ta {
  width: 100%;
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
}
.ta + .hint {
  margin-top: 10px;
  font-size: 12px;
}
</style>
