<script setup lang="ts">
interface Props {
  modelValue: boolean;
  label?: string;
  disabled?: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void;
}>();

function toggle() {
  if (!props.disabled) {
    emit('update:modelValue', !props.modelValue);
  }
}
</script>

<template>
  <label class="mc-checkbox" :class="{ 'mc-checkbox--disabled': props.disabled }" @click="toggle">
    <span class="mc-checkbox__box" :class="{ 'mc-checkbox__box--checked': props.modelValue }">
      <svg v-if="props.modelValue" viewBox="0 0 16 16" fill="none" class="mc-checkbox__check">
        <path d="M3 8L6.5 11.5L13 4.5" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </span>
    <span v-if="props.label" class="mc-checkbox__label">{{ props.label }}</span>
  </label>
</template>

<style scoped>
.mc-checkbox {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  cursor: pointer;
  user-select: none;
}

.mc-checkbox--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.mc-checkbox__box {
  width: 20px;
  height: 20px;
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: border-color var(--transition-fast), background-color var(--transition-fast);
  flex-shrink: 0;
}

.mc-checkbox__box--checked {
  background-color: var(--primary);
  border-color: var(--primary);
  color: var(--text-inverse);
}

.mc-checkbox__check {
  width: 14px;
  height: 14px;
}

.mc-checkbox__label {
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  color: var(--text-primary);
}
</style>
