<script setup lang="ts">
defineProps<{ title?: string }>();
</script>

<template>
  <section class="card">
    <div v-if="title" class="title">{{ title }}</div>
    <slot />
  </section>
</template>

<style scoped>
.card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px;
}
.title {
  color: var(--muted);
  font-weight: 600;
  font-size: 12px;
  margin-bottom: 10px;
}
</style>

