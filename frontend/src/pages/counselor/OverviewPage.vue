<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import UiCard from "../../components/UiCard.vue";
import { getClusterDistribution, getCounselorDashboard } from "../../api/counselor";
import type { CounselorDashboard, GroupDistributionItem } from "../../types";

const loading = ref(true);
const dash = ref<CounselorDashboard | null>(null);
const clusterMethod = ref<"behavior_kmeans" | "text_topic" | "temporal">("behavior_kmeans");
const clusterRows = ref<GroupDistributionItem[]>([]);

const radarEl = ref<HTMLDivElement | null>(null);
const trendEl = ref<HTMLDivElement | null>(null);
const radarChart = shallowRef<echarts.ECharts | null>(null);
const trendChart = shallowRef<echarts.ECharts | null>(null);

const methodHint = computed(() => {
  switch (clusterMethod.value) {
    case "behavior_kmeans":
      return "基于行为特征向量 K-Means，簇规模反映当前在册学生分布。";
    case "text_topic":
      return "基于文本主题模型，同一学生可能跨主题，人数为加权估算。";
    case "temporal":
      return "基于作息与时间序列特征，用于识别昼夜节律差异群体。";
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
  return p;
}

function setRadar(dist: GroupDistributionItem[]) {
  if (!radarEl.value) return;
  if (!radarChart.value) radarChart.value = echarts.init(radarEl.value);
  const max = Math.max(...dist.map((d) => d.value), 1);
  radarChart.value.setOption({
    tooltip: { trigger: "item" },
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
  setRadar(clusterRows.value);
}

onMounted(async () => {
  loading.value = true;
  try {
    dash.value = await getCounselorDashboard();
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
          <div class="kpi-label">在管学生总数</div>
          <div class="kpi-value">{{ dash.kpis.totalStudents }}</div>
        </UiCard>
        <UiCard class="kpi kpi-warn">
          <div class="kpi-label">预警关注人数</div>
          <div class="kpi-value">{{ dash.kpis.warningStudents }}</div>
        </UiCard>
        <UiCard class="kpi kpi-danger">
          <div class="kpi-label">高风险预警人数</div>
          <div class="kpi-value">{{ dash.kpis.highRiskStudents }}</div>
        </UiCard>
        <UiCard class="kpi">
          <div class="kpi-label">处置中 / 已闭环</div>
          <div class="kpi-value">
            <span class="accent">{{ dash.kpis.inProgressTasks }}</span>
            <span class="sep">/</span>
            <span>{{ dash.kpis.closedTasks }}</span>
          </div>
        </UiCard>
      </section>

      <div class="grid-main">
        <div class="col-center">
          <UiCard title="群体聚类雷达（可切换聚类方式）">
            <div class="cluster-bar">
              <label class="lbl">聚类方式</label>
              <select v-model="clusterMethod" class="sel">
                <option value="behavior_kmeans">行为 K-Means</option>
                <option value="text_topic">文本主题</option>
                <option value="temporal">时间节律</option>
              </select>
            </div>
            <p class="hint-line">{{ methodHint }}</p>
            <div ref="radarEl" class="chart radar-h" />
          </UiCard>

          <UiCard title="近 7 日预警触发趋势（示意）">
            <div ref="trendEl" class="chart trend-h" />
          </UiCard>

          <UiCard title="预警列表">
            <ul class="alert-list">
              <li v-for="a in dash.alerts" :key="a.id" class="alert-item">
                <div class="alert-top">
                  <span class="pill" :class="'r-' + a.risk_level">{{ riskLabel(a.risk_level) }}风险</span>
                  <span class="t-time">{{ a.created_at }}</span>
                </div>
                <div class="t-title">{{ a.title }}</div>
                <p class="t-sum">{{ a.summary }}</p>
              </li>
            </ul>
          </UiCard>
        </div>

        <aside class="col-side">
          <UiCard title="近期热点（多平台抓取示意）">
            <p class="hint-line side-note">展示来源与抓取时间；实际接入需配置采集任务与合规审核。</p>
            <ul class="hot-list">
              <li v-for="h in dash.hot_topics" :key="h.id" class="hot-item">
                <div class="hot-meta">
                  <span class="plat">{{ platformLabel(h.platform) }}</span>
                  <span class="heat">{{ h.heat_label }}</span>
                </div>
                <div class="hot-title">{{ h.title }}</div>
                <div class="hot-time">{{ h.captured_at }}</div>
              </li>
            </ul>
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
.hot-time {
  margin-top: 6px;
  font-size: 11px;
  color: var(--muted);
}
</style>
