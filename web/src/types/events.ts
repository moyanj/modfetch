/** WebSocket event types for build progress */

export interface JobStartedEvent {
  event: 'job_started';
  data: { job_id: string; config_summary: Record<string, unknown> };
}

export interface PhaseChangeEvent {
  event: 'phase_change';
  data: { phase: 'resolve' | 'download' | 'package' | 'idle' };
}

export interface ResolveStartEvent {
  event: 'resolve_start';
  data: { mod_slug: string; mc_version: string; loader: string };
}

export interface ResolveCompleteEvent {
  event: 'resolve_complete';
  data: { mod_slug: string; title: string; version: string; dependencies: number };
}

export interface ResolveFailedEvent {
  event: 'resolve_failed';
  data: { mod_slug: string; error: { code: string; message: string } };
}

export interface DownloadStartEvent {
  event: 'download_start';
  data: { filename: string; size: number; url: string };
}

export interface DownloadProgressEvent {
  event: 'download_progress';
  data: { filename: string; percent: number; bytes_downloaded: number; bytes_total: number };
}

export interface DownloadCompleteEvent {
  event: 'download_complete';
  data: { filename: string; size: number };
}

export interface DownloadFailedEvent {
  event: 'download_failed';
  data: { filename: string; error: { code: string; message: string }; retries: number };
}

export interface PackageStartEvent {
  event: 'package_start';
  data: { format: string; mc_version: string; loader: string; mode: string };
}

export interface PackageCompleteEvent {
  event: 'package_complete';
  data: { filename: string; path: string; size: number; format: string };
}

export interface StatsUpdateEvent {
  event: 'stats_update';
  data: { total: number; completed: number; failed: number; skipped: number; bytes_downloaded: number };
}

export interface JobCompleteEvent {
  event: 'job_complete';
  data: {
    results: Array<{
      filename: string;
      path: string;
      size: number;
      format: string;
      mc_version: string;
      loader: string;
    }>;
    duration_ms: number;
  };
}

export interface JobFailedEvent {
  event: 'job_failed';
  data: { error: { code: string; message: string } };
}

export type WsEvent =
  | JobStartedEvent
  | PhaseChangeEvent
  | ResolveStartEvent
  | ResolveCompleteEvent
  | ResolveFailedEvent
  | DownloadStartEvent
  | DownloadProgressEvent
  | DownloadCompleteEvent
  | DownloadFailedEvent
  | PackageStartEvent
  | PackageCompleteEvent
  | StatsUpdateEvent
  | JobCompleteEvent
  | JobFailedEvent;
