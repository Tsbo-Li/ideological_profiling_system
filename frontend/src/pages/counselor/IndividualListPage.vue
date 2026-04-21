<script setup lang="ts">
import { onMounted, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import UiCard from "../../components/UiCard.vue";
import { getStudentsList } from "../../api/counselor";
import type { RiskLevel, StudentListItem } from "../../types";

const loading = ref(true);
const rows = ref<StudentListItem[]>([]);
const keyword = ref("");
const riskLevel = ref<"all" | RiskLevel>("all");
const page = ref(1);
const pageSize = ref(20);
const total = ref(0);
const totalPages = ref(1);

async function load() {
  loading.value = true;
  try {
    const resp = await getStudentsList({
      keyword: keyword.value,
      riskLevel: riskLevel.value,
      limit: pageSize.value,
      offset: (page.value - 1) * pageSize.value
    });
    rows.value = resp.items;
    total.value = resp.total;
    totalPages.value = Math.max(1, Math.ceil(resp.total / pageSize.value));
    if (page.value > totalPages.value) {
      page.value = totalPages.value;
      return void load();
    }
  } finally {
    loading.value = false;
  }
}

onMounted(() => void load());

watch([keyword, riskLevel], () => {
  page.value = 1;
  void load();
});

watch([page, pageSize], () => void load());

function riskText(r: RiskLevel) {
  if (r === "high") return "高";
  if (r === "medium") return "中";
  return "低";
}
</script>

<template>
  <div class="page">
    <UiCard title="学生个体画像列表">
      <div class="toolbar">
        <input v-model="keyword" class="inp" placeholder="按学号 / 班级 / 标签关键词检索" />
        <select v-model="riskLevel" class="sel">
          <option value="all">全部风险等级</option>
          <option value="high">高</option>
          <option value="medium">中</option>
          <option value="low">低</option>
        </select>
        <select v-model.number="pageSize" class="sel">
          <option :value="10">10 / 页</option>
          <option :value="20">20 / 页</option>
          <option :value="50">50 / 页</option>
        </select>
      </div>
      <div v-if="loading" class="hint">加载中…</div>
      <table v-else class="table">
        <thead>
          <tr>
            <th>学号</th>
            <th>班级</th>
            <th>风险等级</th>
            <th>预警分</th>
            <th>最近更新时间</th>
            <th>标签</th>
            <th />
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in rows" :key="s.student_id">
            <td class="mono">{{ s.student_id }}</td>
            <td>{{ s.class_name }}</td>
            <td>
              <span class="pill" :class="'r-' + s.risk_level">{{ riskText(s.risk_level) }}</span>
            </td>
            <td>{{ s.latest_warning_score }}</td>
            <td class="muted">{{ s.latest_active_at }}</td>
            <td class="tags">{{ s.tags.join(" · ") }}</td>
            <td class="act">
              <RouterLink class="link" :to="`/individuals/${encodeURIComponent(s.student_id)}`">查看画像</RouterLink>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="!loading" class="pager">
        <span class="muted">共 {{ total }} 条，第 {{ page }} / {{ totalPages }} 页</span>
        <div class="pager-btns">
          <button type="button" class="pg-btn" :disabled="page <= 1" @click="page = 1">首页</button>
          <button type="button" class="pg-btn" :disabled="page <= 1" @click="page -= 1">上一页</button>
          <button type="button" class="pg-btn" :disabled="page >= totalPages" @click="page += 1">下一页</button>
          <button type="button" class="pg-btn" :disabled="page >= totalPages" @click="page = totalPages">末页</button>
        </div>
      </div>
    </UiCard>
  </div>
</template>

<style scoped>
.page {
  max-width: 1200px;
}
.toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 14px;
}
.inp {
  flex: 1;
  min-width: 200px;
  padding: 9px 11px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
}
.sel {
  padding: 9px 11px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
}
.hint {
  color: var(--muted);
  padding: 16px 0;
}
.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
th,
td {
  text-align: left;
  padding: 10px 8px;
  border-bottom: 1px solid var(--border);
}
th {
  color: var(--muted);
  font-weight: 600;
  font-size: 12px;
}
.mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.muted {
  color: var(--muted);
  white-space: nowrap;
}
.tags {
  color: var(--muted);
  max-width: 280px;
}
.pill {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
  border: 1px solid var(--border);
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
.act {
  text-align: right;
  white-space: nowrap;
}
.link {
  color: var(--accent);
  text-decoration: none;
  font-weight: 600;
}
.link:hover {
  text-decoration: underline;
}
.pager {
  margin-top: 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}
.pager-btns {
  display: flex;
  gap: 8px;
}
.pg-btn {
  padding: 6px 10px;
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
