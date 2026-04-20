<script setup lang="ts">
import { reactive, ref } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const loading = ref(false);
const form = reactive({
  username: "",
  password: "",
  role: "counselor"
});

function login() {
  if (!form.username.trim() || !form.password.trim()) return;
  loading.value = true;
  setTimeout(() => {
    localStorage.setItem("edu_auth_token", "dev-token");
    localStorage.setItem("edu_role", form.role);
    router.replace("/overview");
  }, 300);
}
</script>

<template>
  <div class="login-wrap">
    <div class="panel">
      <h1>数智精准育人系统</h1>
      <p class="subtitle">登录后进入辅导员工作台总览</p>
      <input v-model="form.username" placeholder="用户名" @keydown.enter="login" />
      <input v-model="form.password" type="password" placeholder="密码" @keydown.enter="login" />
      <select v-model="form.role">
        <option value="counselor">辅导员端</option>
        <option value="admin">管理员端</option>
      </select>
      <button :disabled="loading || !form.username.trim() || !form.password.trim()" @click="login">
        {{ loading ? "登录中..." : "登录" }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 16px;
}
.panel {
  width: min(420px, 100%);
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 20px;
  display: grid;
  gap: 10px;
}
h1 { margin: 0; font-size: 22px; }
.subtitle { margin: 0 0 8px; color: var(--muted); font-size: 13px; }
input, select {
  width: 100%;
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: #0c1426;
  color: var(--text);
}
button {
  margin-top: 6px;
  padding: 10px 14px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: linear-gradient(180deg, #2a65ff, #1c49b6);
  color: white;
  cursor: pointer;
}
button:disabled { opacity: 0.6; cursor: not-allowed; }
</style>

