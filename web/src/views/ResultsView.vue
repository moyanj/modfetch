<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { storeToRefs } from 'pinia';
import { useBuildStore } from '@/stores/build';
import { useWebSocket } from '@/composables/useWebSocket';
import { buildJobStreamUrl } from '@/api/jobs';
import McButton from '@/components/ui/McButton.vue';
import McCard from '@/components/ui/McCard.vue';
import McBadge from '@/components/ui/McBadge.vue';

const router = useRouter();
const route = useRoute();
const buildStore = useBuildStore();
const { lastEvent, status, connect } = useWebSocket();
const { jobStatus } = storeToRefs(buildStore);
const jobId = computed(() => String(route.params.id ?? ''));
let pollTimer: ReturnType<typeof setInterval> | null = null;

function formatDuration(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  if (hours > 0) return `${hours}h ${minutes % 60}m ${seconds % 60}s`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function onNewConfig() {
  buildStore.reset();
  router.push('/');
}

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
    }
  }, 1000);
}

async function syncJob(jobIdValue: string) {
  if (!jobIdValue) return;

  await buildStore.hydrateJob(jobIdValue);
  if (buildStore.jobStatus === 'pending' || buildStore.jobStatus === 'running') {
    connect(buildJobStreamUrl(jobIdValue));
    startPolling(jobIdValue);
  } else {
    stopPolling();
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
  <div class="results-view">
    <h2 class="results-view__title">构建结果</h2>
    <McCard v-if="jobStatus === 'pending' || jobStatus === 'running'" variant="elevated" class="results-view__pending">
      任务仍在运行，结果会在完成后自动更新。
    </McCard>
    <div v-if="buildStore.results.length === 0 && buildStore.errors.length === 0" class="results-view__empty-state">
      <h3 class="results-view__empty-title">还没有构建结果</h3>
      <p class="results-view__empty-text">任务完成后，输出文件和错误日志会显示在这里。</p>
    </div>
    <template v-else>
    <McCard variant="elevated" :class="['results-view__banner', buildStore.errors.length > 0 ? 'results-view__banner--error' : 'results-view__banner--success']">
      <div class="results-view__banner-content">
        <span class="results-view__banner-icon">{{ buildStore.errors.length > 0 ? '×' : '✓' }}</span>
        <span class="results-view__banner-text">
          {{ buildStore.errors.length > 0 ? '构建失败' : '构建完成' }}
        </span>
      </div>
      <span v-if="buildStore.durationMs > 0" class="results-view__duration">耗时: {{ formatDuration(buildStore.durationMs) }}</span>
    </McCard>
    <div class="results-view__content">
      <McCard variant="elevated">
        <h3 class="results-view__section-title">输出文件</h3>
        <div v-if="buildStore.results.length === 0" class="results-view__empty">暂无输出文件</div>
        <div v-else class="results-view__files">
          <div v-for="file in buildStore.results" :key="file.filename" class="results-view__file">
            <div class="results-view__file-info">
              <span class="results-view__file-name">{{ file.filename }}</span>
              <span class="results-view__file-path">{{ file.path }}</span>
            </div>
            <div class="results-view__file-meta">
              <McBadge :type="file.format === 'mrpack' ? 'mod' : 'resourcepack'">{{ file.format.toUpperCase() }}</McBadge>
              <span class="results-view__file-version">{{ file.mc_version }} / {{ file.loader }}</span>
              <span class="results-view__file-size">{{ formatBytes(file.size) }}</span>
            </div>
          </div>
        </div>
      </McCard>
      <div v-if="buildStore.errors.length > 0" class="results-view__errors">
        <McCard variant="elevated">
          <h3 class="results-view__section-title">错误日志</h3>
          <div class="results-view__error-list">
            <div v-for="(error, index) in buildStore.errors" :key="index" class="results-view__error-item">
              <span class="results-view__error-code">{{ error.code }}</span>
              <span class="results-view__error-message">{{ error.message }}</span>
            </div>
          </div>
        </McCard>
      </div>
      <div class="results-view__actions">
        <McButton variant="primary" @click="onNewConfig">新建配置</McButton>
        <McButton variant="secondary" @click="buildStore.reset()">重置</McButton>
      </div>
    </div>
    </template>
  </div>
</template>

<style scoped>
.results-view {
  padding: var(--space-6);
  max-width: 1200px;
}

.results-view__title {
  font-family: 'Silkscreen', monospace;
  font-size: 24px;
  color: var(--text-primary);
  margin-bottom: var(--space-6);
}

.results-view__banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-4) var(--space-5);
  margin-bottom: var(--space-6);
}

.results-view__pending {
  margin-bottom: var(--space-6);
}

.results-view__empty-state {
  padding: var(--space-8);
  text-align: center;
  color: var(--text-muted);
  background-color: var(--bg-surface);
  border: 2px solid var(--border-stone);
  border-radius: var(--radius-md);
}

.results-view__empty-title {
  margin: 0 0 var(--space-3);
  font-family: 'Silkscreen', monospace;
  font-size: 16px;
  color: var(--text-primary);
}

.results-view__empty-text {
  margin: 0;
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  line-height: 1.5;
}

.results-view__banner--success {
  border-color: var(--status-success);
  box-shadow: 0 0 12px rgba(124, 179, 66, 0.2);
}

.results-view__banner--error {
  border-color: var(--status-error);
  box-shadow: 0 0 12px rgba(255, 82, 82, 0.2);
}

.results-view__banner-content {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.results-view__banner-icon {
  font-family: 'Silkscreen', monospace;
  font-size: 20px;
}

.results-view__banner-text {
  font-family: 'Silkscreen', monospace;
  font-size: 14px;
  color: var(--text-primary);
}

.results-view__duration {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
}

.results-view__content {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
}

.results-view__section-title {
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
  letter-spacing: 0.5px;
}

.results-view__empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
}

.results-view__files {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

.results-view__file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 1px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  transition: border-color var(--transition-fast);
}

.results-view__file:hover {
  border-color: var(--border-stone);
}

.results-view__file-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}

.results-view__file-name {
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
}

.results-view__file-path {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  color: var(--text-muted);
}

.results-view__file-meta {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-shrink: 0;
}

.results-view__file-version {
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  color: var(--text-secondary);
}

.results-view__file-size {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--accent-gold);
}

.results-view__errors {
  margin-top: var(--space-4);
}

.results-view__error-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.results-view__error-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  padding: var(--space-3);
  background-color: var(--bg-inset);
  border: 1px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
}

.results-view__error-code {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--status-error);
}

.results-view__error-message {
  font-family: 'Outfit', sans-serif;
  font-size: 13px;
  color: var(--text-primary);
}

.results-view__actions {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-4);
}
</style>
