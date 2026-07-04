<script setup lang="ts">
interface Option {
  value: string;
  label: string;
}

interface Props {
  modelValue: string;
  options: Option[];
  disabled?: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

function onChange(event: Event) {
  const target = event.target as HTMLSelectElement;
  emit('update:modelValue', target.value);
}
</script>

<template>
  <div class="mc-select">
    <select :value="props.modelValue" :disabled="props.disabled" @change="onChange">
      <option v-for="opt in props.options" :key="opt.value" :value="opt.value">
        {{ opt.label }}
      </option>
    </select>
    <svg class="mc-select__arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  </div>
</template>

<style scoped>
.mc-select {
  position: relative;
  width: 100%;
}

.mc-select select {
  width: 100%;
  padding: var(--space-3) var(--space-8) var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  appearance: none;
  cursor: pointer;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  outline: none;
}

.mc-select select:focus {
  border-color: var(--border-glow);
  box-shadow: 0 0 0 3px rgba(77, 208, 225, 0.15);
}

.mc-select select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mc-select__arrow {
  position: absolute;
  right: var(--space-3);
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  color: var(--text-secondary);
  pointer-events: none;
}
</style>
