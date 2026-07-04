<script setup lang="ts">
interface Props {
  value: number;
  variant?: 'grass' | 'diamond' | 'gold' | 'redstone';
  showLabel?: boolean;
  size?: 'sm' | 'md';
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'grass',
  showLabel: true,
  size: 'md',
});

const variantColors = {
  grass: { fill: 'var(--primary)', glow: 'var(--primary-glow)' },
  diamond: { fill: 'var(--accent-diamond)', glow: 'rgba(77, 208, 225, 0.3)' },
  gold: { fill: 'var(--accent-gold)', glow: 'rgba(255, 215, 0, 0.3)' },
  redstone: { fill: 'var(--accent-redstone)', glow: 'rgba(255, 82, 82, 0.3)' },
};

const clamped = Math.max(0, Math.min(100, props.value));
</script>

<template>
  <div :class="['mc-progress', `mc-progress--${props.size}`]"
       :style="{ '--fill-color': variantColors[props.variant].fill, '--glow-color': variantColors[props.variant].glow }">
    <div class="mc-progress__track">
      <div
        class="mc-progress__fill"
        :style="{ width: `${clamped}%` }"
        role="progressbar"
        :aria-valuenow="clamped"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <div class="mc-progress__texture"></div>
      </div>
      <span v-if="props.showLabel" class="mc-progress__label">
        {{ Math.round(clamped) }}%
      </span>
    </div>
  </div>
</template>

<style scoped>
.mc-progress {
  width: 100%;
}

.mc-progress--sm .mc-progress__track {
  height: 16px;
}

.mc-progress--md .mc-progress__track {
  height: 24px;
}

.mc-progress__track {
  position: relative;
  background-color: var(--bg-inset);
  border: 2px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  overflow: hidden;
  box-shadow: var(--shadow-inset);
}

.mc-progress__fill {
  height: 100%;
  background-color: var(--fill-color);
  border-radius: var(--radius-sm);
  transition: width 0.3s ease;
  position: relative;
  box-shadow: 0 0 8px var(--glow-color);
}

.mc-progress__texture {
  position: absolute;
  inset: 0;
  background-image: repeating-linear-gradient(
    90deg,
    transparent,
    transparent 4px,
    rgba(0,0,0,0.1) 4px,
    rgba(0,0,0,0.1) 8px
  );
  pointer-events: none;
}

.mc-progress__label {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-primary);
  text-shadow: 0 1px 2px rgba(0,0,0,0.8);
  pointer-events: none;
}
</style>
