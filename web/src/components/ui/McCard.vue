<script setup lang="ts">
interface Props {
  hoverable?: boolean;
  selected?: boolean;
  variant?: 'default' | 'inset' | 'elevated';
}

const props = withDefaults(defineProps<Props>(), {
  hoverable: true,
  selected: false,
  variant: 'default',
});
</script>

<template>
  <div
    :class="[
      'mc-card',
      { 'mc-card--hoverable': props.hoverable, 'mc-card--selected': props.selected },
      `mc-card--${props.variant}`,
    ]"
  >
    <slot />
  </div>
</template>

<style scoped>
.mc-card {
  position: relative;
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-sm);
  padding: var(--space-4);
  transition: border-color var(--transition-fast), transform var(--transition-fast), box-shadow var(--transition-fast);
}

/* Inset top highlight */
.mc-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 2px;
  right: 2px;
  height: 1px;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
  pointer-events: none;
}

.mc-card--hoverable:hover {
  border-color: var(--border-glow);
  transform: scale(1.01);
  box-shadow: var(--shadow-glow);
}

.mc-card--selected {
  border-color: var(--primary);
  box-shadow: 0 0 8px var(--primary-glow);
}

.mc-card--inset {
  background-color: var(--bg-inset);
  box-shadow: var(--shadow-inset);
}

.mc-card--elevated {
  background-color: var(--bg-elevated);
  box-shadow: var(--shadow-elevated);
}
</style>
