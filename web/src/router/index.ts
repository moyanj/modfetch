import { createRouter, createWebHistory } from 'vue-router';
import ConfigView from '@/views/ConfigView.vue';
import SearchView from '@/views/SearchView.vue';
import BuildView from '@/views/BuildView.vue';
import ResultsView from '@/views/ResultsView.vue';

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'config', component: ConfigView },
    { path: '/search', name: 'search', component: SearchView },
    { path: '/build/:id', name: 'build', component: BuildView },
    { path: '/results/:id', name: 'results', component: ResultsView },
  ],
});

export default router;
