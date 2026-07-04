<script setup lang="ts">
import { ref, watch } from 'vue';
import { useConfigStore } from '@/stores/config';
import type { FileType, ModEntry } from '@/types/config';
import McButton from '@/components/ui/McButton.vue';
import McInput from '@/components/ui/McInput.vue';
import McTag from '@/components/ui/McTag.vue';

const props = defineProps<{
  type: FileType;
}>();
const configStore = useConfigStore();
const newSlug = ref('');

const listMap: Record<FileType, keyof typeof configStore.config.minecraft> = {
  mod: 'mods',
  resourcepack: 'resourcepacks',
  shaderpack: 'shaderpacks',
  file: 'extra_urls',
};

const items = ref<(string | ModEntry)[]>([]);

function refresh() {
  const key = listMap[props.type];
  items.value = [...(configStore.config.minecraft[key] as (string | ModEntry)[] || [])];
}

watch(() => configStore.config.minecraft, () => refresh(), { deep: true, immediate: true });

function add() {
  if (!newSlug.value.trim()) return;
  configStore.addMod(newSlug.value.trim(), props.type);
  newSlug.value = '';
  refresh();
}

function remove(index: number) {
  configStore.removeMod(index, props.type);
  refresh();
}

function getDisplay(item: string | ModEntry): string {
  if (typeof item === 'string') return item;
  return item.slug || item.id || '未知';
}

function getConditions(item: string | ModEntry): string[] {
  if (typeof item === 'string') return [];
  const conds: string[] = [];
  if (item.only_version) conds.push(`版本: ${Array.isArray(item.only_version) ? item.only_version.join(', ') : item.only_version}`);
  if (item.feature) conds.push(`特性: ${Array.isArray(item.feature) ? item.feature.join(', ') : item.feature}`);
  return conds;
}
</script>

<template>
  <div class="mod-list">
    <div class="mod-list__add">
      <McInput v-model="newSlug" placeholder="输入模组 slug 或 ID..." @keyup.enter="add" />
      <McButton variant="primary" size="sm" @click="add">添加</McButton>
    </div>
    <div class="mod-list__items">
      <div v-for="(item, index) in items" :key="index" class="mod-list__item">
        <div class="mod-list__info">
          <span class="mod-list__name">{{ getDisplay(item) }}</span>
          <div class="mod-list__conditions">
            <McTag v-for="cond in getConditions(item)" :key="cond" type="mod">{{ cond }}</McTag>
          </div>
        </div>
        <button class="mod-list__remove" @click="remove(index)">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="4" y1="4" x2="12" y2="12" />
            <line x1="12" y1="4" x2="4" y2="12" />
          </svg>
        </button>
      </div>
      <div v-if="items.length === 0" class="mod-list__empty">暂无项目</div>
    </div>
  </div>
</template>

<style scoped>
.mod-list__add {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.mod-list__items {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 300px;
  overflow-y: auto;
}

.mod-list__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 1px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  transition: border-color var(--transition-fast);
}

.mod-list__item:hover {
  border-color: var(--border-stone);
}

.mod-list__info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}

.mod-list__name {
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
}

.mod-list__conditions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.mod-list__remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--transition-fast);
  flex-shrink: 0;
  margin-left: var(--space-2);
}

.mod-list__remove:hover {
  color: var(--accent-redstone);
}

.mod-list__remove svg {
  width: 14px;
  height: 14px;
}

.mod-list__empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
}
</style>
