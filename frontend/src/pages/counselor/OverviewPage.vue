<script setup lang="ts">
import * as echarts from "echarts";
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import { RouterLink } from "vue-router";
import UiCard from "../../components/UiCard.vue";
import { getClusterDistribution, getCounselorDashboard, getHotTopicsPage } from "../../api/counselor";
import type { CounselorDashboard, GroupDistributionItem, HotTopic } from "../../types";

const loading = ref(true);
const dash = ref<CounselorDashboard | null>(null);
const hotPlatform = ref<"douyin" | "bilibili">("douyin");
const hotRows = ref<HotTopic[]>([]);
const hotTotal = ref(0);
const hotPage = ref(1);
const hotPageSize = ref(10);
const hotTotalPages = ref(1);
const clusterMethod = ref<"behavior_kmeans" | "text_topic">("behavior_kmeans");
const clusterRows = ref<GroupDistributionItem[]>([]);

const radarEl = ref<HTMLDivElement | null>(null);
const trendEl = ref<HTMLDivElement | null>(null);
const radarChart = shallowRef<echarts.ECharts | null>(null);
const trendChart = shallowRef<echarts.ECharts | null>(null);

const methodHint = computed(() => {
  switch (clusterMethod.value) {
    case "behavior_kmeans":
      return "基于数值行为特征进行 K-Means 聚类，反映当前学生群体结构。";
    case "text_topic":
      return "基于文本主题模型进行聚类，同一学生可跨主题，人数为加权估算值。";
    default:
      return "";
  }
});

function riskLabel(level: string) {
  if (level === "high") return "高";
  if (level === "medium") return "中";
  return "低";
}

function platformLabel(p: string) {
  if (p === "weibo") return "微博";
  if (p === "douyin") return "抖音";
  if (p === "xiaohongshu") return "小红书";
  if (p === "bilibili") return "B站";
  return p;
}

function toHeat(v: unknown) {
  if (typeof v !== "number" || Number.isNaN(v)) return "—";
  if (v >= 10000) return `${(v / 10000).toFixed(1)}万`;
  return `${Math.round(v)}`;
}

function setRadar(dist: GroupDistributionItem[]) {
  if (!radarEl.value) return;
  if (!radarChart.value) radarChart.value = echarts.init(radarEl.value);
  const max = Math.max(...dist.map((d) => d.value), 1);
  const labelMetaMap = new Map(
    dist.map((d) => [
      d.name,
      {
        labelDisplay: d.label_display ?? d.name,
        labelCode: d.label_code ?? "-"
      }
    ])
  );
  radarChart.value.setOption({
    tooltip: {
      trigger: "item",
      formatter: (params: unknown) => {
        const p = params as { value?: number[] };
        const values = Array.isArray(p.value) ? p.value : [];
        const lines = dist.map((d, i) => {
          const meta = labelMetaMap.get(d.name);
          const val = values[i] ?? d.value;
          return `${meta?.labelDisplay ?? d.name}（${meta?.labelCode ?? "-"}）：${val}`;
        });
        return lines.join("<br/>");
      }
    },
    radar: {
      indicator: dist.map((d) => ({ name: d.name, max: max * 1.15 })),
      splitArea: { areaStyle: { color: ["rgba(106,169,255,0.06)", "rgba(106,169,255,0.02)"] } }
    },
    series: [
      {
        type: "radar",
        name: "人数",
        data: [{ value: dist.map((d) => d.value), areaStyle: { opacity: 0.22 } }],
        itemStyle: { color: "#6aa9ff" },
        lineStyle: { width: 2 }
      }
    ]
  });
}

function setTrend(d: CounselorDashboard) {
  if (!trendEl.value) return;
  if (!trendChart.value) trendChart.value = echarts.init(trendEl.value);
  trendChart.value.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: 36, right: 12, top: 18, bottom: 28 },
    xAxis: { type: "category", data: d.warningTrend.map((x) => x.day), axisLabel: { color: "#9fb0d0" } },
    yAxis: { type: "value", splitLine: { lineStyle: { color: "#23304a" } }, axisLabel: { color: "#9fb0d0" } },
    series: [
      {
        type: "line",
        smooth: true,
        data: d.warningTrend.map((x) => x.value),
        areaStyle: { color: "rgba(106,169,255,0.15)" },
        lineStyle: { color: "#6aa9ff", width: 2 }
      }
    ]
  });
}

async function loadClusters() {
  clusterRows.value = await getClusterDistribution(clusterMethod.value);
}

async function loadHotTopics() {
  const resp = await getHotTopicsPage({
    platform: hotPlatform.value,
    limit: hotPageSize.value,
    offset: (hotPage.value - 1) * hotPageSize.value
  });
  hotRows.value = resp.items;
  hotTotal.value = resp.total;
  hotTotalPages.value = Math.max(1, Math.ceil(resp.total / hotPageSize.value));
  if (hotPage.value > hotTotalPages.value) {
    hotPage.value = hotTotalPages.value;
    return void loadHotTopics();
  }
}

onMounted(async () => {
  loading.value = true;
  try {
    dash.value = await getCounselorDashboard();
    await loadHotTopics();
    await loadClusters();
    if (dash.value) setTrend(dash.value);
  } finally {
    loading.value = false;
  }
  window.addEventListener("resize", resizeCharts);
});

onUnmounted(() => {
  window.removeEventListener("resize", resizeCharts);
  radarChart.value?.dispose();
  trendChart.value?.dispose();
});

function resizeCharts() {
  radarChart.value?.resize();
  trendChart.value?.resize();
}

watch(clusterMethod, () => {
  void loadClusters();
});

async function tryRenderRadar() {
  if (loading.value) return;
  if (!dash.value) return;
  if (!radarEl.value) return;
  if (!clusterRows.value.length) return;
  await nextTick();
  setRadar(clusterRows.value);
}

async function tryRenderTrend() {
  if (loading.value) return;
  if (!dash.value) return;
  if (!trendEl.value) return;
  await nextTick();
  setTrend(dash.value);
}

watch([loading, () => dash.value, () => radarEl.value, () => clusterRows.value], () => {
  void tryRenderRadar();
});

watch([loading, () => dash.value, () => trendEl.value], () => {
  void tryRenderTrend();
});

watch(hotPlatform, () => {
  hotPage.value = 1;
  void loadHotTopics();
});

watch(hotPage, () => {
  void loadHotTopics();
});

watch(
  () => dash.value,
  (d) => {
    if (d) setTrend(d);
  }
);
</script>

<template>
  <div class="overview">
    <div v-if="loading" class="hint">加载中…</div>
    <template v-else-if="dash">
      <section class="kpi-row">
        <UiCard class="kpi">
          <div class="kpi-label">在册学生总数</div>
          <div class="kpi-value">{{ dash.kpis.totalStudents }}</div>
        </UiCard>
        <UiCard class="kpi kpi-warn">
          <div class="kpi-label">预警关注学生数</div>
          <div class="kpi-value">{{ dash.kpis.warningStudents }}</div>
        </UiCard>
        <UiCard class="kpi kpi-danger">
          <div class="kpi-label">高风险学生数</div>
          <div class="kpi-value">{{ dash.kpis.highRiskStudents }}</div>
        </UiCard>
        <UiCard class="kpi">
          <div class="kpi-label">处理中 / 已闭环</div>
          <div class="kpi-value">
            <span class="accent">{{ dash.kpis.inProgressTasks }}</span>
            <span class="sep">/</span>
            <span>{{ dash.kpis.closedTasks }}</span>
          </div>
        </UiCard>
      </section>

      <div class="grid-main">
        <div class="col-center">
          <UiCard title="群体聚类分布（雷达）">
            <div class="cluster-bar">
              <label class="lbl">聚类方式</label>
              <select v-model="clusterMethod" class="sel">
                <option value="behavior_kmeans">数值特征聚类</option>
                <option value="text_topic">文本主题聚类</option>
              </select>
            </div>
            <p class="hint-line">{{ methodHint }}</p>
            <div ref="radarEl" class="chart radar-h" />
          </UiCard>

          <UiCard title="近 7 日预警触发趋势">
            <div ref="trendEl" class="chart trend-h" />
          </UiCard>

          <UiCard title="待关注预警事件">
            <ul class="alert-list">
              <li v-for="a in dash.alerts" :key="a.id" class="alert-item">
                <div class="alert-top">
                  <span class="pill" :class="'r-' + a.risk_level">{{ riskLabel(a.risk_level) }}风险</span>
                  <span class="t-time">{{ a.created_at }}</span>
                </div>
                <RouterLink class="t-title t-link" :to="`/individuals/${encodeURIComponent(a.student_id)}`">
                  {{ a.student_id }}
                </RouterLink>
                <p class="t-sum">
                  {{ a.class_name }} ·{{ a.numeric_cluster_label }} · {{ a.text_cluster_label }}
                </p>
              </li>
            </ul>
          </UiCard>
        </div>

        <aside class="col-side">
          <UiCard title="近期热点榜单">
            <p class="hint-line side-note">支持平台筛选与分页查看，点击标题可跳转至原始链接。</p>
            <div class="cluster-bar">
              <label class="lbl">平台</label>
              <select v-model="hotPlatform" class="sel">
                <option value="douyin">抖音</option>
                <option value="bilibili">B站</option>
              </select>
            </div>
            <ul class="hot-list">
              <li v-for="h in hotRows" :key="h.id" class="hot-item">
                <div class="hot-meta">
                  <span class="plat">{{ platformLabel(h.platform) }}</span>
                  <span class="heat">{{ h.heat_label }} · 热度 {{ toHeat(h.heat_score) }}</span>
                </div>
                <a class="hot-title hot-link" :href="h.source_url || '#'" target="_blank" rel="noopener noreferrer">
                  {{ h.title }}
                </a>
                <div class="hot-time">{{ h.captured_at }}</div>
              </li>
            </ul>
            <div class="pager">
              <span class="muted">共 {{ hotTotal }} 条，第 {{ hotPage }} / {{ hotTotalPages }} 页</span>
              <div class="pager-btns">
                <button type="button" class="pg-btn" :disabled="hotPage <= 1" @click="hotPage = 1">首页</button>
                <button type="button" class="pg-btn" :disabled="hotPage <= 1" @click="hotPage -= 1">上一页</button>
                <button type="button" class="pg-btn" :disabled="hotPage >= hotTotalPages" @click="hotPage += 1">下一页</button>
                <button type="button" class="pg-btn" :disabled="hotPage >= hotTotalPages" @click="hotPage = hotTotalPages">末页</button>
              </div>
            </div>
          </UiCard>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.overview {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.hint {
  color: var(--muted);
  padding: 24px;
  text-align: center;
}
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}
@media (max-width: 1024px) {
  .kpi-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
.kpi {
  min-height: 88px;
}
.kpi-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.kpi-value {
  font-size: 26px;
  font-weight: 700;
  letter-spacing: 0.5px;
}
.kpi-warn .kpi-value {
  color: #ffc266;
}
.kpi-danger .kpi-value {
  color: var(--danger);
}
.accent {
  color: var(--accent);
}
.sep {
  margin: 0 6px;
  color: var(--muted);
  font-weight: 500;
}
.grid-main {
  display: grid;
  grid-template-columns: 1fr minmax(260px, 300px);
  gap: 14px;
  align-items: start;
}
@media (max-width: 1100px) {
  .grid-main {
    grid-template-columns: 1fr;
  }
}
.col-center {
  display: flex;
  flex-direction: column;
  gap: 14px;
  min-width: 0;
}
.col-side {
  position: sticky;
  top: 12px;
}
.cluster-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.lbl {
  font-size: 12px;
  color: var(--muted);
}
.sel {
  flex: 1;
  max-width: 220px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-size: 13px;
}
.hint-line {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.side-note {
  margin-bottom: 12px;
}
.chart {
  width: 100%;
}
.radar-h {
  height: 320px;
}
.trend-h {
  height: 220px;
}
.alert-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.alert-item {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(12, 20, 38, 0.5);
}
.alert-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--muted);
}
.pill.r-high {
  border-color: rgba(255, 138, 138, 0.55);
  color: #ffb4b4;
}
.pill.r-medium {
  border-color: rgba(255, 194, 102, 0.5);
  color: #ffd49a;
}
.pill.r-low {
  border-color: rgba(106, 169, 255, 0.45);
  color: #cfe4ff;
}
.t-time {
  font-size: 11px;
  color: var(--muted);
}
.t-title {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}
.t-link {
  color: var(--text);
  text-decoration: none;
}
.t-link:hover {
  text-decoration: underline;
}
.t-sum {
  margin: 0;
  font-size: 13px;
  color: var(--muted);
  line-height: 1.5;
}
.hot-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hot-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.hot-group {
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 8px 10px;
}
.g-title {
  font-size: 12px;
  color: var(--accent);
  margin-bottom: 6px;
}
.hot-item {
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.hot-item:last-child {
  border-bottom: none;
}
.hot-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--muted);
  margin-bottom: 4px;
}
.plat {
  color: var(--accent);
}
.hot-title {
  font-size: 13px;
  line-height: 1.45;
}
.hot-link {
  color: inherit;
  text-decoration: none;
}
.hot-link:hover {
  text-decoration: underline;
}
.hot-time {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
}
.pager {
  margin-top: 10px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}
.pager-btns {
  display: flex;
  gap: 6px;
}
.pg-btn {
  padding: 5px 9px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  cursor: pointer;
}
.pg-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
