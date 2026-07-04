<script setup lang="ts">
import { ref, watch } from 'vue';
import type { ProjectInfo } from '@/types/api';
import McBadge from '@/components/ui/McBadge.vue';

interface Props {
  project: ProjectInfo;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'add', slug: string): void;
}>();
const iconFailed = ref(false);

const typeBadge: Record<string, 'mod' | 'resourcepack' | 'shader' | 'datapack'> = {
  mod: 'mod',
  resource_pack: 'resourcepack',
  shader: 'shader',
  datapack: 'datapack',
};

watch(() => props.project.icon, () => {
  iconFailed.value = false;
}, { immediate: true });
</script>

<template>
  <div class="search-result-card">
    <div class="search-result-card__icon">
      <img
        v-if="props.project.icon && !iconFailed"
        :src="props.project.icon"
        :alt="`${props.project.title || props.project.name} 图标`"
        class="search-result-card__icon-image"
        loading="lazy"
        referrerpolicy="no-referrer"
        @error="iconFailed = true"
      />
      <span v-else class="search-result-card__placeholder">{{ props.project.name?.slice(0, 2).toUpperCase() }}</span>
    </div>
    <div class="search-result-card__info">
      <div class="search-result-card__header">
        <h3 class="search-result-card__title">{{ props.project.title || props.project.name }}</h3>
        <McBadge :type="typeBadge[props.project.project_type] || 'mod'" />
      </div>
      <p class="search-result-card__desc">{{ props.project.description?.slice(0, 100) || '暂无描述' }}</p>
      <div class="search-result-card__meta">
        <span class="search-result-card__downloads" v-if="props.project.downloads">
          <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="16">
            <path d="M8 12l-4-4h2.5V3h3v5H12L8 12zM3 13h10v1H3z"/>
          </svg>
          {{ props.project.downloads.toLocaleString() }}
        </span>
        <div v-if="props.project.categories" class="search-result-card__categories">
          <McBadge v-for="cat in props.project.categories.slice(0, 3)" :key="cat" type="mod">{{ cat }}</McBadge>
        </div>
      </div>
    </div>
    <button class="search-result-card__add" @click="emit('add', props.project.name)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="12" y1="5" x2="12" y2="19" />
        <line x1="5" y1="12" x2="19" y2="12" />
      </svg>
      添加
    </button>
  </div>
</template>

<style scoped>
.search-result-card {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-4);
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-sm);
  transition: border-color var(--transition-fast), transform var(--transition-fast);
  align-items: flex-start;
}

.search-result-card:hover {
  border-color: var(--border-glow);
  transform: scale(1.01);
}

.search-result-card__icon {
  width: 64px;
  height: 64px;
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  overflow: hidden;
}

.search-result-card__icon-image {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.search-result-card__placeholder {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-muted);
}

.search-result-card__info {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  flex: 1;
  min-width: 0;
}

.search-result-card__header {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.search-result-card__title {
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  color: var(--text-primary);
  margin: 0;
  line-height: 1.3;
  word-break: break-all;
}

.search-result-card__desc {
  font-family: 'Outfit', sans-serif;
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.search-result-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.search-result-card__downloads {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  color: var(--accent-gold);
}

.search-result-card__categories {
  display: flex;
  gap: var(--space-1);
  flex-wrap: wrap;
}

.search-result-card__add {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  padding: var(--space-2) var(--space-3);
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  flex-shrink: 0;
}

.search-result-card__add:hover {
  border-color: var(--primary);
  color: var(--primary);
  background-color: var(--bg-elevated);
}

.search-result-card__add svg {
  width: 16px;
  height: 16px;
  stroke-width: 2;
}
</style>
