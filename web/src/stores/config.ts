import { defineStore } from 'pinia';
import { ref, computed } from 'vue';
import type { ModFetchConfig, ModEntry, ModLoader, FileType } from '@/types/config';
import { createDefaultConfig } from '@/types/config';

export const useConfigStore = defineStore('config', () => {
  const config = ref<ModFetchConfig>(createDefaultConfig());

  const modCount = computed(() => config.value.minecraft.mods.length);
  const resourcepackCount = computed(() => config.value.minecraft.resourcepacks.length);
  const shaderpackCount = computed(() => config.value.minecraft.shaderpacks.length);
  const extraUrlCount = computed(() => config.value.minecraft.extra_urls.length);

  const buildMatrix = computed(() => {
    const versions = config.value.minecraft.version;
    const loaders = Array.isArray(config.value.minecraft.mod_loader)
      ? config.value.minecraft.mod_loader
      : [config.value.minecraft.mod_loader];
    const combos: { version: string; loader: ModLoader }[] = [];
    for (const version of versions) {
      for (const loader of loaders) {
        combos.push({ version, loader });
      }
    }
    return combos;
  });

  function addMod(slug: string, type: FileType = 'mod') {
    const entry: ModEntry = { slug };
    if (type === 'mod') config.value.minecraft.mods.push(entry);
    else if (type === 'resourcepack') config.value.minecraft.resourcepacks.push(entry);
    else if (type === 'shaderpack') config.value.minecraft.shaderpacks.push(entry);
  }

  function removeMod(index: number, type: FileType = 'mod') {
    if (type === 'mod') config.value.minecraft.mods.splice(index, 1);
    else if (type === 'resourcepack') config.value.minecraft.resourcepacks.splice(index, 1);
    else if (type === 'shaderpack') config.value.minecraft.shaderpacks.splice(index, 1);
  }

  function updateMod(index: number, type: FileType, patch: Partial<ModEntry>) {
    let target: (string | ModEntry)[] = [];
    if (type === 'mod') target = config.value.minecraft.mods;
    else if (type === 'resourcepack') target = config.value.minecraft.resourcepacks;
    else if (type === 'shaderpack') target = config.value.minecraft.shaderpacks;

    const item = target[index];
    if (typeof item === 'object') {
      target[index] = { ...item, ...patch };
    }
  }

  function addExtraUrl(url: string) {
    config.value.minecraft.extra_urls.push({ url });
  }

  function removeExtraUrl(index: number) {
    config.value.minecraft.extra_urls.splice(index, 1);
  }

  function validate(): string[] {
    const errors: string[] = [];
    if (!config.value.minecraft.version.length) errors.push('必须选择至少一个 Minecraft 版本');
    if (!config.value.minecraft.mods.length) errors.push('必须添加至少一个模组');
    return errors;
  }

  function loadFromJson(json: ModFetchConfig) {
    config.value = json;
  }

  function exportToml(): string {
    return JSON.stringify(config.value, null, 2);
  }

  return {
    config,
    modCount,
    resourcepackCount,
    shaderpackCount,
    extraUrlCount,
    buildMatrix,
    addMod,
    removeMod,
    updateMod,
    addExtraUrl,
    removeExtraUrl,
    validate,
    loadFromJson,
    exportToml,
  };
});
