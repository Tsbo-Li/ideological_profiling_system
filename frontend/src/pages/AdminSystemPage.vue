<script setup lang="ts">
import UiCard from "../components/UiCard.vue";
</script>

<template>
  <UiCard title="系统管理（建设中）">
    <p class="p">当前页面为管理员入口预留位，后续可接入模型运维、任务调度、数据审计与权限管理能力。</p>
    <p class="p">如需上线管理员功能，可在本路由下按模块逐步扩展子页面与后端接口。</p>
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
