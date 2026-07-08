<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useBuildStore } from '@/stores/build';

const route = useRoute();
const buildStore = useBuildStore();

const pageTitles: Record<string, string> = {
  config: '配置项目',
  search: '搜索模组',
  build: '构建进度',
  results: '构建结果',
};

const currentTitle = computed(() => pageTitles[String(route.name ?? '')] || 'ModFetch');

const statusMap: Record<string, { text: string; color: string }> = {
  idle: { text: '就绪', color: 'var(--text-muted)' },
  pending: { text: '排队中', color: 'var(--accent-gold)' },
  running: { text: '构建中', color: 'var(--primary)' },
  completed: { text: '完成', color: 'var(--status-success)' },
  failed: { text: '失败', color: 'var(--status-error)' },
};

const currentStatus = computed(() => statusMap[buildStore.jobStatus] || statusMap.idle);
</script>

<template>
  <header class="app-topbar">
    <h1 class="app-topbar__title">{{ currentTitle }}</h1>
    <div class="app-topbar__status">
      <span
        class="app-topbar__status-dot"
        :style="{ backgroundColor: currentStatus.color, boxShadow: `0 0 8px ${currentStatus.color}` }"
      ></span>
      <span class="app-topbar__status-text" :style="{ color: currentStatus.color }">{{ currentStatus.text }}</span>
    </div>
  </header>
</template>

<style scoped>
.app-topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-6);
  border-bottom: 1px solid var(--border-stone);
  background-color: var(--bg-base);
}

.app-topbar__title {
  font-family: 'Silkscreen', monospace;
  font-size: 18px;
  color: var(--text-primary);
  margin: 0;
  letter-spacing: 0.5px;
}

.app-topbar__status {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.app-topbar__status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.app-topbar__status-text {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
</style>
