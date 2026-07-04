<script setup lang="ts">
interface Props {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  disabled?: boolean;
  loading?: boolean;
  type?: 'button' | 'submit' | 'reset';
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'primary',
  size: 'md',
  disabled: false,
  loading: false,
  type: 'button',
});

const sizeClasses = {
  sm: 'mc-button--sm',
  md: 'mc-button--md',
  lg: 'mc-button--lg',
};

const variantClasses = {
  primary: 'mc-button--primary',
  secondary: 'mc-button--secondary',
  danger: 'mc-button--danger',
  ghost: 'mc-button--ghost',
};
</script>

<template>
  <button
    :type="props.type"
    :disabled="props.disabled || props.loading"
    :class="['mc-button', sizeClasses[props.size], variantClasses[props.variant], { 'mc-button--loading': props.loading }]"
  >
    <span v-if="props.loading" class="mc-button__spinner" aria-hidden="true"></span>
    <span class="mc-button__text" :style="{ opacity: props.loading ? 0 : 1 }"><slot /></span>
  </button>
</template>

<style scoped>
.mc-button {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  border: none;
  cursor: pointer;
  font-family: 'Silkscreen', monospace;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: transform var(--transition-fast), filter var(--transition-fast);
  user-select: none;
  white-space: nowrap;
  border-radius: var(--radius-sm);
}

.mc-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Size variants */
.mc-button--sm {
  padding: var(--space-2) var(--space-3);
  font-size: 10px;
  line-height: 1.4;
  border-width: 2px;
}

.mc-button--md {
  padding: var(--space-3) var(--space-4);
  font-size: 12px;
  line-height: 1.4;
  border-width: 3px;
}

.mc-button--lg {
  padding: var(--space-4) var(--space-6);
  font-size: 14px;
  line-height: 1.4;
  border-width: 4px;
}

/* Primary button - 3D grass block */
.mc-button--primary {
  background-color: var(--primary);
  color: var(--text-inverse);
  box-shadow: inset 0 2px 0 var(--primary-hover), inset 0 -3px 0 var(--primary-dark);
}

.mc-button--primary:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.1);
}

.mc-button--primary:active:not(:disabled) {
  transform: translateY(2px);
  box-shadow: inset 0 2px 0 var(--primary-dark);
}

/* Secondary button - stone */
.mc-button--secondary {
  background-color: var(--bg-surface);
  color: var(--text-primary);
  box-shadow: inset 0 2px 0 var(--bg-elevated), inset 0 -3px 0 var(--bg-inset);
  border: 2px solid var(--border-stone);
}

.mc-button--secondary:hover:not(:disabled) {
  transform: translateY(-1px);
  border-color: var(--border-glow);
}

.mc-button--secondary:active:not(:disabled) {
  transform: translateY(2px);
}

/* Danger button - redstone */
.mc-button--danger {
  background-color: var(--accent-redstone);
  color: var(--text-inverse);
  box-shadow: inset 0 2px 0 #ff8a80, inset 0 -3px 0 #c62828;
}

.mc-button--danger:hover:not(:disabled) {
  transform: translateY(-1px);
  filter: brightness(1.1);
}

/* Ghost button */
.mc-button--ghost {
  background-color: transparent;
  color: var(--text-secondary);
  border: 2px solid transparent;
}

.mc-button--ghost:hover:not(:disabled) {
  color: var(--text-primary);
  border-color: var(--border-stone);
  background-color: var(--bg-surface);
}

/* Loading spinner */
.mc-button--loading {
  cursor: wait;
}

.mc-button__spinner {
  position: absolute;
  width: 16px;
  height: 16px;
  border: 2px solid var(--text-secondary);
  border-top-color: transparent;
  border-radius: 50%;
  animation: pixel-spin 0.8s steps(8) infinite;
}

@keyframes pixel-spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
