<script setup lang="ts">
import { ref } from 'vue';
import { useSearchStore } from '@/stores/search';
import McInput from '@/components/ui/McInput.vue';

const searchStore = useSearchStore();
const query = ref(searchStore.query);

function onSearch() {
  searchStore.search(query.value);
}
</script>

<template>
  <div class="search-bar">
    <McInput v-model="query" placeholder="搜索模组..." @keyup.enter="onSearch" />
    <button class="search-bar__button" @click="onSearch">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="8" />
        <line x1="21" y1="21" x2="16.65" y2="16.65" />
      </svg>
    </button>
  </div>
</template>

<style scoped>
.search-bar {
  display: flex;
  gap: var(--space-2);
}

.search-bar__button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  background-color: var(--primary);
  border: none;
  border-radius: var(--radius-sm);
  color: var(--text-inverse);
  cursor: pointer;
  transition: background-color var(--transition-fast);
  flex-shrink: 0;
}

.search-bar__button:hover {
  background-color: var(--primary-hover);
}

.search-bar__button svg {
  width: 18px;
  height: 18px;
}
</style>
