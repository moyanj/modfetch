import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ProjectInfo } from '@/types/api';
import { searchMods as searchModsApi } from '@/api/search';

export const useSearchStore = defineStore('search', () => {
  const query = ref('');
  const results = ref<ProjectInfo[]>([]);
  const loading = ref(false);
  const filters = ref<Record<string, string>>({});
  const offset = ref(0);
  const limit = ref(20);
  const totalHits = ref(0);

  const hasMore = computed(() => results.value.length < totalHits.value);

  async function search(q: string) {
    query.value = q;
    offset.value = 0;
    loading.value = true;
    try {
      const res = await searchModsApi(q, filters.value, offset.value, limit.value);
      results.value = res.hits;
      totalHits.value = res.total_hits;
    } finally {
      loading.value = false;
    }
  }

  async function loadMore() {
    if (!hasMore.value || loading.value) return;
    loading.value = true;
    try {
      const res = await searchModsApi(query.value, filters.value, offset.value + limit.value, limit.value);
      results.value.push(...res.hits);
      offset.value += limit.value;
    } finally {
      loading.value = false;
    }
  }

  function applyFilter(key: string, value: string) {
    filters.value[key] = value;
    if (query.value) search(query.value);
  }

  function removeFilter(key: string) {
    delete filters.value[key];
    if (query.value) search(query.value);
  }

  function clearFilters() {
    filters.value = {};
    if (query.value) search(query.value);
  }

  return {
    query,
    results,
    loading,
    filters,
    offset,
    limit,
    totalHits,
    hasMore,
    search,
    loadMore,
    applyFilter,
    removeFilter,
    clearFilters,
  };
});
