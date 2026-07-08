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

export interface ValidationSuggestion {
  slug: string;
  project_id: string;
  title: string;
  project_type: string;
  downloads: number;
}

export interface ValidationIssue {
  field: string;
  code: string;
  message: string;
  context?: {
    identifier?: string;
    entry_type?: string;
    actual_type?: string;
    incompatible_targets?: string[];
    suggestions?: ValidationSuggestion[];
  };
}

export interface ValidateConfigResponse {
  valid: boolean;
  errors: ValidationIssue[];
}

export interface JobResultItem {
  filename: string;
  path: string;
  size: number;
  format: string;
  mc_version: string;
  loader: string;
}

export interface JobErrorItem {
  code: string;
  message: string;
  context?: Record<string, unknown> | null;
}

export interface JobStats {
  total_mods: number;
  resolved: number;
  downloaded: number;
  failed: number;
  bytes_downloaded: number;
}

export interface JobState {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  phase: 'resolve' | 'download' | 'package' | 'idle';
  stats: JobStats;
  results: JobResultItem[] | null;
  errors: JobErrorItem[] | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface JobSummary {
  id: string;
  status: string;
  phase: string;
  started_at: string | null;
  completed_at: string | null;
}
