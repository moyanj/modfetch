<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useBuildStore } from '@/stores/build';
import { useWebSocket } from '@/composables/useWebSocket';
import { buildJobStreamUrl } from '@/api/jobs';
import PhaseIndicator from '@/components/build/PhaseIndicator.vue';
import DownloadItem from '@/components/build/DownloadItem.vue';
import StatsCard from '@/components/build/StatsCard.vue';
import McProgress from '@/components/ui/McProgress.vue';
import McCard from '@/components/ui/McCard.vue';

const route = useRoute();
const router = useRouter();
const buildStore = useBuildStore();
const { lastEvent, status, connect } = useWebSocket();

const jobId = computed(() => String(route.params.id ?? ''));
let pollTimer: ReturnType<typeof setInterval> | null = null;

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling(jobIdValue: string) {
  stopPolling();
  pollTimer = setInterval(async () => {
    await buildStore.hydrateJob(jobIdValue);
    if (buildStore.jobStatus === 'completed' || buildStore.jobStatus === 'failed') {
      stopPolling();
      await router.replace(`/results/${jobIdValue}`);
    }
  }, 1000);
}

async function syncJob(jobIdValue: string) {
  if (!jobIdValue) return;

  await buildStore.hydrateJob(jobIdValue);
  if (buildStore.jobStatus === 'completed' || buildStore.jobStatus === 'failed') {
    stopPolling();
    await router.replace(`/results/${jobIdValue}`);
    return;
  }

  if (buildStore.jobStatus === 'pending' || buildStore.jobStatus === 'running') {
    connect(buildJobStreamUrl(jobIdValue));
    startPolling(jobIdValue);
  }
}

onMounted(() => {
  void syncJob(jobId.value);
});

watch(jobId, (nextJobId) => {
  void syncJob(nextJobId);
});

watch(lastEvent, (event) => {
  if (!event) return;

  buildStore.handleEvent(event);
  if (event.event === 'job_complete' || event.event === 'job_failed') {
    stopPolling();
    void router.replace(`/results/${jobId.value}`);
  }
});

watch(status, (value) => {
  buildStore.connectionStatus = value;
}, { immediate: true });

onUnmounted(() => {
  stopPolling();
});
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
