<script setup lang="ts">
import { useConfigStore } from '@/stores/config';
import McCheckbox from '@/components/ui/McCheckbox.vue';
import McInput from '@/components/ui/McInput.vue';

const configStore = useConfigStore();
</script>

<template>
  <div class="output-form">
    <div class="output-form__field">
      <label class="output-form__label">输出格式</label>
      <div class="output-form__checkboxes">
        <McCheckbox
          :model-value="configStore.config.output.format.includes('mrpack')"
          label="MRPACK"
          @update:model-value="val => {
            const idx = configStore.config.output.format.indexOf('mrpack');
            if (val && idx < 0) configStore.config.output.format.push('mrpack');
            else if (!val && idx >= 0) configStore.config.output.format.splice(idx, 1);
          }"
        />
        <McCheckbox
          :model-value="configStore.config.output.format.includes('zip')"
          label="ZIP"
          @update:model-value="val => {
            const idx = configStore.config.output.format.indexOf('zip');
            if (val && idx < 0) configStore.config.output.format.push('zip');
            else if (!val && idx >= 0) configStore.config.output.format.splice(idx, 1);
          }"
        />
      </div>
    </div>
    <div class="output-form__field">
      <label class="output-form__label">MRPACK 模式</label>
      <div class="output-form__checkboxes">
        <McCheckbox
          :model-value="configStore.config.output.mrpack_modes.includes('download')"
          label="下载 (Download)"
          @update:model-value="val => {
            const idx = configStore.config.output.mrpack_modes.indexOf('download');
            if (val && idx < 0) configStore.config.output.mrpack_modes.push('download');
            else if (!val && idx >= 0) configStore.config.output.mrpack_modes.splice(idx, 1);
          }"
        />
        <McCheckbox
          :model-value="configStore.config.output.mrpack_modes.includes('reference')"
          label="引用 (Reference)"
          @update:model-value="val => {
            const idx = configStore.config.output.mrpack_modes.indexOf('reference');
            if (val && idx < 0) configStore.config.output.mrpack_modes.push('reference');
            else if (!val && idx >= 0) configStore.config.output.mrpack_modes.splice(idx, 1);
          }"
        />
      </div>
    </div>
    <div class="output-form__field">
      <label class="output-form__label">下载目录</label>
      <McInput v-model="configStore.config.output.download_dir" placeholder="downloads" />
    </div>
  </div>
</template>

<style scoped>
.output-form {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.output-form__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.output-form__label {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.output-form__checkboxes {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-4);
}
</style>
