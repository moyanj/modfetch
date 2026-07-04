import { api } from './client';
import type { MinecraftVersionItem, ValidateConfigResponse } from '@/types/api';

export async function getMcVersions(): Promise<MinecraftVersionItem[]> {
  const { data } = await api.get('/minecraft/versions');
  if (Array.isArray(data)) {
    return data.map((version) => ({ version, version_type: inferVersionType(version) }));
  }
  if (Array.isArray(data.items) && data.items.length > 0) {
    return data.items;
  }
  return (data.versions ?? []).map((version: string) => ({ version, version_type: inferVersionType(version) }));
}

function inferVersionType(version: string): string {
  const normalized = version.toLowerCase();
  if (/^\d+\.\d+(?:\.\d+)?$/.test(normalized)) {
    return 'release';
  }
  return 'snapshot';
}

export async function getLoaders(): Promise<string[]> {
  const { data } = await api.get('/minecraft/loaders');
  return Array.isArray(data) ? data : (data.loaders ?? []).map((item: { name: string }) => item.name);
}

export async function validateConfig(config: Record<string, unknown>): Promise<ValidateConfigResponse> {
  const { data } = await api.post('/config/validate', { config });
  return {
    valid: Boolean(data.valid),
    errors: Array.isArray(data.errors) ? data.errors : [],
  };
}
