<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue';

interface Props {
  show: boolean;
  title?: string;
}

const props = defineProps<Props>();
const emit = defineEmits<{
  (e: 'close'): void;
}>();

function onKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') emit('close');
}

onMounted(() => window.addEventListener('keydown', onKeydown));
onUnmounted(() => window.removeEventListener('keydown', onKeydown));
</script>

<template>
  <Transition name="mc-modal">
    <div v-if="props.show" class="mc-modal" @click="emit('close')">
      <div class="mc-modal__content" @click.stop>
        <div class="mc-modal__header">
          <h3 v-if="props.title" class="mc-modal__title">{{ props.title }}</h3>
          <button class="mc-modal__close" @click="emit('close')" aria-label="关闭">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="mc-modal__body">
          <slot />
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.mc-modal {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: rgba(13, 14, 26, 0.8);
  backdrop-filter: blur(4px);
}

.mc-modal__content {
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-md);
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  overflow-y: auto;
  box-shadow: var(--shadow-elevated);
}

.mc-modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  border-bottom: 1px solid var(--border-stone);
}

.mc-modal__title {
  font-family: 'Silkscreen', monospace;
  font-size: 14px;
  color: var(--text-primary);
  margin: 0;
}

.mc-modal__close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.mc-modal__close:hover {
  color: var(--text-primary);
}

.mc-modal__close svg {
  width: 18px;
  height: 18px;
}

.mc-modal__body {
  padding: var(--space-5);
}

.mc-modal-enter-active,
.mc-modal-leave-active {
  transition: opacity var(--transition-normal);
}

.mc-modal-enter-from,
.mc-modal-leave-to {
  opacity: 0;
}
</style>
