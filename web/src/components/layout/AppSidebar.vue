<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import appLogo from '../../../../logo/logo_raw.png';
import { useBuildStore } from '@/stores/build';

const route = useRoute();
const buildStore = useBuildStore();

const navItems = computed(() => [
  { path: '/', label: '配置项目', icon: 'M' },
  { path: '/search', label: '搜索模组', icon: 'S' },
  { path: buildStore.currentJobId ? `/build/${buildStore.currentJobId}` : '/', label: '构建进度', icon: 'B' },
  { path: buildStore.currentJobId ? `/results/${buildStore.currentJobId}` : '/', label: '构建结果', icon: 'R' },
]);

function isActive(path: string) {
  if (path === '/') return route.path === '/';
  return route.path.startsWith(path);
}
</script>

<template>
  <aside class="app-sidebar">
    <div class="app-sidebar__logo">
      <div class="app-sidebar__icon">
        <img :src="appLogo" alt="ModFetch logo" class="app-sidebar__logo-image" />
      </div>
      <div class="app-sidebar__brand">
        <span class="app-sidebar__title">ModFetch</span>
        <span class="app-sidebar__subtitle">v1.0</span>
      </div>
    </div>
    <nav class="app-sidebar__nav">
      <router-link
        v-for="item in navItems"
        :key="item.label"
        :to="item.path"
        :class="['app-sidebar__item', { 'app-sidebar__item--active': isActive(item.path) }]"
      >
        <span class="app-sidebar__item-icon">{{ item.icon }}</span>
        <span class="app-sidebar__item-label">{{ item.label }}</span>
      </router-link>
    </nav>
    <div class="app-sidebar__footer">
      <span class="app-sidebar__footer-text">Minecraft Mod Downloader</span>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  position: fixed;
  top: 0;
  left: 0;
  width: 240px;
  height: 100vh;
  background-color: var(--bg-base);
  border-right: 2px solid var(--border-stone);
  display: flex;
  flex-direction: column;
  z-index: 100;
}

.app-sidebar__logo {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-5) var(--space-5);
  border-bottom: 1px solid var(--border-stone);
}

.app-sidebar__icon {
  width: 40px;
  height: 40px;
  background-color: var(--bg-inset);
  border: 2px solid var(--primary-dark);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.app-sidebar__logo-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.app-sidebar__brand {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.app-sidebar__title {
  font-family: 'Silkscreen', monospace;
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.2;
}

.app-sidebar__subtitle {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-muted);
  line-height: 1.2;
}

.app-sidebar__nav {
  flex: 1;
  padding: var(--space-4) var(--space-3);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  overflow-y: auto;
}

.app-sidebar__item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  border-radius: var(--radius-sm);
  text-decoration: none;
  color: var(--text-secondary);
  transition: all var(--transition-fast);
  border: 2px solid transparent;
}

.app-sidebar__item:hover {
  background-color: var(--bg-surface);
  color: var(--text-primary);
}

.app-sidebar__item--active {
  background-color: var(--bg-surface);
  border-color: var(--border-stone);
  color: var(--primary);
  box-shadow: inset 3px 0 0 var(--primary);
}

.app-sidebar__item-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  flex-shrink: 0;
}

.app-sidebar__item-label {
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  letter-spacing: 0.5px;
}

.app-sidebar__footer {
  padding: var(--space-4) var(--space-5);
  border-top: 1px solid var(--border-stone);
}

.app-sidebar__footer-text {
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
</style>
