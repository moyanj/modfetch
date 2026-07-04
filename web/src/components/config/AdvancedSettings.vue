<script setup lang="ts">
import { ref } from 'vue';
import { useConfigStore } from '@/stores/config';
import McInput from '@/components/ui/McInput.vue';

const configStore = useConfigStore();
const collapsed = ref(true);
</script>

<template>
  <div class="advanced-settings">
    <button class="advanced-settings__toggle" @click="collapsed = !collapsed">
      <span class="advanced-settings__icon" :class="{ 'advanced-settings__icon--open': !collapsed }">▶</span>
      <span class="advanced-settings__label">高级设置</span>
    </button>
    <div v-if="!collapsed" class="advanced-settings__content">
      <div class="advanced-settings__field">
        <label class="advanced-settings__label">最大并发数</label>
        <McInput
          :model-value="String(configStore.config.max_concurrent ?? 5)"
          type="number"
          @update:model-value="val => configStore.config.max_concurrent = Number(val)"
        />
      </div>
      <div class="advanced-settings__field">
        <label class="advanced-settings__label">最大重试次数</label>
        <McInput
          :model-value="String(configStore.config.max_retries ?? 3)"
          type="number"
          @update:model-value="val => configStore.config.max_retries = Number(val)"
        />
      </div>
      <div class="advanced-settings__field">
        <label class="advanced-settings__label">重试延迟 (秒)</label>
        <McInput
          :model-value="String(configStore.config.retry_delay ?? 1.0)"
          type="number"
          @update:model-value="val => configStore.config.retry_delay = Number(val)"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.advanced-settings__toggle {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-3) 0;
  background: none;
  border: none;
  color: var(--text-secondary);
  cursor: pointer;
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: color var(--transition-fast);
}

.advanced-settings__toggle:hover {
  color: var(--text-primary);
}

.advanced-settings__icon {
  display: inline-block;
  transition: transform var(--transition-fast);
  font-size: 10px;
}

.advanced-settings__icon--open {
  transform: rotate(90deg);
}

.advanced-settings__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  padding-top: var(--space-3);
}

.advanced-settings__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.advanced-settings__label {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
</style>
