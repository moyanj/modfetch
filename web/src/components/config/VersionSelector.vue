<script setup lang="ts">
import { computed, ref, watch, onMounted } from 'vue';
import { useConfigStore } from '@/stores/config';
import { getMcVersions } from '@/api/meta';
import type { MinecraftVersionItem } from '@/types/api';
import McCheckbox from '@/components/ui/McCheckbox.vue';

const configStore = useConfigStore();
const versions = ref<MinecraftVersionItem[]>([]);
const loading = ref(false);
const includeSnapshots = ref(false);

onMounted(async () => {
  loading.value = true;
  try {
    versions.value = await getMcVersions();
  } catch (e) {
    console.error('Failed to fetch versions:', e);
    versions.value = ['1.21.1', '1.20.4', '1.20.1', '1.19.4', '1.19.2', '1.18.2', '1.17.1', '1.16.5']
      .map((version) => ({ version, version_type: 'release' }));
  } finally {
    loading.value = false;
  }
});

const selected = ref<string[]>([...(configStore.config.minecraft.version || [])]);

watch(() => configStore.config.minecraft.version, (val) => {
  selected.value = [...(val || [])];
}, { deep: true });

const visibleVersions = computed(() => {
  if (includeSnapshots.value) return versions.value;
  return versions.value.filter((item) => item.version_type === 'release');
});

function toggle(version: string) {
  const idx = selected.value.indexOf(version);
  if (idx >= 0) {
    selected.value.splice(idx, 1);
  } else {
    selected.value.push(version);
  }
  configStore.config.minecraft.version = [...selected.value];
}
</script>

<template>
  <div class="version-selector">
    <div class="version-selector__header">
      <h4 class="version-selector__label">Minecraft 版本</h4>
      <McCheckbox
        :model-value="includeSnapshots"
        label="包含 Snapshot"
        @update:model-value="includeSnapshots = $event"
      />
    </div>
    <div class="version-selector__grid">
      <McCheckbox
        v-for="item in visibleVersions"
        :key="item.version"
        :model-value="selected.includes(item.version)"
        :label="item.version"
        @update:model-value="toggle(item.version)"
      />
    </div>
  </div>
</template>

<style scoped>
.version-selector__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  flex-wrap: wrap;
}

.version-selector__label {
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.version-selector__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
  gap: var(--space-2);
  max-height: 220px;
  overflow-y: auto;
  overflow-x: hidden;
  align-content: start;
  scrollbar-gutter: stable;
}

@media (max-width: 640px) {
  .version-selector__grid {
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    max-height: 200px;
  }
}
</style>
