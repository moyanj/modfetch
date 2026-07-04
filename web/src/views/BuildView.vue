<script setup lang="ts">
import { onMounted, watch } from 'vue';
import { useRoute } from 'vue-router';
import { useBuildStore } from '@/stores/build';
import { useWebSocket } from '@/composables/useWebSocket';
import PhaseIndicator from '@/components/build/PhaseIndicator.vue';
import DownloadItem from '@/components/build/DownloadItem.vue';
import StatsCard from '@/components/build/StatsCard.vue';
import McProgress from '@/components/ui/McProgress.vue';
import McCard from '@/components/ui/McCard.vue';

const route = useRoute();
const buildStore = useBuildStore();
  const { events, connect } = useWebSocket();

const jobId = route.params.id as string;

onMounted(() => {
  if (jobId) {
    connect(`ws://localhost:8000/api/jobs/${jobId}/stream`);
  }
});

watch(events, (newEvents) => {
  const last = newEvents[newEvents.length - 1];
  if (last) buildStore.handleEvent(last);
}, { deep: true });
</script>

<template>
  <div class="build-view">
    <h2 class="build-view__title">构建进度</h2>
    <div v-if="!buildStore.currentJobId && buildStore.downloadItems.length === 0" class="build-view__empty">
      <h3 class="build-view__empty-title">还没有构建任务</h3>
      <p class="build-view__empty-text">从配置页面开始构建后，这里会显示解析、下载和打包进度。</p>
    </div>
    <template v-else>
      <PhaseIndicator :phase="buildStore.phase" />
      <div class="build-view__content">
      <div class="build-view__main">
        <McCard variant="elevated">
          <h3 class="build-view__section-title">下载进度</h3>
          <McProgress :value="buildStore.overallProgress" show-label />
          <div v-if="buildStore.downloadItems.length > 0" class="build-view__downloads">
            <DownloadItem
              v-for="item in buildStore.downloadItems"
              :key="item.filename"
              :filename="item.filename"
              :percent="item.percent"
              :bytes-downloaded="item.bytes_downloaded"
              :bytes-total="item.bytes_total"
              :retries="item.retries"
            />
          </div>
          <div v-else class="build-view__hint">
            当前阶段还没有可显示的下载项。
          </div>
        </McCard>
      </div>
      <div class="build-view__side">
        <StatsCard
          :total="buildStore.stats.total"
          :completed="buildStore.stats.completed"
          :failed="buildStore.stats.failed"
          :skipped="buildStore.stats.skipped"
          :bytes-downloaded="buildStore.stats.bytes_downloaded"
        />
      </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.build-view {
  padding: var(--space-6);
  max-width: 1200px;
}

.build-view__title {
  font-family: 'Silkscreen', monospace;
  font-size: 24px;
  color: var(--text-primary);
  margin-bottom: var(--space-6);
}

.build-view__content {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: var(--space-6);
  margin-top: var(--space-6);
}

.build-view__main {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.build-view__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.build-view__section-title {
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
  letter-spacing: 0.5px;
}

.build-view__empty,
.build-view__hint {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-muted);
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-md);
}

.build-view__empty-title {
  margin: 0 0 var(--space-3);
  font-family: 'Silkscreen', monospace;
  font-size: 16px;
  color: var(--text-primary);
}

.build-view__empty-text {
  margin: 0;
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

.build-view__downloads {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-4);
  max-height: 400px;
  overflow-y: auto;
}

@media (max-width: 1024px) {
  .build-view__content {
    grid-template-columns: 1fr;
  }
}
</style>
