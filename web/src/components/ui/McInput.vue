<script setup lang="ts">
interface Props {
  modelValue: string;
  placeholder?: string;
  type?: string;
  disabled?: boolean;
  readonly?: boolean;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'update:modelValue', value: string): void;
}>();

function onInput(event: Event) {
  const target = event.target as HTMLInputElement;
  emit('update:modelValue', target.value);
}
</script>

<template>
  <input
    :type="props.type || 'text'"
    :value="props.modelValue"
    :placeholder="props.placeholder"
    :disabled="props.disabled"
    :readonly="props.readonly"
    class="mc-input"
    @input="onInput"
  />
</template>

<style scoped>
.mc-input {
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  transition: border-color var(--transition-fast), box-shadow var(--transition-fast);
  outline: none;
}

.mc-input::placeholder {
  color: var(--text-muted);
}

.mc-input:focus {
  border-color: var(--border-glow);
  box-shadow: 0 0 0 3px rgba(77, 208, 225, 0.15);
}

.mc-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
