<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { useConfigStore } from '@/stores/config';
import { useBuildStore } from '@/stores/build';
import MetadataForm from '@/components/config/MetadataForm.vue';
import VersionSelector from '@/components/config/VersionSelector.vue';
import LoaderSelector from '@/components/config/LoaderSelector.vue';
import ModList from '@/components/config/ModList.vue';
import OutputForm from '@/components/config/OutputForm.vue';
import AdvancedSettings from '@/components/config/AdvancedSettings.vue';
import ConfigPreview from '@/components/config/ConfigPreview.vue';
import FeaturePluginSettings from '@/components/config/FeaturePluginSettings.vue';
import McButton from '@/components/ui/McButton.vue';
import McCard from '@/components/ui/McCard.vue';

const configStore = useConfigStore();
const buildStore = useBuildStore();
const router = useRouter();
const activeTab = ref<'mods' | 'resourcepacks' | 'shaderpacks'>('mods');

async function onBuild() {
  const errors = configStore.validate();
  if (errors.length > 0) {
    alert(errors.join('\n'));
    return;
  }
  try {
    const jobId = await buildStore.startJob(configStore.config);
    router.push(`/build/${jobId}`);
  } catch (e) {
    alert(`创建构建任务失败: ${e}`);
  }
}
</script>

<template>
  <div class="config-view">
    <h2 class="config-view__title">配置项目</h2>
    <div class="config-view__grid">
      <div class="config-view__main">
        <McCard variant="elevated">
          <h3 class="config-view__section-title">元数据</h3>
          <MetadataForm />
        </McCard>
        <McCard variant="elevated">
          <VersionSelector />
        </McCard>
        <McCard variant="elevated">
          <LoaderSelector />
        </McCard>
        <McCard variant="elevated">
          <div class="config-view__tabs">
            <button v-for="tab in (['mods', 'resourcepacks', 'shaderpacks'] as const)" :key="tab"
              :class="['config-view__tab', { 'config-view__tab--active': activeTab === tab }]" @click="activeTab = tab">
              {{ tab === 'mods' ? '模组' : tab === 'resourcepacks' ? '资源包' : '光影' }}
            </button>
          </div>
          <ModList
            :type="activeTab === 'mods' ? 'mod' : activeTab === 'resourcepacks' ? 'resourcepack' : 'shaderpack'" />
        </McCard>
        <McCard variant="elevated">
          <h3 class="config-view__section-title">输出设置</h3>
          <OutputForm />
        </McCard>
        <McCard variant="elevated">
          <AdvancedSettings />
        </McCard>
      </div>
      <div class="config-view__side">
        <McCard variant="elevated">
          <ConfigPreview />
        </McCard>
        <McCard variant="elevated">
          <FeaturePluginSettings />
        </McCard>
        <McButton variant="primary" size="lg" @click="onBuild">
          开始构建
        </McButton>
      </div>
    </div>
  </div>
</template>

<style scoped>
.config-view {
  padding: var(--space-6);
  max-width: 1200px;
}

.config-view__title {
  font-family: 'Silkscreen', monospace;
  font-size: 24px;
  color: var(--text-primary);
  margin-bottom: var(--space-6);
}

.config-view__grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: var(--space-6);
}

.config-view__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.config-view__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.config-view__section-title {
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
  letter-spacing: 0.5px;
}

.config-view__tabs {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  border-bottom: 2px solid var(--border-stone);
  padding-bottom: var(--space-2);
}

.config-view__tab {
  padding: var(--space-2) var(--space-4);
  background: none;
  border: none;
  color: var(--text-secondary);
  font-family: 'Silkscreen', monospace;
  font-size: 11px;
  cursor: pointer;
  transition: color var(--transition-fast);
  border-bottom: 2px solid transparent;
  margin-bottom: calc(-1 * var(--space-2) - 2px);
}

.config-view__tab:hover {
  color: var(--text-primary);
}

.config-view__tab--active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

@media (max-width: 1024px) {
  .config-view__grid {
    grid-template-columns: 1fr;
  }
}
</style>
