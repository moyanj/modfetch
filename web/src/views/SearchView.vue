<script setup lang="ts">
import { useSearchStore } from '@/stores/search';
import { useConfigStore } from '@/stores/config';
import SearchBar from '@/components/search/SearchBar.vue';
import SearchResultCard from '@/components/search/SearchResultCard.vue';
import McButton from '@/components/ui/McButton.vue';

const searchStore = useSearchStore();
const configStore = useConfigStore();

function onLoadMore() {
  searchStore.loadMore();
}
</script>

<template>
  <div class="search-view">
    <h2 class="search-view__title">搜索模组</h2>
    <SearchBar />
    <div v-if="searchStore.loading && searchStore.results.length === 0" class="search-view__loading">
      <div class="search-view__spinner"></div>
      <span>搜索中...</span>
    </div>
    <div v-else-if="searchStore.results.length === 0" class="search-view__empty">
      输入关键词开始搜索模组
    </div>
    <div v-else class="search-view__results">
      <SearchResultCard
        v-for="project in searchStore.results"
        :key="project.id"
        :project="project"
        @add="configStore.addMod($event, 'mod')"
      />
    </div>
    <div v-if="searchStore.hasMore" class="search-view__more">
      <McButton variant="secondary" size="sm" :disabled="searchStore.loading" @click="onLoadMore">
        {{ searchStore.loading ? '加载中...' : '加载更多' }}
      </McButton>
    </div>
  </div>
</template>

<style scoped>
.search-view {
  padding: var(--space-6);
  max-width: 1200px;
}

.search-view__title {
  font-family: 'Silkscreen', monospace;
  font-size: 24px;
  color: var(--text-primary);
  margin-bottom: var(--space-6);
}

.search-view__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-10);
  color: var(--text-secondary);
  font-family: 'Silkscreen', monospace;
  font-size: 12px;
}

.search-view__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border-stone);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: pixel-spin 0.8s steps(8) infinite;
}

.search-view__empty {
  text-align: center;
  padding: var(--space-10);
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
}

.search-view__results {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  margin-top: var(--space-6);
}

.search-view__more {
  display: flex;
  justify-content: center;
  margin-top: var(--space-6);
}

@keyframes pixel-spin {
  to { transform: rotate(360deg); }
}
</style>
