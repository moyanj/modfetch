<script setup lang="ts">
import { ref, watch } from 'vue';
import { useConfigStore } from '@/stores/config';
import type { FileType, ModEntry } from '@/types/config';
import type { ProjectInfo, ValidationSuggestion } from '@/types/api';
import { searchMods } from '@/api/search';
import McButton from '@/components/ui/McButton.vue';
import McInput from '@/components/ui/McInput.vue';
import McTag from '@/components/ui/McTag.vue';

const props = defineProps<{
  type: FileType;
}>();

const configStore = useConfigStore();
const newSlug = ref('');
const expanded = ref<number[]>([]);
const suggestions = ref<ProjectInfo[]>([]);
const searching = ref(false);
let searchTimer: number | undefined;

const listMap: Record<FileType, keyof typeof configStore.config.minecraft> = {
  mod: 'mods',
  resourcepack: 'resourcepacks',
  shaderpack: 'shaderpacks',
  file: 'extra_urls',
};

const items = ref<(string | ModEntry)[]>([]);

function refresh() {
  const key = listMap[props.type];
  items.value = [...((configStore.config.minecraft[key] as (string | ModEntry)[]) || [])];
}

watch(() => configStore.config.minecraft, () => refresh(), { deep: true, immediate: true });
watch(newSlug, (value) => {
  if (searchTimer) window.clearTimeout(searchTimer);
  if (!value.trim()) {
    suggestions.value = [];
    return;
  }
  searchTimer = window.setTimeout(() => {
    void fetchSuggestions(value.trim());
  }, 180);
});

function add() {
  if (!newSlug.value.trim()) return;
  configStore.addMod(newSlug.value.trim(), props.type);
  newSlug.value = '';
  suggestions.value = [];
  refresh();
}

function remove(index: number) {
  configStore.removeMod(index, props.type);
  expanded.value = expanded.value.filter(i => i !== index).map(i => (i > index ? i - 1 : i));
  refresh();
}

function toggleExpanded(index: number) {
  if (expanded.value.includes(index)) {
    expanded.value = expanded.value.filter(i => i !== index);
    return;
  }
  configStore.normalizeMod(index, props.type);
  expanded.value = [...expanded.value, index];
  refresh();
}

function isExpanded(index: number) {
  return expanded.value.includes(index);
}

function getDisplay(item: string | ModEntry): string {
  if (typeof item === 'string') return item;
  return item.slug || item.id || '未知';
}

function getConditions(item: string | ModEntry): string[] {
  if (typeof item === 'string') return [];
  const conds: string[] = [];
  if (item.version) conds.push(`固定版本: ${item.version}`);
  if (item.only_version) conds.push(`MC: ${Array.isArray(item.only_version) ? item.only_version.join(', ') : item.only_version}`);
  if (item.feature) conds.push(`特性: ${Array.isArray(item.feature) ? item.feature.join(', ') : item.feature}`);
  return conds;
}

function asEntry(item: string | ModEntry): ModEntry {
  if (typeof item === 'string') return { slug: item };
  return item;
}

function formatMultiValue(value?: string | string[]) {
  if (!value) return '';
  return Array.isArray(value) ? value.join(', ') : value;
}

function parseMultiValue(value: string): string | string[] | undefined {
  const parts = value.split(',').map(part => part.trim()).filter(Boolean);
  if (parts.length === 0) return undefined;
  if (parts.length === 1) return parts[0];
  return parts;
}

function updateField(index: number, patch: Partial<ModEntry>) {
  configStore.updateMod(index, props.type, patch);
  refresh();
}

function issueKey(index: number) {
  const group = props.type === 'mod'
    ? 'mods'
    : props.type === 'resourcepack'
      ? 'resourcepacks'
      : 'shaderpacks';
  return `minecraft.${group}[${index}]`;
}

function getIssue(index: number) {
  return configStore.getValidationIssue(issueKey(index));
}

function applySuggestion(suggestion: ProjectInfo | ValidationSuggestion, index?: number) {
  const slug = 'name' in suggestion ? suggestion.name : suggestion.slug;
  if (typeof index === 'number') {
    updateField(index, { slug, id: undefined });
    return;
  }
  newSlug.value = slug;
  suggestions.value = [];
}

async function fetchSuggestions(query: string) {
  searching.value = true;
  try {
    const primaryLoader = Array.isArray(configStore.config.minecraft.mod_loader)
      ? configStore.config.minecraft.mod_loader[0]
      : configStore.config.minecraft.mod_loader;
    const primaryVersion = configStore.config.minecraft.version[0];
    const result = await searchMods(query, {
      type: props.type === 'shaderpack' ? 'shader' : props.type,
      loader: props.type === 'mod' ? primaryLoader : undefined,
      version: primaryVersion,
    }, 0, 5);
    suggestions.value = result.hits;
  } finally {
    searching.value = false;
  }
}
</script>

<template>
  <div class="mod-list">
    <div class="mod-list__add">
      <McInput v-model="newSlug" placeholder="输入模组 slug 或 ID..." @keyup.enter="add" />
      <McButton variant="primary" size="sm" @click="add">添加</McButton>
    </div>
    <div v-if="newSlug.trim()" class="mod-list__suggestions">
      <div v-if="searching" class="mod-list__suggestion-empty">搜索中...</div>
      <button
        v-for="suggestion in suggestions"
        :key="suggestion.id"
        class="mod-list__suggestion"
        @click="applySuggestion(suggestion)"
      >
        <span class="mod-list__suggestion-name">{{ suggestion.title || suggestion.name }}</span>
        <span class="mod-list__suggestion-slug">{{ suggestion.name }}</span>
      </button>
      <div v-if="!searching && suggestions.length === 0" class="mod-list__suggestion-empty">
        没有候选
      </div>
    </div>
    <div class="mod-list__items">
      <div v-for="(item, index) in items" :key="index" class="mod-list__item">
        <div class="mod-list__row">
          <div class="mod-list__info">
            <span class="mod-list__name">{{ getDisplay(item) }}</span>
            <div class="mod-list__conditions">
              <McTag v-for="cond in getConditions(item)" :key="cond" type="mod">{{ cond }}</McTag>
            </div>
          </div>
          <div class="mod-list__actions">
            <button class="mod-list__toggle" @click="toggleExpanded(index)">
              {{ isExpanded(index) ? '收起' : '编辑' }}
            </button>
            <button class="mod-list__remove" @click="remove(index)">
              <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="4" y1="4" x2="12" y2="12" />
                <line x1="12" y1="4" x2="4" y2="12" />
              </svg>
            </button>
          </div>
        </div>

        <div v-if="isExpanded(index)" class="mod-list__editor">
          <div class="mod-list__grid">
            <div class="mod-list__field">
              <label class="mod-list__label">Slug</label>
              <McInput
                :model-value="asEntry(item).slug ?? ''"
                placeholder="例如 sodium"
                @update:model-value="val => updateField(index, { slug: val.trim() || undefined })"
              />
            </div>
            <div class="mod-list__field">
              <label class="mod-list__label">ID</label>
              <McInput
                :model-value="asEntry(item).id ?? ''"
                placeholder="例如 AANobbMI"
                @update:model-value="val => updateField(index, { id: val.trim() || undefined })"
              />
            </div>
            <div class="mod-list__field mod-list__field--full">
              <label class="mod-list__label">模组版本固定</label>
              <McInput
                :model-value="asEntry(item).version ?? ''"
                placeholder="输入 Modrinth 版本号或发布版本字符串"
                @update:model-value="val => updateField(index, { version: val.trim() || undefined })"
              />
            </div>
            <div class="mod-list__field">
              <label class="mod-list__label">仅限 MC 版本</label>
              <McInput
                :model-value="formatMultiValue(asEntry(item).only_version)"
                placeholder="例如 1.20.1, 1.21.1"
                @update:model-value="val => updateField(index, { only_version: parseMultiValue(val) })"
              />
            </div>
            <div class="mod-list__field">
              <label class="mod-list__label">所需 Features</label>
              <McInput
                :model-value="formatMultiValue(asEntry(item).feature)"
                placeholder="例如 client, opt-in"
                @update:model-value="val => updateField(index, { feature: parseMultiValue(val) })"
              />
            </div>
          </div>
        </div>
        <div v-if="getIssue(index)" class="mod-list__issue">
          <p class="mod-list__issue-text">{{ getIssue(index)?.message }}</p>
          <div v-if="getIssue(index)?.suggestions?.length" class="mod-list__issue-suggestions">
            <button
              v-for="suggestion in getIssue(index)?.suggestions"
              :key="`${index}-${suggestion.project_id}`"
              class="mod-list__issue-suggestion"
              @click="applySuggestion(suggestion, index)"
            >
              使用 {{ suggestion.slug }}
            </button>
          </div>
        </div>
      </div>
      <div v-if="items.length === 0" class="mod-list__empty">暂无项目</div>
    </div>
  </div>
</template>

<style scoped>
.mod-list__add {
  display: flex;
  gap: var(--space-2);
  margin-bottom: var(--space-3);
}

.mod-list__items {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  max-height: 420px;
  overflow-y: auto;
}

.mod-list__suggestions {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  margin-bottom: var(--space-3);
  padding: var(--space-2);
  background-color: rgba(18, 26, 25, 0.92);
  border: 1px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
}

.mod-list__suggestion {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  width: 100%;
  padding: var(--space-2) var(--space-3);
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  text-align: left;
  cursor: pointer;
}

.mod-list__suggestion:hover {
  border-color: var(--border-glow);
  background-color: rgba(77, 208, 225, 0.08);
}

.mod-list__suggestion-name {
  font-family: 'Outfit', sans-serif;
}

.mod-list__suggestion-slug,
.mod-list__suggestion-empty {
  color: var(--text-secondary);
  font-size: 12px;
}

.mod-list__item {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background-color: var(--bg-inset);
  border: 1px solid var(--border-stone-dark);
  border-radius: var(--radius-sm);
  transition: border-color var(--transition-fast);
}

.mod-list__item:hover {
  border-color: var(--border-stone);
}

.mod-list__row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
}

.mod-list__info {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
  flex: 1;
  min-width: 0;
}

.mod-list__name {
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
  color: var(--text-primary);
  word-break: break-all;
}

.mod-list__conditions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-1);
}

.mod-list__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.mod-list__toggle {
  padding: var(--space-2) var(--space-3);
  background-color: var(--bg-surface);
  border: 1px solid var(--border-stone);
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  cursor: pointer;
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  text-transform: uppercase;
}

.mod-list__toggle:hover {
  color: var(--text-primary);
  border-color: var(--border-glow);
}

.mod-list__remove {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  transition: color var(--transition-fast);
}

.mod-list__remove:hover {
  color: var(--accent-redstone);
}

.mod-list__remove svg {
  width: 14px;
  height: 14px;
}

.mod-list__editor {
  border-top: 1px solid var(--border-stone-dark);
  padding-top: var(--space-3);
}

.mod-list__issue {
  padding: var(--space-3);
  background-color: rgba(157, 46, 46, 0.12);
  border: 1px solid rgba(221, 88, 88, 0.35);
  border-radius: var(--radius-sm);
}

.mod-list__issue-text {
  color: #ffb3b3;
  font-size: 12px;
}

.mod-list__issue-suggestions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-top: var(--space-2);
}

.mod-list__issue-suggestion {
  padding: var(--space-1) var(--space-2);
  border: 1px solid rgba(255, 179, 179, 0.35);
  border-radius: var(--radius-sm);
  background: transparent;
  color: #ffd3d3;
  font-size: 12px;
  cursor: pointer;
}

.mod-list__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-3);
}

.mod-list__field {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.mod-list__field--full {
  grid-column: 1 / -1;
}

.mod-list__label {
  font-family: 'Silkscreen', monospace;
  font-size: 10px;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.mod-list__empty {
  text-align: center;
  padding: var(--space-6);
  color: var(--text-muted);
  font-family: 'Outfit', sans-serif;
  font-size: 14px;
}

@media (max-width: 720px) {
  .mod-list__grid {
    grid-template-columns: 1fr;
  }

  .mod-list__row {
    flex-direction: column;
  }

  .mod-list__actions {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
