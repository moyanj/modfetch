<script setup lang="ts">
interface Props {
  type: 'mod' | 'resourcepack' | 'shader' | 'forge' | 'fabric' | 'neoforge' | 'quilt' | 'success' | 'warning' | 'error' | 'datapack';
}

const props = defineProps<Props>();

const labelMap: Record<string, string> = {
  mod: 'MOD',
  resourcepack: '资源包',
  shader: '光影',
  forge: 'Forge',
  neoforge: 'NeoForge',
  fabric: 'Fabric',
  quilt: 'Quilt',
  success: '✓',
  warning: '!',
  error: '×',
  datapack: '数据包',
};

const colorMap: Record<string, string> = {
  mod: 'var(--primary)',
  resourcepack: 'var(--accent-diamond)',
  shader: 'var(--accent-gold)',
  forge: 'var(--accent-torch)',
  neoforge: 'var(--accent-torch)',
  fabric: 'var(--primary)',
  quilt: 'var(--accent-lapis)',
  success: 'var(--status-success)',
  warning: 'var(--status-warning)',
  error: 'var(--status-error)',
  datapack: 'var(--accent-emerald)',
};
</script>

<template>
  <span
    class="mc-badge"
    :style="{
      backgroundColor: `${colorMap[props.type]}33`,
      borderColor: `${colorMap[props.type]}99`,
      color: colorMap[props.type],
    }"
  >
    {{ labelMap[props.type] || props.type.toUpperCase() }}
  </span>
</template>

<style scoped>
.mc-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 2px 8px;
  font-family: 'Silkscreen', monospace;
  font-size: 9px;
  line-height: 1.4;
  border: 1px solid;
  border-radius: var(--radius-sm);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}
</style>
