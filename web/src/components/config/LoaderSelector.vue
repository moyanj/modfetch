<script setup lang="ts">
import { ref, watch } from 'vue';
import { useConfigStore } from '@/stores/config';
import type { ModLoader } from '@/types/config';

const configStore = useConfigStore();

const loaders: { value: ModLoader; label: string; icon: string }[] = [
  { value: 'fabric', label: 'Fabric', icon: 'F' },
  { value: 'forge', label: 'Forge', icon: 'Fg' },
  { value: 'neoforge', label: 'NeoForge', icon: 'N' },
  { value: 'quilt', label: 'Quilt', icon: 'Q' },
];

const selected = ref<ModLoader[]>([]);

watch(() => configStore.config.minecraft.mod_loader, (val) => {
  selected.value = Array.isArray(val) ? [...val] : [val];
}, { immediate: true, deep: true });

function toggle(loader: ModLoader) {
  const idx = selected.value.indexOf(loader);
  if (idx >= 0) {
    selected.value.splice(idx, 1);
  } else {
    selected.value.push(loader);
  }
  configStore.config.minecraft.mod_loader = selected.value.length > 1 ? [...selected.value] : selected.value[0] || 'fabric';
}
</script>

<template>
  <div class="loader-selector">
    <h4 class="loader-selector__label">模组加载器</h4>
    <div class="loader-selector__grid">
      <div
        v-for="l in loaders"
        :key="l.value"
        :class="['loader-selector__card', { 'loader-selector__card--active': selected.includes(l.value) }]"
        @click="toggle(l.value)"
      >
        <span class="loader-selector__icon">{{ l.icon }}</span>
        <span class="loader-selector__name">{{ l.label }}</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.loader-selector__label {
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--space-3);
}

.loader-selector__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: var(--space-3);
}

.loader-selector__card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-4);
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.loader-selector__card:hover {
  border-color: var(--border-glow);
}

.loader-selector__card--active {
  border-color: var(--primary);
  background-color: var(--bg-elevated);
  box-shadow: 0 0 8px var(--primary-glow);
}

.loader-selector__icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  font-family: 'Silkscreen', monospace;
  font-size: 14px;
  color: var(--text-primary);
}

.loader-selector__name {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
}
</style>
