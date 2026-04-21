<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();
const role = computed(() => localStorage.getItem("edu_role") || "counselor");

const counselorNav = [
  { to: "/overview", label: "工作台总览", match: (p: string) => p === "/overview" },
  { to: "/group-analysis", label: "群体画像分析", match: (p: string) => p.startsWith("/group-analysis") },
  { to: "/individuals", label: "学生个体画像", match: (p: string) => p.startsWith("/individuals") },
  { to: "/content-studio", label: "内容策划与生成", match: (p: string) => p.startsWith("/content-studio") }
];

const adminNav = [{ to: "/system", label: "系统管理", match: (p: string) => p.startsWith("/system") }];

const nav = computed(() => {
  if (role.value === "admin") return [...counselorNav, ...adminNav];
  return counselorNav;
});

const pageTitle = computed(() => (route.meta.title as string) || "辅导员工作台");
const activePath = computed(() => route.path);

function isActive(item: (typeof counselorNav)[0]) {
  return item.match(activePath.value);
}

function logout() {
  localStorage.removeItem("edu_auth_token");
  localStorage.removeItem("edu_role");
  router.replace("/login");
}
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="title">数智育人研判平台</div>
        <div class="sub">{{ role === "admin" ? "管理员视角（含辅导员功能）" : "辅导员业务视角" }}</div>
      </div>
      <nav class="nav">
        <RouterLink
          v-for="item in nav"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ active: isActive(item) }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </aside>
    <main class="main">
      <header class="topbar">
        <div class="page-head">
          <h1 class="page-title">{{ pageTitle }}</h1>
          <p class="page-path">{{ route.path }}</p>
        </div>
        <button type="button" class="logout" @click="logout">退出登录</button>
      </header>
      <div class="content">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px 1fr;
  min-height: 100vh;
}
.sidebar {
  border-right: 1px solid var(--border);
  background: #0c1426;
  padding: 14px;
}
.brand {
  padding: 12px 10px;
  border: 1px solid var(--border);
  border-radius: 14px;
  background: rgba(18, 26, 43, 0.85);
}
.title {
  font-weight: 700;
  letter-spacing: 0.4px;
  font-size: 15px;
}
.sub {
  margin-top: 6px;
  color: var(--muted);
  font-size: 12px;
}
.nav {
  margin-top: 14px;
  display: grid;
  gap: 8px;
}
.nav-item {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid var(--border);
  text-decoration: none;
  color: var(--muted);
  background: rgba(18, 26, 43, 0.4);
  font-size: 14px;
}
.nav-item.active {
  color: var(--text);
  border-color: rgba(106, 169, 255, 0.45);
  background: rgba(106, 169, 255, 0.12);
}
.main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.topbar {
  min-height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
  background: rgba(18, 26, 43, 0.55);
}
.page-head {
  min-width: 0;
}
.page-title {
  margin: 0;
  font-size: 17px;
  font-weight: 650;
}
.page-path {
  margin: 4px 0 0;
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
}
.logout {
  flex-shrink: 0;
  padding: 8px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #101a30;
  color: var(--muted);
  cursor: pointer;
  font-size: 13px;
}
.content {
  padding: 18px;
  flex: 1;
}
@media (max-width: 960px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .sidebar {
    position: sticky;
    top: 0;
    z-index: 5;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .nav {
    grid-auto-flow: column;
    grid-auto-columns: minmax(120px, 1fr);
    overflow-x: auto;
  }
}
</style>
