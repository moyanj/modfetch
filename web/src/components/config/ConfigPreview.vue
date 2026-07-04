<script setup lang="ts">
import { computed } from 'vue';
import { useConfigStore } from '@/stores/config';

const configStore = useConfigStore();

const tomlPreview = computed(() => {
  const c = configStore.config;
  return `[metadata]
name = "${c.metadata.name}"
version = "${c.metadata.version}"
description = "${c.metadata.description}"

[minecraft]
version = [${c.minecraft.version.map(v => `"${v}"`).join(', ')}]
mod_loader = [${(Array.isArray(c.minecraft.mod_loader) ? c.minecraft.mod_loader : [c.minecraft.mod_loader]).map(l => `"${l}"`).join(', ')}]
mods = [${c.minecraft.mods.map(m => typeof m === 'string' ? `"${m}"` : `{ slug = "${m.slug || m.id || ''}" }`).join(', ')}]
resourcepacks = [${c.minecraft.resourcepacks.map(m => typeof m === 'string' ? `"${m}"` : `{ slug = "${m.slug || m.id || ''}" }`).join(', ')}]
shaderpacks = [${c.minecraft.shaderpacks.map(m => typeof m === 'string' ? `"${m}"` : `{ slug = "${m.slug || m.id || ''}" }`).join(', ')}]

[output]
download_dir = "${c.output.download_dir}"
format = [${c.output.format.map(f => `"${f}"`).join(', ')}]
mrpack_modes = [${c.output.mrpack_modes.map(m => `"${m}"`).join(', ')}]
`;
});
</script>

<template>
  <div class="config-preview">
    <h4 class="config-preview__title">配置预览 (TOML)</h4>
    <pre class="config-preview__code"><code>{{ tomlPreview }}</code></pre>
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
