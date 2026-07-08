import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { buildJobStreamUrl } from '@/api/jobs';
import { useBuildStore } from '@/stores/build';
import type { JobState } from '@/types/api';

function makeCompletedJob(): JobState {
  return {
    id: 'job-123',
    status: 'completed',
    phase: 'idle',
    stats: {
      total_mods: 4,
      resolved: 4,
      downloaded: 3,
      failed: 1,
      bytes_downloaded: 4096,
    },
    results: [
      {
        filename: 'pack.mrpack',
        path: '/tmp/pack.mrpack',
        size: 2048,
        format: 'mrpack',
        mc_version: '1.21.1',
        loader: 'fabric',
      },
    ],
    errors: null,
    started_at: '2026-07-04T10:00:00+00:00',
    completed_at: '2026-07-04T10:00:05+00:00',
  };
}

describe('build store hydration', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('applies backend job snapshot to result state', () => {
    const store = useBuildStore();

    store.applyJobSnapshot(makeCompletedJob());

    expect(store.currentJobId).toBe('job-123');
    expect(store.jobStatus).toBe('completed');
    expect(store.phase).toBe('idle');
    expect(store.stats).toEqual({
      total: 4,
      completed: 3,
      failed: 1,
      skipped: 0,
      bytes_downloaded: 4096,
    });
    expect(store.results).toHaveLength(1);
    expect(store.durationMs).toBe(5000);
  });

  it('marks job as completed when completion event arrives', () => {
    const store = useBuildStore();

    store.handleEvent({
      event: 'job_complete',
      data: {
        results: [
          {
            filename: 'pack.mrpack',
            path: '/tmp/pack.mrpack',
            size: 2048,
            format: 'mrpack',
            mc_version: '1.21.1',
            loader: 'fabric',
          },
        ],
        duration_ms: 1234,
      },
    });

    expect(store.jobStatus).toBe('completed');
    expect(store.results[0]?.filename).toBe('pack.mrpack');
    expect(store.durationMs).toBe(1234);
    expect(store.isRunning).toBe(false);
  });
});

describe('build job stream url', () => {
  it('uses current origin and upgrades to websocket protocol', () => {
    const url = buildJobStreamUrl('job-123', 'https://mods.example.com/app/');

    expect(url).toBe('wss://mods.example.com/api/jobs/job-123/stream');
  });
});
