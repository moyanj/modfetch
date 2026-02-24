<template>
  <div id="app">
    <el-container class="generator-container">
      <el-header class="header">
        <h1>ModFetch 配置生成器</h1>
      </el-header>
      <el-main class="main-content">
        <el-form :model="config" label-width="150px" label-position="right" class="config-form">

          <!-- From 配置 -->
          <el-card class="box-card section-card">
            <template #header>
              <div class="card-header">
                <span><el-icon>
                    <Link />
                  </el-icon> From - 配置源继承</span>
                <el-button type="primary" :icon="Plus" circle size="small" @click="addFromItem"></el-button>
              </div>
            </template>
            <el-form-item v-for="(item, index) in config.from" :key="index" :label="`配置源 ${index + 1}`">
              <el-row :gutter="20" style="width: 100%;">
                <el-col :span="10">
                  <el-input v-model="item.url" placeholder="URL (file:// or http(s)://)" size="small"></el-input>
                </el-col>
                <el-col :span="8">
                  <el-select v-model="item.format" placeholder="格式" size="small">
                    <el-option label="toml" value="toml"></el-option>
                    <el-option label="json" value="json"></el-option>
                    <el-option label="yaml" value="yaml"></el-option>
                    <el-option label="xml" value="xml"></el-option>
                  </el-select>
                </el-col>
                <el-col :span="2">
                  <el-button type="danger" :icon="Remove" circle size="small"
                    @click="removeFromItem(index)"></el-button>
                </el-col>
              </el-row>
            </el-form-item>
          </el-card>

          <!-- Metadata 配置 -->
          <el-card class="box-card section-card">
            <template #header>
              <div class="card-header">
                <span><el-icon>
                    <InfoFilled />
                  </el-icon> Metadata - 整合包元数据</span>
              </div>
            </template>
            <el-form-item label="名称">
              <el-input v-model="config.metadata.name" placeholder="整合包名称"></el-input>
            </el-form-item>
            <el-form-item label="版本号">
              <el-input v-model="config.metadata.version" placeholder="包版本号 (例如 'v1.2.0')"></el-input>
            </el-form-item>
            <el-form-item label="描述">
              <el-input type="textarea" v-model="config.metadata.description" placeholder="简要描述整合包内容"></el-input>
            </el-form-item>
            <el-form-item label="作者">
              <el-row v-for="(author, index) in config.metadata.authors" :key="index" :gutter="10"
                style="margin-bottom: 5px;">
                <el-col :span="20">
                  <el-input v-model="config.metadata.authors[index]" placeholder="作者姓名"></el-input>
                </el-col>
                <el-col :span="2">
                  <el-button type="danger" :icon="Minus" circle size="small" @click="removeAuthor(index)"></el-button>
                </el-col>
              </el-row>
              <el-button type="primary" :icon="Plus" size="small" @click="addAuthor">添加作者</el-button>
            </el-form-item>
          </el-card>

          <!-- Minecraft 配置 -->
          <el-card class="box-card section-card">
            <template #header>
              <div class="card-header">
                <span><el-icon>
                    <VideoCamera />
                  </el-icon> Minecraft - 游戏客户端核心配置</span>
              </div>
            </template>
            <el-form-item label="Minecraft 版本">
              <el-select v-model="config.minecraft.version" multiple filterable allow-create default-first-option
                placeholder="选择或输入 Minecraft 版本" style="width: 100%;">
                <el-option v-for="item in commonMinecraftVersions" :key="item" :label="item" :value="item"></el-option>
              </el-select>
              <el-text class="mx-1" type="info">可选择多个版本，或输入自定义版本。<p>例如：["1.21.1", "1.20.4"]</p></el-text>
            </el-form-item>
            <el-form-item label="模组加载器">
              <el-select v-model="config.minecraft.mod_loader" multiple placeholder="选择模组加载器" style="width: 100%;">
                <el-option label="fabric" value="fabric"></el-option>
                <el-option label="forge" value="forge"></el-option>
                <el-option label="neoforge" value="neoforge"></el-option>
                <el-option label="quilt" value="quilt"></el-option>
              </el-select>
            </el-form-item>

            <!-- 模组 Mods -->
            <el-divider><el-icon>
                <Box />
              </el-icon> 模组列表</el-divider>
            <el-form-item label-width="0px">
              <el-button type="success" :icon="Plus" size="small" @click="addModItem">添加模组</el-button>
            </el-form-item>
            <div v-for="(mod, index) in config.minecraft.mods" :key="`mod-${index}`" class="item-card">
              <el-card>
                <template #header>
                  <div class="card-header-item">
                    <span>模组 {{ index + 1 }}</span>
                    <el-button type="danger" :icon="Delete" circle size="small"
                      @click="removeModItem(index)"></el-button>
                  </div>
                </template>
                <el-form-item label="ID / Slug">
                  <el-input v-model="mod.id" placeholder="Modrinth 项目 ID 或 slug"></el-input>
                </el-form-item>
                <el-form-item label="限定版本">
                  <el-select v-model="mod.only_version" multiple filterable allow-create default-first-option
                    placeholder="限定 Minecraft 版本 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonMinecraftVersions" :key="item" :label="item"
                      :value="item"></el-option>
                  </el-select>
                </el-form-item>
                <el-form-item label="特性标签">
                  <el-select v-model="mod.feature" multiple filterable allow-create default-first-option
                    placeholder="添加特性标签 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonFeatures" :key="item" :label="item" :value="item"></el-option>
                  </el-select>
                </el-form-item>
              </el-card>
            </div>

            <!-- 资源包 Resourcepacks -->
            <el-divider><el-icon>
                <Picture />
              </el-icon> 资源包列表</el-divider>
            <el-form-item label-width="0px">
              <el-button type="success" :icon="Plus" size="small" @click="addResourcepackItem">添加资源包</el-button>
            </el-form-item>
            <div v-for="(rp, index) in config.minecraft.resourcepacks" :key="`rp-${index}`" class="item-card">
              <el-card>
                <template #header>
                  <div class="card-header-item">
                    <span>资源包 {{ index + 1 }}</span>
                    <el-button type="danger" :icon="Delete" circle size="small"
                      @click="removeResourcepackItem(index)"></el-button>
                  </div>
                </template>
                <el-form-item label="ID / Slug">
                  <el-input v-model="rp.id" placeholder="Modrinth 项目 ID 或 slug"></el-input>
                </el-form-item>
                <el-form-item label="限定版本">
                  <el-select v-model="rp.only_version" multiple filterable allow-create default-first-option
                    placeholder="限定 Minecraft 版本 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonMinecraftVersions" :key="item" :label="item"
                      :value="item"></el-option>
                  </el-select>
                </el-form-item>
                <el-form-item label="特性标签">
                  <el-select v-model="rp.feature" multiple filterable allow-create default-first-option
                    placeholder="添加特性标签 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonFeatures" :key="item" :label="item" :value="item"></el-option>
                  </el-select>
                </el-form-item>
              </el-card>
            </div>

            <!-- 光影包 Shaderpacks -->
            <el-divider><el-icon>
                <MagicStick />
              </el-icon> 光影包列表</el-divider>
            <el-form-item label-width="0px">
              <el-button type="success" :icon="Plus" size="small" @click="addShaderpackItem">添加光影包</el-button>
            </el-form-item>
            <div v-for="(sp, index) in config.minecraft.shaderpacks" :key="`sp-${index}`" class="item-card">
              <el-card>
                <template #header>
                  <div class="card-header-item">
                    <span>光影包 {{ index + 1 }}</span>
                    <el-button type="danger" :icon="Delete" circle size="small"
                      @click="removeShaderpackItem(index)"></el-button>
                  </div>
                </template>
                <el-form-item label="ID / Slug">
                  <el-input v-model="sp.id" placeholder="Modrinth 项目 ID 或 slug"></el-input>
                </el-form-item>
                <el-form-item label="限定版本">
                  <el-select v-model="sp.only_version" multiple filterable allow-create default-first-option
                    placeholder="限定 Minecraft 版本 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonMinecraftVersions" :key="item" :label="item"
                      :value="item"></el-option>
                  </el-select>
                </el-form-item>
                <el-form-item label="特性标签">
                  <el-select v-model="sp.feature" multiple filterable allow-create default-first-option
                    placeholder="添加特性标签 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonFeatures" :key="item" :label="item" :value="item"></el-option>
                  </el-select>
                </el-form-item>
              </el-card>
            </div>


            <!-- 额外文件 extra_urls -->
            <el-divider><el-icon>
                <FolderAdd />
              </el-icon> 额外文件 (External Files)</el-divider>
            <el-form-item label-width="0px">
              <el-button type="success" :icon="Plus" size="small" @click="addExtraUrlItem">添加额外文件</el-button>
            </el-form-item>
            <div v-for="(extraFile, index) in config.minecraft.extra_urls" :key="`extra-${index}`" class="item-card">
              <el-card>
                <template #header>
                  <div class="card-header-item">
                    <span>额外文件 {{ index + 1 }}</span>
                    <el-button type="danger" :icon="Delete" circle size="small"
                      @click="removeExtraUrlItem(index)"></el-button>
                  </div>
                </template>
                <el-form-item label="URL">
                  <el-input v-model="extraFile.url" placeholder="文件下载地址 (支持 file://)"></el-input>
                </el-form-item>
                <el-form-item label="文件名 (可选)">
                  <el-input v-model="extraFile.filename" placeholder="文件保存名 (默认为原始文件名)"></el-input>
                </el-form-item>
                <el-form-item label="文件类型">
                  <el-select v-model="extraFile.type" placeholder="选择文件类型" style="width: 100%;">
                    <el-option label="mod" value="mod"></el-option>
                    <el-option label="resourcepack" value="resourcepack"></el-option>
                    <el-option label="shaderpack" value="shaderpack"></el-option>
                    <el-option label="file" value="file"></el-option>
                  </el-select>
                </el-form-item>
                <el-form-item label="SHA1 校验 (可选)">
                  <el-input v-model="extraFile.sha1" placeholder="SHA1 校验，防止文件重复或损坏"></el-input>
                </el-form-item>
                <el-form-item label="限定版本">
                  <el-select v-model="extraFile.only_version" multiple filterable allow-create default-first-option
                    placeholder="指定版本触发下载的条件 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonMinecraftVersions" :key="item" :label="item"
                      :value="item"></el-option>
                  </el-select>
                </el-form-item>
                <el-form-item label="特性标签">
                  <el-select v-model="extraFile.feature" multiple filterable allow-create default-first-option
                    placeholder="运行时特征筛选 (可选)" style="width: 100%;">
                    <el-option v-for="item in commonFeatures" :key="item" :label="item" :value="item"></el-option>
                  </el-select>
                </el-form-item>
              </el-card>
            </div>

          </el-card>

          <!-- Output 配置 -->
          <el-card class="box-card section-card">
            <template #header>
              <div class="card-header">
                <span><el-icon>
                    <Download />
                  </el-icon> Output - 输出配置</span>
              </div>
            </template>
            <el-form-item label="下载目录">
              <el-input v-model="config.output.download_dir" placeholder="最终文件存储目录，例如 ./modpacks"></el-input>
            </el-form-item>
            <el-form-item label="输出格式">
              <el-select v-model="config.output.format" multiple placeholder="选择输出格式" style="width: 100%;">
                <el-option label="zip" value="zip"></el-option>
                <el-option label="mrpack" value="mrpack"></el-option>
              </el-select>
            </el-form-item>
          </el-card>

        </el-form>

        <el-card class="box-card generated-output section-card">
          <template #header>
            <div class="card-header">
              <span><el-icon>
                  <Tickets />
                </el-icon> 生成的 TOML 配置</span>
              <el-button type="primary" :icon="DocumentCopy" circle size="small" @click="copyConfig"></el-button>
            </div>
          </template>
          <pre v-if="generatedConfig" class="toml-output">{{ generatedConfig }}</pre>
          <pre v-else class="toml-output no-content">请填写配置信息...</pre>
        </el-card>

        <el-button type="success" size="large" :icon="Cpu" @click="generateConfig" class="generate-button">
          生成配置文件
        </el-button>
      </el-main>
    </el-container>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue';
import { ElMessage } from 'element-plus';
import {
  Link, InfoFilled, VideoCamera, Download, Plus, Minus, Delete, Box, Picture, MagicStick, FolderAdd,
  DocumentCopy, Cpu, Remove
} from '@element-plus/icons-vue';

// 初始配置数据结构
const config = reactive({
  from: [],
  metadata: {
    name: '',
    version: '',
    description: '',
    authors: [],
  },
  minecraft: {
    version: [],
    mod_loader: [],
    mods: [],
    resourcepacks: [],
    shaderpacks: [],
    extra_urls: [],
  },
  output: {
    download_dir: '',
    format: [],
  },
});

const generatedConfig = ref('');

// 常用 Minecraft 版本和特性标签（用于选择器提示）
const commonMinecraftVersions = ref([
  '1.21.1', '1.20.4', '1.19.2', '1.18.2', '1.16.5'
]);
const commonFeatures = ref([
  'performance', 'shader', 'utility', 'qol', 'texture', 'debug'
]);

// From D&D
const addFromItem = () => {
  config.from.push({ url: '', format: 'toml' });
};
const removeFromItem = (index) => {
  config.from.splice(index, 1);
};

// Metadata D&D
const addAuthor = () => {
  config.metadata.authors.push('');
};
const removeAuthor = (index) => {
  config.metadata.authors.splice(index, 1);
};

// Mod/Resourcepack/Shaderpack D&D (Minecraft section)
const addModItem = () => {
  config.minecraft.mods.push({ id: '', only_version: [], feature: [], sha1: '' });
};
const removeModItem = (index) => {
  config.minecraft.mods.splice(index, 1);
};

const addResourcepackItem = () => {
  config.minecraft.resourcepacks.push({ id: '', only_version: [], feature: [] });
};
const removeResourcepackItem = (index) => {
  config.minecraft.resourcepacks.splice(index, 1);
};

const addShaderpackItem = () => {
  config.minecraft.shaderpacks.push({ id: '', only_version: [], feature: [] });
};
const removeShaderpackItem = (index) => {
  config.minecraft.shaderpacks.splice(index, 1);
};

const addExtraUrlItem = () => {
  config.minecraft.extra_urls.push({
    url: '',
    filename: '',
    type: 'file',
    sha1: '',
    only_version: [],
    feature: [],
  });
};
const removeExtraUrlItem = (index) => {
  config.minecraft.extra_urls.splice(index, 1);
};


// 核心生成逻辑，将 JS 对象转换为 TOML 字符串
const generateConfig = () => {
  let toml = '';

  // Helper function for TOML string escaping
  const toTomlString = (value) => {
    if (typeof value === 'string') {
      return `"${value.replace(/"/g, '\\"')}"`; // Escape double quotes
    }
    return value;
  };

  // Helper function for TOML array formatting
  const toTomlArray = (arr) => {
    if (!arr || arr.length === 0) return '';
    const formatted = arr.map(item => toTomlString(item)).join(', ');
    return `[${formatted}]`;
  };

  // From Section
  if (config.from.length > 0) {
    toml += '[from]\n';
    if (config.from.length === 1) {
      const item = config.from[0];
      if (item.url) toml += `url = ${toTomlString(item.url)}\n`;
      if (item.format) toml += `format = ${toTomlString(item.format)}\n`;
    } else {
      config.from.forEach(item => {
        toml += '[[from]]\n';
        if (item.url) toml += `url = ${toTomlString(item.url)}\n`;
        if (item.format) toml += `format = ${toTomlString(item.format)}\n`;
      });
    }
    toml += '\n';
  }

  // Metadata Section
  if (config.metadata.name || config.metadata.version || config.metadata.description || config.metadata.authors.length > 0) {
    toml += '[metadata]\n';
    if (config.metadata.name) toml += `name = ${toTomlString(config.metadata.name)}\n`;
    if (config.metadata.version) toml += `version = ${toTomlString(config.metadata.version)}\n`;
    if (config.metadata.description) toml += `description = ${toTomlString(config.metadata.description)}\n`;
    if (config.metadata.authors.length > 0) toml += `authors = ${toTomlArray(config.metadata.authors)}\n`;
    toml += '\n';
  }

  // Minecraft Section
  if (config.minecraft.version.length > 0 || config.minecraft.mod_loader.length > 0 ||
    config.minecraft.mods.length > 0 || config.minecraft.resourcepacks.length > 0 ||
    config.minecraft.shaderpacks.length > 0 || config.minecraft.extra_urls.length > 0) {
    toml += '[minecraft]\n';
    if (config.minecraft.version.length > 0) toml += `version = ${toTomlArray(config.minecraft.version)}\n`;
    if (config.minecraft.mod_loader.length > 0) {
      if (config.minecraft.mod_loader.length === 1) {
        toml += `mod_loader = ${toTomlString(config.minecraft.mod_loader[0])}\n`;
      } else {
        toml += `mod_loader = ${toTomlArray(config.minecraft.mod_loader)}\n`;
      }
    }

    // Mods
    if (config.minecraft.mods.length > 0) {
      toml += '\nmods = [\n';
      config.minecraft.mods.forEach(mod => {
        if (mod.only_version.length === 0 && mod.feature.length === 0 && !mod.sha1) {
          // Simple string form
          toml += `    ${toTomlString(mod.id)},\n`;
        } else {
          // Table form
          toml += '    {\n';
          if (mod.id) toml += `        id = ${toTomlString(mod.id)},\n`;
          if (mod.only_version.length > 0) toml += `        only_version = ${toTomlArray(mod.only_version)},\n`;
          if (mod.feature.length > 0) toml += `        feature = ${toTomlArray(mod.feature)},\n`;
          if (mod.sha1) toml += `        sha1 = ${toTomlString(mod.sha1)},\n`;
          toml += '    },\n';
        }
      });
      toml += ']\n';
    }

    // Resourcepacks
    if (config.minecraft.resourcepacks.length > 0) {
      toml += '\nresourcepacks = [\n';
      config.minecraft.resourcepacks.forEach(rp => {
        if (rp.only_version.length === 0 && rp.feature.length === 0) {
          // Simple string form (not explicitly shown in doc for RP, but follows mod pattern)
          toml += `    ${toTomlString(rp.id)},\n`;
        } else {
          // Table form
          toml += '    {\n';
          if (rp.id) toml += `        id = ${toTomlString(rp.id)},\n`;
          if (rp.only_version.length > 0) toml += `        only_version = ${toTomlArray(rp.only_version)},\n`;
          if (rp.feature.length > 0) toml += `        feature = ${toTomlArray(rp.feature)},\n`;
          toml += '    },\n';
        }
      });
      toml += ']\n';
    }

    // Shaderpacks (Assuming similar structure to resourcepacks based on `mods` example)
    if (config.minecraft.shaderpacks.length > 0) {
      toml += '\nshaderpacks = [\n';
      config.minecraft.shaderpacks.forEach(sp => {
        if (sp.only_version.length === 0 && sp.feature.length === 0) {
          // Simple string form
          toml += `    ${toTomlString(sp.id)},\n`;
        } else {
          // Table form
          toml += '    {\n';
          if (sp.id) toml += `        id = ${toTomlString(sp.id)},\n`;
          if (sp.only_version.length > 0) toml += `        only_version = ${toTomlArray(sp.only_version)},\n`;
          if (sp.feature.length > 0) toml += `        feature = ${toTomlArray(sp.feature)},\n`;
          toml += '    },\n';
        }
      });
      toml += ']\n';
    }


    // Extra URLs
    if (config.minecraft.extra_urls.length > 0) {
      toml += '\nextra_urls = [\n';
      config.minecraft.extra_urls.forEach(extraFile => {
        toml += '    {\n';
        if (extraFile.url) toml += `        url = ${toTomlString(extraFile.url)},\n`;
        if (extraFile.filename) toml += `        filename = ${toTomlString(extraFile.filename)},\n`;
        if (extraFile.type) toml += `        type = ${toTomlString(extraFile.type)},\n`;
        if (extraFile.sha1) toml += `        sha1 = ${toTomlString(extraFile.sha1)},\n`;
        if (extraFile.only_version.length > 0) toml += `        only_version = ${toTomlArray(extraFile.only_version)},\n`;
        if (extraFile.feature.length > 0) toml += `        feature = ${toTomlArray(extraFile.feature)},\n`;
        toml += '    },\n';
      });
      toml += ']\n';
    }
    toml += '\n';
  }

  // Output Section
  if (config.output.download_dir || config.output.format.length > 0) {
    toml += '[output]\n';
    if (config.output.download_dir) toml += `download_dir = ${toTomlString(config.output.download_dir)}\n`;
    if (config.output.format.length > 0) toml += `format = ${toTomlArray(config.output.format)}\n`;
    toml += '\n';
  }

  generatedConfig.value = toml.trim(); // Trim any trailing newlines
};

// 自动生成配置 (可选，可以在每次数据变化时触发)
watch(config, generateConfig, { deep: true, immediate: true });

// 复制配置到剪贴板
const copyConfig = async () => {
  try {
    if (generatedConfig.value) {
      await navigator.clipboard.writeText(generatedConfig.value);
      ElMessage({
        message: '配置已成功复制到剪贴板！',
        type: 'success',
      });
    } else {
      ElMessage({
        message: '没有可复制的配置内容。',
        type: 'warning',
      });
    }
  } catch (err) {
    ElMessage({
      message: '复制失败！请手动复制。',
      type: 'error',
    });
    console.error('Failed to copy: ', err);
  }
};
</script>

<style>
/* 全局滚动条样式 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  z-index: 10;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.3);
}

/* Firefox滚动条样式 */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
}

#app {
  font-family: 'Inter', sans-serif, Avenir, Helvetica, Arial;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: #333;
  background-color: #f7f9fc;
  min-height: 100vh;
}

.generator-container {
  max-width: 1000px;
  margin: 0 auto;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  border-radius: 8px;
  overflow: hidden;
  background-color: #fff;
}

.header {
  background-color: #409EFF;
  /* Element Plus Primary Blue */
  color: white;
  text-align: center;
  padding: 20px;
  border-bottom: 2px solid #337ecc;
  /* 添加 flexbox 布局以更好地居中内容 */
  display: flex;
  /* 让内容在主轴上对齐 */
  justify-content: center;
  /* 水平居中 */
  align-items: center;
  /* 垂直居中 */
}

.header h1 {
  /* margin: 0;  // 这一行在原有代码中已存在，但可能不够强效 */
  margin: 0;
  /* 确保无外边距，防止溢出 */
  padding: 0;
  /* 确保无内边距，防止溢出 */
  font-size: 2.2em;
  /* 保持 H1 大小 */
  letter-spacing: 1px;
  white-space: nowrap;
  /* 防止文本换行，强制在同一行显示 */
  overflow: hidden;
  /* 隐藏溢出部分（虽然有了 justify-content 应该不会再溢出） */
  text-overflow: ellipsis;
  /* 如果溢出，显示省略号（不一定需要，但以防万一） */
  width: 100%;
  /* 确保 H1 占据可用宽度 */
}

.main-content {
  padding: 30px;
}

.config-form {
  margin-bottom: 30px;
}

.section-card {
  margin-bottom: 25px;
  border-radius: 8px;
  border: 1px solid #ebeef5;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 1.1em;
  font-weight: bold;
  color: #303133;
}

.card-header span {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-card {
  margin-bottom: 15px;
  border-radius: 6px;
  border: 1px solid #ebeef5;
  background-color: #fcfcfc;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}

.item-card .el-card__header {
  background-color: #f5f7fa;
  padding: 10px 20px;
}

.item-card .el-card__body {
  padding: 20px;
}

.card-header-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 1em;
  color: #606266;
  font-weight: normal;
}

.el-form-item {
  margin-bottom: 18px;
}

.el-form-item.is-error .el-input__inner,
.el-form-item.is-error .el-textarea__inner {
  border-color: #F56C6C;
}

.el-divider {
  margin: 30px 0;
  border-color: #dcdfe6;
}

.el-button+.el-button {
  margin-left: 10px;
}

.toml-output {
  background-color: #f0f4f7;
  border-radius: 6px;
  padding: 20px;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'Source Code Pro', monospace;
  /* Modern monospace font */
  font-size: 0.95em;
  line-height: 1.5;
  color: #333;
  white-space: pre-wrap;
  /* Preserves whitespace and wraps long lines */
  word-break: break-all;
  /* Ensures long words break */
}

.toml-output.no-content {
  color: #999;
  text-align: center;
  font-style: italic;
  padding: 50px;
}

.generate-button {
  width: 100%;
  margin-top: 20px;
  padding: 15px 0;
  font-size: 1.2em;
}

/* 覆盖 Element Plus 的多选框样式，使之更紧凑 */
.el-select-dropdown__item {
  padding: 0 20px;
  line-height: 34px;
  height: 34px;
}

.el-select__tags-text {
  max-width: 150px;
  /* Limit tag width to prevent overflow */
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.el-input__inner {
  height: 32px;
  /* Make input fields slightly smaller */
}

/* Info text below select */
.el-text.mx-1 {
  font-size: 0.85em;
  color: #909399;
  margin-top: 5px;
  display: block;
}

.el-text.mx-1 p {
  margin: 0;
  line-height: 1.2;
}

/* 优化滚动条样式 - 不占用空间 */
::-webkit-scrollbar {
  width: 8px;
  height: 8px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  z-index: 10;
  background-color: rgba(0, 0, 0, 0.2);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background-color: rgba(0, 0, 0, 0.3);
}

html {
  overflow-y: overlay;
  scrollbar-width: thin;
  scrollbar-color: rgba(0, 0, 0, 0.2) transparent;
  margin-left: calc(-1 * (100vw - 100%));
  scrollbar-gutter: stable;
}

body {
  font-family: "MiSans",
    "Helvetica Neue",
    Helvetica,
    Arial,
    "PingFang SC",
    "Hiragino Sans GB",
    "Heiti SC",
    "Microsoft YaHei",
    "WenQuanYi Micro Hei",
    sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  margin: 0;
  padding: 10px;
  max-width: 100%;
  overflow-x: hidden;
}
</style>
