<script setup lang="ts">
import { ref, watch } from 'vue';
import { useConfigStore } from '@/stores/config';
import McInput from '@/components/ui/McInput.vue';

const configStore = useConfigStore();
const featuresInput = ref('');
const pluginsEnabledInput = ref('');
const pluginConfigsInput = ref('{}');
const pluginConfigsError = ref('');

function joinList(value?: string[]) {
  return value?.join(', ') ?? '';
}

function parseList(value: string) {
  return value.split(',').map(item => item.trim()).filter(Boolean);
}

function syncFromStore() {
  featuresInput.value = joinList(configStore.config.features);
  pluginsEnabledInput.value = joinList(configStore.config.plugins?.enabled);
  pluginConfigsInput.value = JSON.stringify(configStore.config.plugins?.configs ?? {}, null, 2);
}

function updateFeatures(value: string) {
  featuresInput.value = value;
  configStore.config.features = parseList(value);
}

function updatePluginsEnabled(value: string) {
  pluginsEnabledInput.value = value;
  if (!configStore.config.plugins) {
    configStore.config.plugins = { enabled: [], configs: {} };
  }
  configStore.config.plugins.enabled = parseList(value);
}

function updatePluginConfigs(value: string) {
  pluginConfigsInput.value = value;
  if (!configStore.config.plugins) {
    configStore.config.plugins = { enabled: [], configs: {} };
  }

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('插件配置必须是 JSON 对象');
    }
    configStore.config.plugins.configs = parsed as Record<string, Record<string, unknown>>;
    pluginConfigsError.value = '';
    configStore.clearValidationIssue('plugins.configs');
  } catch (error) {
    pluginConfigsError.value = error instanceof Error ? error.message : '插件配置 JSON 无法解析';
    configStore.setValidationIssue('plugins.configs', `插件配置无效: ${pluginConfigsError.value}`);
  }
}

watch(
  () => configStore.config,
  () => syncFromStore(),
  { deep: true, immediate: true },
);
</script>

<template>
  <div class="feature-plugin-settings">
    <h3 class="feature-plugin-settings__title">功能与插件</h3>
    <div class="feature-plugin-settings__field">
      <label class="feature-plugin-settings__label">启用 Features</label>
      <McInput
        :model-value="featuresInput"
        placeholder="例如 client, server, optional"
        @update:model-value="updateFeatures"
      />
    </div>
    <div class="feature-plugin-settings__field">
      <label class="feature-plugin-settings__label">启用 Plugins</label>
      <McInput
        :model-value="pluginsEnabledInput"
        placeholder="例如 progress, notify"
        @update:model-value="updatePluginsEnabled"
      />
    </div>
    <div class="feature-plugin-settings__field">
      <label class="feature-plugin-settings__label">Plugin Configs (JSON)</label>
      <textarea
        class="feature-plugin-settings__textarea"
        :value="pluginConfigsInput"
        placeholder="{&#10;  &quot;notify&quot;: { &quot;channel&quot;: &quot;desktop&quot; }&#10;}"
        @input="event => updatePluginConfigs((event.target as HTMLTextAreaElement).value)"
      />
      <p v-if="pluginConfigsError" class="feature-plugin-settings__error">{{ pluginConfigsError }}</p>
    </div>
  </div>
</template>

<style scoped>
.feature-plugin-settings {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.feature-plugin-settings__title {
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  color: var(--text-primary);
  letter-spacing: 0.5px;
}

.feature-plugin-settings__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.feature-plugin-settings__label {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.feature-plugin-settings__textarea {
  min-height: 180px;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
}

.feature-plugin-settings__textarea:focus {
  border-color: var(--border-glow);
  box-shadow: 0 0 0 3px rgba(77, 208, 225, 0.15);
}

.feature-plugin-settings__error {
  color: var(--accent-redstone);
  font-size: 12px;
  font-family: 'Outfit', sans-serif;
}
</style>
