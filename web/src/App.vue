<script setup lang="ts">
import { RouterView } from 'vue-router';
import AppSidebar from '@/components/layout/AppSidebar.vue';
import AppTopBar from '@/components/layout/AppTopBar.vue';
import AppBackground from '@/components/layout/AppBackground.vue';
</script>

<template>
  <div class="app">
    <AppBackground />
    <AppSidebar />
    <div class="app__content">
      <AppTopBar />
      <main class="app__main">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  min-height: 100vh;
  position: relative;
}

.app__content {
  flex: 1;
  margin-left: 240px;
  display: flex;
  flex-direction: column;
  min-height: 100vh;
  position: relative;
  z-index: 1;
}

.app__main {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-6);
}

@media (max-width: 1024px) {
  .app__content {
    margin-left: 0;
  }
}
</style>
