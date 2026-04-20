<script setup lang="ts">
import UiCard from "../components/UiCard.vue";
</script>

<template>
  <UiCard title="系统管理（占位）">
    <p class="p">原「模型运维 / 数据监控 / 反馈闭环」等管理模块已随框架重置移除。</p>
    <p class="p">若需要恢复管理员能力，可在此路由下逐步挂载新的子页面与接口。</p>
  </UiCard>
</template>

<style scoped>
.p {
  margin: 0 0 10px;
  color: var(--muted);
  line-height: 1.55;
  font-size: 14px;
}
</style>
