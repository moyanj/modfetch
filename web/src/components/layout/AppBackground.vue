<template>
  <div class="app-background">
    <div class="app-background__noise"></div>
    <div class="app-background__grid"></div>
  </div>
</template>

<style scoped>
.app-background {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 0;
}

.app-background__noise {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E");
}

.app-background__grid {
  position: absolute;
  inset: 0;
  opacity: 0.03;
  background-image: linear-gradient(var(--border-stone) 1px, transparent 1px), linear-gradient(90deg, var(--border-stone) 1px, transparent 1px);
  background-size: 32px 32px;
}
</style>
