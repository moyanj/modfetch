import { api } from './client';
import type { SearchResult, ProjectInfo } from '@/types/api';

export async function searchMods(
  query: string,
  filters: { type?: string; loader?: string; version?: string } = {},
  offset = 0,
  limit = 20,
): Promise<SearchResult> {
  const params = new URLSearchParams();
  params.append('q', query);
  params.append('offset', String(offset));
  params.append('limit', String(limit));
  if (filters.type) params.append('type', filters.type);
  if (filters.loader) params.append('loader', filters.loader);
  if (filters.version) params.append('version', filters.version);
  const { data } = await api.get(`/search?${params.toString()}`);
  return {
    hits: (data.hits ?? []).map((hit: Record<string, unknown>) => ({
      id: String(hit.project_id ?? hit.slug ?? ''),
      name: String(hit.slug ?? ''),
      title: String(hit.title ?? ''),
      description: String(hit.description ?? ''),
      project_type: normalizeProjectType(String(hit.project_type ?? 'mod')),
      versions: [],
      icon: typeof hit.icon_url === 'string' ? hit.icon_url : undefined,
      downloads: typeof hit.downloads === 'number' ? hit.downloads : 0,
      categories: Array.isArray(hit.categories) ? hit.categories.filter((item): item is string => typeof item === 'string') : [],
    })),
    offset: typeof data.offset === 'number' ? data.offset : offset,
    limit: typeof data.limit === 'number' ? data.limit : limit,
    total_hits: typeof data.total_hits === 'number' ? data.total_hits : ((data.hits ?? []).length),
  };
}

export async function getProject(projectId: string): Promise<ProjectInfo> {
  const { data } = await api.get(`/projects/${projectId}`);
  return {
    id: String(data.id ?? ''),
    name: String(data.slug ?? ''),
    title: String(data.title ?? ''),
    description: String(data.description ?? ''),
    project_type: normalizeProjectType(String(data.project_type ?? 'mod')),
    versions: Array.isArray(data.versions) ? data.versions : [],
    icon: typeof data.icon_url === 'string' ? data.icon_url : undefined,
    downloads: undefined,
    categories: Array.isArray(data.categories) ? data.categories.filter((item: unknown): item is string => typeof item === 'string') : [],
  };
}

function normalizeProjectType(type: string): ProjectInfo['project_type'] {
  if (type === 'resourcepack' || type === 'resource_pack') return 'resource_pack';
  if (type === 'shader' || type === 'shaderpack') return 'shader';
  if (type === 'datapack') return 'datapack';
  return 'mod';
}
