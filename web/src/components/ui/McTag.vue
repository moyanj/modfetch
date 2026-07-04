<script setup lang="ts">
interface Props {
  type?: 'mod' | 'resourcepack' | 'shader' | 'success' | 'warning' | 'error' | 'info';
  removable?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  type: 'mod',
  removable: false,
});

const emit = defineEmits<{
  (e: 'remove'): void;
}>();

const colorMap: Record<string, string> = {
  mod: 'var(--primary)',
  resourcepack: 'var(--accent-diamond)',
  shader: 'var(--accent-gold)',
  success: 'var(--status-success)',
  warning: 'var(--status-warning)',
  error: 'var(--status-error)',
  info: 'var(--status-info)',
};
</script>

<template>
  <span
    class="mc-tag"
    :style="{
      color: colorMap[props.type],
      borderColor: `${colorMap[props.type]}66`,
      backgroundColor: `${colorMap[props.type]}1a`,
    }"
  >
    <slot />
    <button v-if="props.removable" class="mc-tag__remove" @click.stop="emit('remove')">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
        <line x1="4" y1="4" x2="12" y2="12" />
        <line x1="12" y1="4" x2="4" y2="12" />
      </svg>
    </button>
  </span>
</template>

<style scoped>
.mc-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  line-height: 1.4;
  border: 1px solid;
  border-radius: var(--radius-sm);
  white-space: nowrap;
}

.mc-tag__remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  padding: 0;
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  opacity: 0.7;
  transition: opacity var(--transition-fast);
}

.mc-tag__remove:hover {
  opacity: 1;
}

.mc-tag__remove svg {
  width: 8px;
  height: 8px;
}
</style>
