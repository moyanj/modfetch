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
