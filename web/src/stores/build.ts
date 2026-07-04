import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ModFetchConfig } from '@/types/config';
import type { WsEvent } from '@/types/events';
import { createJob } from '@/api/jobs';

type BuildPhase = 'idle' | 'resolve' | 'download' | 'package';

interface ResolveItem {
  mod_slug: string;
  status: 'pending' | 'resolving' | 'completed' | 'failed';
  title?: string;
  version?: string;
  dependencies?: number;
  error?: { code: string; message: string };
}

interface DownloadItem {
  filename: string;
  size: number;
  url: string;
  percent: number;
  bytes_downloaded: number;
  bytes_total: number;
  status: 'pending' | 'downloading' | 'completed' | 'failed';
  retries: number;
  error?: { code: string; message: string };
}

interface BuildStats {
  total: number;
  completed: number;
  failed: number;
  skipped: number;
  bytes_downloaded: number;
}

interface BuildResult {
  filename: string;
  path: string;
  size: number;
  format: string;
  mc_version: string;
  loader: string;
}

export const useBuildStore = defineStore('build', () => {
  const currentJobId = ref<string | null>(null);
  const phase = ref<BuildPhase>('idle');
  const resolveItems = ref<ResolveItem[]>([]);
  const downloadItems = ref<DownloadItem[]>([]);
  const stats = ref<BuildStats>({ total: 0, completed: 0, failed: 0, skipped: 0, bytes_downloaded: 0 });
  const results = ref<BuildResult[]>([]);
  const errors = ref<Array<{ code: string; message: string }>>([]);
  const connectionStatus = ref<'connecting' | 'open' | 'closed' | 'error'>('closed');
  const durationMs = ref(0);

  const isRunning = computed(() => phase.value !== 'idle');
  const overallProgress = computed(() => {
    if (!stats.value.total) return 0;
    return Math.round(((stats.value.completed + stats.value.failed + stats.value.skipped) / stats.value.total) * 100);
  });

  async function startJob(config: ModFetchConfig): Promise<string> {
    reset();
    const { job_id } = await createJob(config);
    currentJobId.value = job_id;
    return job_id;
  }

  function handleEvent(event: WsEvent) {
    switch (event.event) {
      case 'job_started':
        currentJobId.value = event.data.job_id;
        phase.value = 'idle';
        break;
      case 'phase_change':
        phase.value = event.data.phase;
        break;
      case 'resolve_start':
        resolveItems.value.push({
          mod_slug: event.data.mod_slug,
          status: 'resolving',
        });
        break;
      case 'resolve_complete': {
        const rIdx = resolveItems.value.findIndex(i => i.mod_slug === event.data.mod_slug);
        if (rIdx >= 0) {
          resolveItems.value[rIdx] = {
            ...resolveItems.value[rIdx],
            status: 'completed',
            title: event.data.title,
            version: event.data.version,
            dependencies: event.data.dependencies,
          };
        }
        break;
      }
      case 'resolve_failed': {
        const rfIdx = resolveItems.value.findIndex(i => i.mod_slug === event.data.mod_slug);
        if (rfIdx >= 0) {
          resolveItems.value[rfIdx] = {
            ...resolveItems.value[rfIdx],
            status: 'failed',
            error: event.data.error,
          };
        }
        break;
      }
      case 'download_start':
        downloadItems.value.push({
          filename: event.data.filename,
          size: event.data.size,
          url: event.data.url,
          percent: 0,
          bytes_downloaded: 0,
          bytes_total: event.data.size,
          status: 'downloading',
          retries: 0,
        });
        break;
      case 'download_progress': {
        const dpIdx = downloadItems.value.findIndex(i => i.filename === event.data.filename);
        if (dpIdx >= 0) {
          downloadItems.value[dpIdx] = {
            ...downloadItems.value[dpIdx],
            percent: event.data.percent,
            bytes_downloaded: event.data.bytes_downloaded,
            bytes_total: event.data.bytes_total,
          };
        }
        break;
      }
      case 'download_complete': {
        const dcIdx = downloadItems.value.findIndex(i => i.filename === event.data.filename);
        if (dcIdx >= 0) {
          downloadItems.value[dcIdx] = {
            ...downloadItems.value[dcIdx],
            status: 'completed',
            size: event.data.size,
          };
        }
        break;
      }
      case 'download_failed': {
        const dfIdx = downloadItems.value.findIndex(i => i.filename === event.data.filename);
        if (dfIdx >= 0) {
          downloadItems.value[dfIdx] = {
            ...downloadItems.value[dfIdx],
            status: 'failed',
            retries: event.data.retries,
            error: event.data.error,
          };
        }
        break;
      }
      case 'stats_update':
        stats.value = event.data;
        break;
      case 'job_complete':
        phase.value = 'idle';
        results.value = event.data.results;
        durationMs.value = event.data.duration_ms;
        break;
      case 'job_failed':
        phase.value = 'idle';
        errors.value.push(event.data.error);
        break;
    }
  }

  function reset() {
    currentJobId.value = null;
    phase.value = 'idle';
    resolveItems.value = [];
    downloadItems.value = [];
    stats.value = { total: 0, completed: 0, failed: 0, skipped: 0, bytes_downloaded: 0 };
    results.value = [];
    errors.value = [];
    durationMs.value = 0;
  }

  return {
    currentJobId,
    phase,
    resolveItems,
    downloadItems,
    stats,
    results,
    errors,
    connectionStatus,
    durationMs,
    isRunning,
    overallProgress,
    startJob,
    handleEvent,
    reset,
  };
});
