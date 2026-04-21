<script setup lang="ts">
import * as echarts from "echarts";
import * as THREE from "three";
import { CSS2DObject, CSS2DRenderer } from "three/examples/jsm/renderers/CSS2DRenderer.js";
import { computed, nextTick, onMounted, onUnmounted, ref, shallowRef, watch } from "vue";
import { useRouter } from "vue-router";
import UiCard from "../../components/UiCard.vue";
import { getCounselorGroups, getCounselorScatter, type ScatterMethod } from "../../api/counselor";
import type { CounselorScatterPoint, GroupPortrait } from "../../types";

const router = useRouter();

const groups = ref<GroupPortrait[]>([]);
const groupMethod = ref<"numeric" | "text">("numeric");
const scatterPoints = ref<CounselorScatterPoint[]>([]);
const scatterMethod = ref<ScatterMethod>("numeric");
const loading = ref(true);
const scatterEl = ref<HTMLDivElement | null>(null);
const cloudEl = ref<HTMLDivElement | null>(null);
const chart = shallowRef<echarts.ECharts | null>(null);

const cloudScene = shallowRef<THREE.Scene | null>(null);
const cloudCamera = shallowRef<THREE.PerspectiveCamera | null>(null);
const cloudRenderer = shallowRef<THREE.WebGLRenderer | null>(null);
const cloudLabelRenderer = shallowRef<CSS2DRenderer | null>(null);
const cloudAnimationId = shallowRef<number | null>(null);
const cloudGroup = shallowRef<THREE.Group | null>(null);
const cloudAutoRotate = ref(true);
const cloudRotateSpeed = ref(1);
const cloudZoom = ref(1);

const isDraggingCloud = ref(false);
const lastCloudPos = ref<{ x: number; y: number } | null>(null);

const wordWeights = computed(() => {
  const map = new Map<string, number>();
  for (const g of groups.value) {
    const w = Math.max(1, Math.round(Math.sqrt(g.size)));
    const tags = (g.representative_text_tags?.length ? g.representative_text_tags : g.representative_behavior_tags) ?? [];
    for (const t of tags) {
      map.set(t, (map.get(t) ?? 0) + w);
    }
  }
  return [...map.entries()].sort((a, b) => b[1] - a[1]);
});

function disposeCloud3D() {
  if (cloudAnimationId.value != null) {
    cancelAnimationFrame(cloudAnimationId.value);
    cloudAnimationId.value = null;
  }
  cloudRenderer.value?.dispose();
  if (cloudRenderer.value?.domElement?.parentElement) cloudRenderer.value.domElement.parentElement.removeChild(cloudRenderer.value.domElement);
  if (cloudLabelRenderer.value?.domElement?.parentElement) cloudLabelRenderer.value.domElement.parentElement.removeChild(cloudLabelRenderer.value.domElement);

  cloudScene.value = null;
  cloudCamera.value = null;
  cloudRenderer.value = null;
  cloudLabelRenderer.value = null;
  cloudGroup.value = null;
  isDraggingCloud.value = false;
  lastCloudPos.value = null;
}

function renderWordCloud3D() {
  if (!cloudEl.value) return;
  disposeCloud3D();

  const container = cloudEl.value;
  container.style.touchAction = "none";
  const w = container.clientWidth || 400;
  const h = container.clientHeight || 400;

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, w / h, 0.1, 1000);
  camera.position.set(0, 0, 160 / Math.max(0.2, cloudZoom.value));

  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(w, h);
  renderer.setClearColor(0x000000, 0);

  const labelRenderer = new CSS2DRenderer();
  labelRenderer.setSize(w, h);
  labelRenderer.domElement.style.position = "absolute";
  labelRenderer.domElement.style.top = "0";
  labelRenderer.domElement.style.left = "0";
  labelRenderer.domElement.style.pointerEvents = "none";

  container.style.position = "relative";
  container.appendChild(renderer.domElement);
  container.appendChild(labelRenderer.domElement);

  const group = new THREE.Group();
  scene.add(group);

  const words = wordWeights.value.slice(0, 80); // cap for performance
  const values = words.map(([, v]) => v);
  const maxV = Math.max(...values, 1);
  const minV = Math.min(...values, 1);
  const radius = 70;
  const palette = ["#6aa9ff", "#8fc5ff", "#c49bff", "#6fe0c3", "#ffc266"];

  // Fibonacci sphere distribution
  for (let i = 0; i < words.length; i++) {
    const [text, val] = words[i];
    const t = (val - minV) / Math.max(1e-6, maxV - minV);
    const fontSize = Math.round(12 + t * 18);

    const phi = Math.acos(1 - (2 * (i + 0.5)) / words.length);
    const theta = Math.PI * (1 + Math.sqrt(5)) * (i + 0.5);
    const x = radius * Math.sin(phi) * Math.cos(theta);
    const y = radius * Math.sin(phi) * Math.sin(theta);
    const z = radius * Math.cos(phi);

    const el = document.createElement("div");
    el.textContent = text;
    el.style.fontSize = `${fontSize}px`;
    el.style.fontWeight = "650";
    el.style.whiteSpace = "nowrap";
    el.style.color = palette[i % palette.length];
    el.style.textShadow = "0 2px 10px rgba(0,0,0,0.35)";
    el.style.opacity = "0.92";

    const label = new CSS2DObject(el);
    label.position.set(x, y, z);
    group.add(label as unknown as THREE.Object3D);
  }

  const ambient = new THREE.AmbientLight(0xffffff, 1.0);
  scene.add(ambient);

  function onPointerDown(ev: PointerEvent) {
    isDraggingCloud.value = true;
    lastCloudPos.value = { x: ev.clientX, y: ev.clientY };
    container.setPointerCapture(ev.pointerId);
  }
  function onPointerMove(ev: PointerEvent) {
    if (!isDraggingCloud.value || !lastCloudPos.value) return;
    const dx = ev.clientX - lastCloudPos.value.x;
    const dy = ev.clientY - lastCloudPos.value.y;
    lastCloudPos.value = { x: ev.clientX, y: ev.clientY };

    // drag rotates: dx -> y axis, dy -> x axis
    group.rotation.y += dx * 0.005;
    group.rotation.x += dy * 0.005;
  }
  function onPointerUp(ev: PointerEvent) {
    isDraggingCloud.value = false;
    lastCloudPos.value = null;
    try {
      container.releasePointerCapture(ev.pointerId);
    } catch {
      // ignore
    }
  }
  function onWheel(ev: WheelEvent) {
    ev.preventDefault();
    const next = Math.min(2.2, Math.max(0.5, cloudZoom.value + (ev.deltaY > 0 ? -0.06 : 0.06)));
    cloudZoom.value = next;
    camera.position.set(0, 0, 160 / Math.max(0.2, cloudZoom.value));
  }

  container.addEventListener("pointerdown", onPointerDown);
  container.addEventListener("pointermove", onPointerMove);
  container.addEventListener("pointerup", onPointerUp);
  container.addEventListener("pointercancel", onPointerUp);
  container.addEventListener("wheel", onWheel, { passive: false });

  function tick() {
    if (cloudAutoRotate.value && !isDraggingCloud.value) {
      const s = 0.0018 * Math.max(0.2, cloudRotateSpeed.value);
      group.rotation.y += s * 1.2;
      group.rotation.x += s * 0.7;
    }
    renderer.render(scene, camera);
    labelRenderer.render(scene, camera);
    cloudAnimationId.value = requestAnimationFrame(tick);
  }
  tick();

  cloudScene.value = scene;
  cloudCamera.value = camera;
  cloudRenderer.value = renderer;
  cloudLabelRenderer.value = labelRenderer;
  cloudGroup.value = group;
}

function buildScatterData(points: CounselorScatterPoint[]) {
  const colors = ["#6aa9ff", "#ffc266", "#c49bff", "#6fe0c3", "#ff8a8a"];
  const byGroup = new Map<string, CounselorScatterPoint[]>();
  for (const p of points) {
    const list = byGroup.get(p.group) ?? [];
    list.push(p);
    byGroup.set(p.group, list);
  }

  return [...byGroup.entries()].map(([groupName, items], idx) => {
    const data = items.map((p) => [p.x, p.y, p.student_id, p.warning_score] as [number, number, string, number]);
    return {
      name: groupName,
      type: "scatter" as const,
      symbolSize: 10,
      itemStyle: { color: colors[idx % colors.length], opacity: 0.78 },
      data
    };
  });
}

function renderScatter(points: CounselorScatterPoint[]) {
  if (!scatterEl.value) return;
  if (!chart.value) chart.value = echarts.init(scatterEl.value);
  chart.value.setOption({
    tooltip: {
      formatter: (p: unknown) => {
        const param = p as { seriesName?: string; value?: [number, number, string, number] };
        const v = param.value;
        if (!v) return "";
        return `${v[2]}<br/>群体：${param.seriesName ?? "-"}<br/>预警分：${v[3]}`;
      }
    },
    grid: { left: 48, right: 24, top: 24, bottom: 40 },
    xAxis: {
      name: "维度 1",
      nameTextStyle: { color: "#9fb0d0", fontSize: 11 },
      splitLine: { lineStyle: { color: "#23304a" } },
      axisLabel: { color: "#9fb0d0" }
    },
    yAxis: {
      name: "维度 2",
      nameTextStyle: { color: "#9fb0d0", fontSize: 11 },
      splitLine: { lineStyle: { color: "#23304a" } },
      axisLabel: { color: "#9fb0d0" }
    },
    legend: {
      bottom: 0,
      textStyle: { color: "#9fb0d0", fontSize: 11 },
      type: "scroll"
    },
    series: buildScatterData(points)
  });
}

onMounted(async () => {
  loading.value = true;
  try {
    groups.value = await getCounselorGroups(groupMethod.value);
    scatterPoints.value = await getCounselorScatter(scatterMethod.value);
  } finally {
    loading.value = false;
  }
  await nextTick();
  renderScatter(scatterPoints.value);
  renderWordCloud3D();
  window.addEventListener("resize", () => chart.value?.resize());
  window.addEventListener("resize", resizeCloud3D);
});

watch(scatterMethod, async (m) => {
  scatterPoints.value = await getCounselorScatter(m);
  await nextTick();
  renderScatter(scatterPoints.value);
});

watch(groupMethod, async (m) => {
  groups.value = await getCounselorGroups(m);
  await nextTick();
  renderWordCloud3D();
});

watch(wordWeights, async () => {
  await nextTick();
  renderWordCloud3D();
});

watch([cloudAutoRotate, cloudRotateSpeed], async () => {
  // no-op: tick loop reads reactive values
  await nextTick();
});

watch(cloudZoom, async () => {
  await nextTick();
  resizeCloud3D();
});

onUnmounted(() => {
  chart.value?.dispose();
  disposeCloud3D();
});

function resizeCloud3D() {
  if (!cloudEl.value) return;
  const renderer = cloudRenderer.value;
  const labelRenderer = cloudLabelRenderer.value;
  const camera = cloudCamera.value;
  if (!renderer || !labelRenderer || !camera) return;
  const w = cloudEl.value.clientWidth || 400;
  const h = cloudEl.value.clientHeight || 400;
  renderer.setSize(w, h);
  labelRenderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

function goToStudent(studentId: string) {
  const id = (studentId || "").trim();
  if (!id) return;
  router.push(`/individuals/${encodeURIComponent(id)}`);
}
</script>

<template>
  <div class="page">
    <div v-if="loading" class="hint">数据加载中…</div>
    <template v-else>
      <div class="grid">
        <UiCard title="学生分布散点（二维降维）">
          <div class="toolbar">
            <label class="lbl">散点来源</label>
            <select v-model="scatterMethod" class="sel">
              <option value="numeric">数值特征投影</option>
              <option value="text">文本特征投影</option>
            </select>
          </div>
          <p class="note">基于所选特征做 PCA 二维投影；悬停可查看学号、所属群体与预警分。</p>
          <div ref="scatterEl" class="chart" />
        </UiCard>
        <UiCard title="群体关键词词云（加权）">
          <div class="toolbar">
            <label class="lbl">自动旋转</label>
            <select v-model="cloudAutoRotate" class="sel">
              <option :value="true">开启</option>
              <option :value="false">关闭</option>
            </select>
            <label class="lbl">速度</label>
            <input v-model.number="cloudRotateSpeed" class="rng" type="range" min="0.2" max="3" step="0.2" />
          </div>
          <p class="note">支持拖拽旋转与滚轮缩放。</p>
          <div ref="cloudEl" class="cloud" />
        </UiCard>
      </div>
      <UiCard title="群体画像卡片">
        <div class="toolbar">
          <label class="lbl">群体视角</label>
          <select v-model="groupMethod" class="sel">
            <option value="numeric">数值特征群体</option>
            <option value="text">文本主题群体</option>
          </select>
        </div>
        <div class="cards">
          <button
            v-for="g in groups"
            :key="g.name"
            type="button"
            class="gcard gbtn"
            @click="goToStudent(g.topStudent)"
          >
            <div class="gname">{{ g.name }}</div>
            <div class="gmeta">群体规模 {{ g.size }} · 示例学号 {{ g.topStudent }}</div>
          </button>
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
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.lbl {
  font-size: 12px;
  color: var(--muted);
}
.sel {
  min-width: 180px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
  font-size: 13px;
}
.rng {
  width: 160px;
}
.chart {
  width: 100%;
  height: 400px;
}
.cloud {
  width: 100%;
  height: 400px;
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
  text-align: left;
}
.gname {
  font-weight: 650;
  margin-bottom: 6px;
  color: #e7efff;
}
.gmeta {
  font-size: 12px;
  color: rgba(231, 239, 255, 0.72);
  margin-bottom: 8px;
}
.gbtn {
  cursor: pointer;
}
.gbtn:hover {
  border-color: rgba(106, 169, 255, 0.45);
  box-shadow: 0 0 0 1px rgba(106, 169, 255, 0.12) inset;
}
.gbtn:active {
  transform: translateY(1px);
}
</style>
