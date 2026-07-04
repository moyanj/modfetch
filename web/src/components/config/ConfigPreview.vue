<script setup lang="ts">
import { computed } from 'vue';
import { useConfigStore } from '@/stores/config';

const configStore = useConfigStore();

const configPreview = computed(() => JSON.stringify(configStore.config, null, 2));
</script>

<template>
  <div class="config-preview">
    <h4 class="config-preview__title">配置预览 (JSON)</h4>
    <pre class="config-preview__code"><code>{{ configPreview }}</code></pre>
  </div>
</template>

<style scoped>
.config-preview__title {
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--space-3);
}

.config-preview__code {
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  padding: var(--space-4);
  font-family: 'JetBrains Mono', monospace;
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary);
  overflow-x: auto;
  white-space: pre;
}
</style>
