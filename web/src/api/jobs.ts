import { api } from './client';
import type { ModFetchConfig } from '@/types/config';
import type { JobState, JobSummary } from '@/types/api';

export async function createJob(config: ModFetchConfig): Promise<{ job_id: string }> {
  const { data } = await api.post('/jobs', { config });
  return data;
}

export async function getJob(jobId: string): Promise<JobState> {
  const { data } = await api.get(`/jobs/${jobId}`);
  return data;
}

export async function listJobs(): Promise<JobSummary[]> {
  const { data } = await api.get('/jobs');
  return data;
}

export async function cancelJob(jobId: string): Promise<void> {
  await api.post(`/jobs/${jobId}/cancel`);
}

export function buildJobStreamUrl(jobId: string, origin = window.location.origin): string {
  const base = new URL(origin);
  base.protocol = base.protocol === 'https:' ? 'wss:' : 'ws:';
  base.pathname = `/api/jobs/${jobId}/stream`;
  base.search = '';
  base.hash = '';
  return base.toString();
}
