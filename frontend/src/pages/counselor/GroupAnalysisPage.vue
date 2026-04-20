<script setup lang="ts">
import * as echarts from "echarts";
import { computed, onMounted, onUnmounted, ref, shallowRef } from "vue";
import UiCard from "../../components/UiCard.vue";
import { getCounselorGroups } from "../../api/counselor";
import type { GroupPortrait } from "../../types";

const groups = ref<GroupPortrait[]>([]);
const loading = ref(true);
const scatterEl = ref<HTMLDivElement | null>(null);
const chart = shallowRef<echarts.ECharts | null>(null);

const wordWeights = computed(() => {
  const map = new Map<string, number>();
  for (const g of groups.value) {
    const w = Math.max(1, Math.round(Math.sqrt(g.size)));
    for (const t of g.representative_behavior_tags ?? []) {
      map.set(t, (map.get(t) ?? 0) + w);
    }
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
});

function buildScatterData(gs: GroupPortrait[]) {
  const colors = ["#6aa9ff", "#ffc266", "#c49bff", "#6fe0c3", "#ff8a8a"];
  const series = gs.map((g, idx) => {
    const n = Math.min(40, Math.max(8, Math.floor(g.size / 6)));
    const data: [number, number, string][] = [];
    const cx = (idx % 3) * 3.2 - 3.2;
    const cy = Math.floor(idx / 3) * 2.6 - 1.2;
    for (let i = 0; i < n; i++) {
      const rx = (Math.random() - 0.5) * 1.8;
      const ry = (Math.random() - 0.5) * 1.4;
      data.push([cx + rx, cy + ry, g.name]);
    }
    return {
      name: g.name,
      type: "scatter" as const,
      symbolSize: 10,
      itemStyle: { color: colors[idx % colors.length], opacity: 0.78 },
      data
    };
  });
  return series;
}

function renderScatter(gs: GroupPortrait[]) {
  if (!scatterEl.value) return;
  if (!chart.value) chart.value = echarts.init(scatterEl.value);
  chart.value.setOption({
    tooltip: {
      formatter: (p: unknown) => {
        const param = p as { value?: [number, number, string] };
        const v = param.value;
        if (!v) return "";
        return `${v[2]}<br/>示意坐标：行为降维投影`;
      }
    },
    grid: { left: 48, right: 24, top: 24, bottom: 40 },
    xAxis: {
      name: "维度 1（示意）",
      nameTextStyle: { color: "#9fb0d0", fontSize: 11 },
      splitLine: { lineStyle: { color: "#23304a" } },
      axisLabel: { color: "#9fb0d0" }
    },
    yAxis: {
      name: "维度 2（示意）",
      nameTextStyle: { color: "#9fb0d0", fontSize: 11 },
      splitLine: { lineStyle: { color: "#23304a" } },
      axisLabel: { color: "#9fb0d0" }
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#9fb0d0", fontSize: 11 },
      type: "scroll"
    },
    series: buildScatterData(gs)
  });
}

onMounted(async () => {
  loading.value = true;
  try {
    groups.value = await getCounselorGroups();
    renderScatter(groups.value);
  } finally {
    loading.value = false;
  }
  window.addEventListener("resize", () => chart.value?.resize());
});

onUnmounted(() => {
  chart.value?.dispose();
});
</script>

<template>
  <div class="page">
    <div v-if="loading" class="hint">加载中…</div>
    <template v-else>
      <div class="grid">
        <UiCard title="学生二维行为分布（降维投影示意）">
          <p class="note">实际接入时用 UMAP / t-SNE 等将多维行为映射到平面；悬停可看所属群体名称。</p>
          <div ref="scatterEl" class="chart" />
        </UiCard>
        <UiCard title="群体词云（由代表行为标签加权合成）">
          <p class="note">词频与群体规模、代表标签共现相关；后续可换真实词云渲染引擎。</p>
          <div class="cloud">
            <span
              v-for="([w, c], i) in wordWeights"
              :key="w"
              class="w"
              :style="{ fontSize: 12 + Math.min(22, c) + 'px', opacity: 0.45 + i / (wordWeights.length + 4) }"
            >
              {{ w }}
            </span>
            <span v-if="!wordWeights.length" class="hint">暂无标签</span>
          </div>
        </UiCard>
      </div>
      <UiCard title="群体卡片">
        <div class="cards">
          <div v-for="g in groups" :key="g.name" class="gcard">
            <div class="gname">{{ g.name }}</div>
            <div class="gmeta">规模 {{ g.size }} · 示例学号 {{ g.topStudent }}</div>
            <div class="tags">
              <span v-for="t in g.representative_behavior_tags ?? []" :key="t" class="tag">{{ t }}</span>
            </div>
          </div>
        </div>
      </UiCard>
    </template>
  </div>
</template>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.hint {
  color: var(--muted);
  padding: 20px;
}
.grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr;
  gap: 14px;
  align-items: stretch;
}
@media (max-width: 960px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
.note {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  line-height: 1.45;
}
.chart {
  width: 100%;
  height: 400px;
}
.cloud {
  min-height: 200px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 14px;
  align-items: center;
  padding: 8px 4px;
}
.w {
  color: var(--accent);
  font-weight: 600;
  line-height: 1.2;
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.gcard {
  padding: 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: rgba(12, 20, 38, 0.45);
}
.gname {
  font-weight: 650;
  margin-bottom: 6px;
}
.gmeta {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  font-size: 11px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
  color: var(--muted);
}
</style>
