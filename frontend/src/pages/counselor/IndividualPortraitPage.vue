<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import UiCard from "../../components/UiCard.vue";
import { getStudentProfileDetail, getTalkingAssistantDraft } from "../../api/counselor";
import type { StudentProfileDetail } from "../../types";

const route = useRoute();
const router = useRouter();
const studentId = computed(() => String(route.params.studentId || ""));

const profile = ref<StudentProfileDetail | null>(null);
const loading = ref(true);
const aiLoading = ref(false);
const aiLines = ref<string[]>([]);

const tagCloud = computed(() => {
  const p = profile.value;
  if (!p) return [];
  const parts: { text: string; w: number }[] = [];
  let w = 22;
  for (const t of p.basic_tags ?? []) parts.push({ text: t, w: w-- });
  for (const t of p.behavior_tags ?? []) parts.push({ text: t, w: w-- });
  for (const t of p.cognitive_tags ?? []) parts.push({ text: t, w: w-- });
  return parts.sort((a, b) => b.w - a.w);
});

onMounted(async () => {
  loading.value = true;
  try {
    profile.value = await getStudentProfileDetail(studentId.value);
  } finally {
    loading.value = false;
  }
});

async function runAssistant() {
  aiLoading.value = true;
  try {
    aiLines.value = await getTalkingAssistantDraft(studentId.value);
  } finally {
    aiLoading.value = false;
  }
}
</script>

<template>
  <div class="page">
    <button type="button" class="back" @click="router.push('/individuals')">← 返回列表</button>

    <div v-if="loading" class="hint">加载画像…</div>
    <template v-else-if="profile">
      <div class="grid">
        <div class="main">
          <UiCard :title="`学生 ${profile.student_id}`">
            <div class="sub">最近计算：{{ profile.last_computed_at ?? "—" }}</div>
            <div v-if="profile.intervention_action" class="action">
              <div class="lbl">系统建议摘要</div>
              <p>{{ profile.intervention_action }}</p>
            </div>
          </UiCard>

          <UiCard title="标签云">
            <div class="cloud">
              <span
                v-for="(item, i) in tagCloud"
                :key="item.text + i"
                class="tag"
                :style="{ fontSize: 12 + Math.min(16, item.w) + 'px' }"
              >
                {{ item.text }}
              </span>
            </div>
          </UiCard>
        </div>

        <aside class="side">
          <UiCard title="AI 谈话助手（占位）">
            <p class="note">根据画像生成谈话提纲；正式环境需接入模型并加人工审核。</p>
            <button type="button" class="btn" :disabled="aiLoading" @click="runAssistant">
              {{ aiLoading ? "生成中…" : "生成针对性意见" }}
            </button>
            <ol v-if="aiLines.length" class="ai-out">
              <li v-for="(line, i) in aiLines" :key="i">{{ line }}</li>
            </ol>
          </UiCard>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.back {
  align-self: flex-start;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #101a30;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
}
.hint {
  color: var(--muted);
  padding: 20px;
}
.grid {
  display: grid;
  grid-template-columns: 1fr minmax(280px, 340px);
  gap: 14px;
  align-items: start;
}
@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.sub {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 10px;
}
.action {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid rgba(106, 169, 255, 0.35);
  background: rgba(106, 169, 255, 0.08);
}
.action .lbl {
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 6px;
}
.action p {
  margin: 0;
  font-size: 14px;
  line-height: 1.55;
}
.cloud {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 12px;
  align-items: center;
}
.tag {
  color: #cfe4ff;
  font-weight: 600;
}
.note {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.btn {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid rgba(106, 169, 255, 0.45);
  background: linear-gradient(180deg, #2a65ff, #1c49b6);
  color: #fff;
  font-size: 14px;
  cursor: pointer;
}
.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.ai-out {
  margin: 14px 0 0;
  padding-left: 18px;
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
}
.side {
  position: sticky;
  top: 8px;
}
</style>
