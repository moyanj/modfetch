/** API response types */

import type { ModLoader } from './config';

export interface MinecraftVersionItem {
  version: string;
  version_type: string;
}

export interface ProjectInfo {
  id: string;
  name: string;
  title: string;
  description: string;
  project_type: 'mod' | 'resource_pack' | 'shader' | 'datapack';
  versions: string[];
  icon?: string;
  downloads?: number;
  categories?: string[];
}

export interface FileInfo {
  url: string;
  filename: string;
  size: number;
  hashes?: Record<string, string>;
}

export interface DependencyInfo {
  project_id: string;
  dependency_type: 'required' | 'optional' | 'incompatible' | 'embedded';
}

export interface VersionInfo {
  id: string;
  name: string;
  version: string;
  loaders: ModLoader[];
  game_versions: string[];
  files: FileInfo[];
  dependencies: DependencyInfo[];
}

export interface SearchResult {
  hits: ProjectInfo[];
  offset: number;
  limit: number;
  total_hits: number;
}

export interface JobState {
  job_id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  phase: 'resolve' | 'download' | 'package' | 'idle';
  progress: number;
  config_summary?: Record<string, unknown>;
}

export interface JobSummary {
  job_id: string;
  status: string;
  created_at: string;
}
