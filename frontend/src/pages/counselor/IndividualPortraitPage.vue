<script setup lang="ts">
import * as echarts from "echarts";
import "echarts-wordcloud";
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import UiCard from "../../components/UiCard.vue";
import { getStudentProfileDetail, getTalkingAssistantDraftStream, saveInterventionRecord } from "../../api/counselor";
import type { StudentProfileDetail } from "../../types";

const route = useRoute();
const router = useRouter();
const studentId = computed(() => String(route.params.studentId || ""));

const profile = ref<StudentProfileDetail | null>(null);
const loading = ref(true);
const aiLoading = ref(false);
const aiLines = ref<string[]>([]);
const aiStreamText = ref("");
const aiError = ref("");
const handlingStatus = ref<"processing" | "resolved" | "ignored">("processing");
const handlingNote = ref("");
const handlingSaving = ref(false);
const handlingMsg = ref("");

const cloudEl = ref<HTMLDivElement | null>(null);
const cloudChart = shallowRef<echarts.ECharts | null>(null);

const cloudData = computed(() => {
  const p = profile.value;
  if (!p) return [];
  const map = new Map<string, number>();

  const add = (terms: string[], w: number) => {
    for (const t of terms) {
      const key = (t || "").trim();
      if (!key) continue;
      map.set(key, (map.get(key) ?? 0) + w);
    }
  };

  add(p.basic_tags ?? [], 12);
  add(p.behavior_tags ?? [], 12);
  add(p.cognitive_tags ?? [], 12);
  add(p.content_keywords ?? [], 7);

  return [...map.entries()].map(([name, value]) => ({ name, value }));
});

function renderWordCloud() {
  if (!cloudEl.value) return;
  if (!cloudChart.value) cloudChart.value = echarts.init(cloudEl.value);
  cloudChart.value.setOption({
    tooltip: { show: true },
    series: [
      {
        type: "wordCloud",
        shape: "circle",
        width: "100%",
        height: "100%",
        sizeRange: [14, 44],
        rotationRange: [-35, 35],
        gridSize: 8,
        drawOutOfBound: false,
        textStyle: {
          color: () => {
            const palette = ["#6aa9ff", "#8fc5ff", "#c49bff", "#6fe0c3", "#ffc266"];
            return palette[Math.floor(Math.random() * palette.length)];
          }
        },
        emphasis: { textStyle: { shadowBlur: 10, shadowColor: "#000" } },
        data: cloudData.value
      }
    ]
  });
}

onMounted(async () => {
  loading.value = true;
  try {
    profile.value = await getStudentProfileDetail(studentId.value);
  } finally {
    loading.value = false;
  }
  await nextTick();
  renderWordCloud();
});

watch(cloudData, async () => {
  await nextTick();
  renderWordCloud();
});

onUnmounted(() => {
  cloudChart.value?.dispose();
});

async function runAssistant() {
  aiLoading.value = true;
  aiError.value = "";
  aiLines.value = [];
  aiStreamText.value = "";
  try {
    aiLines.value = await getTalkingAssistantDraftStream(
      studentId.value,
      (chunk) => {
        aiStreamText.value += chunk;
      },
      (message) => {
        aiError.value = message;
      }
    );
  } finally {
    aiLoading.value = false;
  }
}

function warningStatusText(s?: string | null) {
  if (s === "resolved") return "已闭环";
  if (s === "processing") return "处理中";
  if (s === "ignored") return "已忽略";
  return "待处理";
}

async function submitHandling() {
  if (!profile.value) return;
  handlingSaving.value = true;
  handlingMsg.value = "";
  try {
    await saveInterventionRecord({
      studentId: profile.value.student_id,
      actionType: handlingStatus.value === "resolved" ? "closed" : handlingStatus.value === "ignored" ? "ignored" : "followup",
      record: handlingNote.value.trim() || "已登记处理。"
    });
    profile.value = await getStudentProfileDetail(studentId.value);
    handlingMsg.value = "处理结果已保存";
  } catch {
    handlingMsg.value = "保存失败，请稍后重试";
  } finally {
    handlingSaving.value = false;
  }
}
</script>

<template>
  <div class="page">
    <button type="button" class="back" @click="router.push('/individuals')">← 返回个体列表</button>

    <div v-if="loading" class="hint">画像数据加载中…</div>
    <template v-else-if="profile">
      <div class="grid">
        <div class="main">
          <UiCard :title="`学生 ${profile.student_id}`">
            <div class="sub">最近计算时间：{{ profile.last_computed_at ?? "—" }}</div>
            <div class="sub">预警分：{{ profile.warning_score ?? "—" }} · 处置状态：{{ warningStatusText(profile.warning_status) }}</div>
            <div v-if="profile.intervention_action" class="action">
              <div class="lbl">系统建议摘要（仅供参考）</div>
              <p>{{ profile.intervention_action }}</p>
            </div>
            <div class="action">
              <div class="lbl">预警处置登记</div>
              <div class="row">
                <select v-model="handlingStatus" class="sel">
                  <option value="processing">处理中</option>
                  <option value="resolved">已闭环</option>
                  <option value="ignored">暂不处理</option>
                </select>
              </div>
              <textarea v-model="handlingNote" class="ta" rows="3" placeholder="填写处置记录（面谈、转介、跟进计划等）" />
              <div class="row">
                <button type="button" class="btn mini" :disabled="handlingSaving" @click="submitHandling">
                  {{ handlingSaving ? "保存中…" : "保存处置结果" }}
                </button>
                <span class="hint-inline">{{ handlingMsg }}</span>
              </div>
            </div>
          </UiCard>

          <UiCard title="关键词词云（文本与画像标签）">
            <p class="note">词云由学生文本关键词与画像标签加权生成，用于辅助快速研判。</p>
            <div ref="cloudEl" class="cloud" />
          </UiCard>
        </div>

        <aside class="side">
          <UiCard title="AI 谈话建议">
            <p class="note">根据画像生成谈话提纲，输出结果需辅导员人工复核后使用。</p>
            <button type="button" class="btn" :disabled="aiLoading" @click="runAssistant">
              {{ aiLoading ? "生成中…" : "生成谈话建议" }}
            </button>
            <p v-if="aiError" class="warn">模型调用异常，已切换兜底：{{ aiError }}</p>
            <p v-if="aiLoading && aiStreamText" class="stream">{{ aiStreamText }}</p>
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
  width: 100%;
  height: 360px;
}
.note {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.warn {
  margin: 10px 0 0;
  color: #ffb3b3;
  font-size: 12px;
}
.stream {
  margin: 10px 0 0;
  color: var(--text);
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
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
.btn.mini {
  width: auto;
  padding: 8px 12px;
  font-size: 13px;
}
.row {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-top: 8px;
}
.sel {
  min-width: 160px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-size: 13px;
}
.ta {
  margin-top: 8px;
  width: 100%;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  padding: 8px 10px;
  resize: vertical;
}
.hint-inline {
  color: var(--muted);
  font-size: 12px;
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
