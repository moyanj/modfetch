# Lua 插件系统实现计划

## TL;DR

使用 Lua 作为插件脚本语言，通过 `lupa` 库嵌入 Lua 运行时。
Lua 脚本无需编译，Nuitka 打包后仍可正常工作。

## 为什么选择 Lua

### 优势
- **Nuitka 兼容** - 纯文本脚本，不需要动态导入
- **沙箱安全** - 可以限制 Lua 环境，防止恶意代码
- **轻量快速** - 嵌入式脚本语言，启动开销小
- **热重载** - 可以运行时重新加载脚本
- **配置即代码** - 配置文件和插件使用同一种语言

### 对比 Python 插件
| 特性 | Python 插件 | Lua 插件 |
|------|------------|----------|
| Nuitka 兼容 | ❌ 动态导入失效 | ✅ 纯文本解释执行 |
| 安全性 | ⚠️ 难以完全限制 | ✅ 完整沙箱 |
| 性能 | 快 | 中等 |
| 学习成本 | 低 | 低 |
| 生态 | 丰富 | 够用 |

## 技术方案

### 依赖
```toml
[project.dependencies]
lupa = "^2.0"
```

### 架构
```
modfetch/
├── plugins/
│   ├── lua/
│   │   ├── __init__.py      # Lua 运行时管理
│   │   ├── runtime.py       # Lua 执行环境
│   │   ├── bridge.py        # Python-Lua 桥接
│   │   └── hooks.py         # Hook 系统
│   └── builtin/             # 内置 Lua 插件
│       ├── progress.lua
│       ├── filter.lua
│       └── notify.lua
```

### Lua API 设计

```lua
-- 插件元数据
local plugin = {
    name = "progress",
    version = "1.0.0",
    description = "显示下载进度",
    author = "ModFetch"
}

-- Hook 处理器
function plugin.on_config_loaded(ctx)
    print("配置加载完成!")
    print("Minecraft 版本: " .. ctx.config.minecraft.version[1])
    return { success = true }
end

function plugin.on_post_package(ctx)
    print("打包完成: " .. ctx.extra_data.output_path)
    return { success = true }
end

-- 返回插件
return plugin
```

### 配置使用

```toml
[minecraft]
version = ["1.21.1"]
mods = ["sodium"]

[plugins]
enabled = ["progress", "notify"]

[plugins.config.filter]
blacklist = ["badmod"]
```

## Work Objectives

### 核心目标
实现基于 Lua 的插件系统，完全兼容 Nuitka 打包

### 具体任务
1. 添加 `lupa` 依赖
2. 实现 Lua 运行时 (`LuaRuntime`)
3. 实现 Python-Lua 桥接层
4. 实现 Hook 系统
5. 移植内置插件到 Lua
6. 修改 CLI 支持 Lua 插件
7. 验证功能

## Execution Strategy

### Wave 1: 基础架构
- Task 1.1: 添加 lupa 依赖
- Task 1.2: 实现 LuaRuntime 类
- Task 1.3: 实现配置和上下文的 Lua 桥接

### Wave 2: Hook 系统
- Task 2.1: 实现 Hook 注册和执行
- Task 2.2: 实现 Lua 插件加载器
- Task 2.3: 插件管理器集成

### Wave 3: 内置插件
- Task 3.1: 创建 progress.lua
- Task 3.2: 创建 filter.lua
- Task 3.3: 创建 notify.lua

### Wave 4: CLI 集成
- Task 4.1: 修改 CLI 加载 Lua 插件
- Task 4.2: 配置文件解析

### Wave 5: 验证
- Task 5.1: 单元测试
- Task 5.2: 集成测试

## TODOs

- [ ] 1. 添加 lupa 依赖

  **What to do**:
  - 在 `pyproject.toml` 中添加 `lupa = "^2.0"`
  - 运行 `uv sync` 安装依赖

  **Acceptance Criteria**:
  - [ ] `uv run python -c "import lupa"` 成功

  **Commit**: `feat(plugins): 添加 lupa Lua 运行时依赖`

- [ ] 2. 实现 Lua 运行时

  **What to do**:
  - 创建 `modfetch/plugins/lua/runtime.py`
  - 实现 `LuaRuntime` 类封装 lupa
  - 提供安全的 Lua 执行环境

  **Acceptance Criteria**:
  - [ ] 可以执行简单的 Lua 代码
  - [ ] 可以传递 Python 对象到 Lua
  - [ ] 可以从 Lua 获取返回值

  **Commit**: `feat(plugins): 实现 Lua 运行时`

- [ ] 3. 实现 Python-Lua 桥接

  **What to do**:
  - 创建 `modfetch/plugins/lua/bridge.py`
  - 实现配置对象的 Lua 访问
  - 实现 HookContext 的 Lua 封装

  **Acceptance Criteria**:
  - [ ] Lua 可以读取配置数据
  - [ ] Lua 可以修改 HookResult

  **Commit**: `feat(plugins): 实现 Python-Lua 桥接层`

- [ ] 4. 实现 Lua 插件加载器

  **What to do**:
  - 创建 `modfetch/plugins/lua/loader.py`
  - 实现 `load_lua_plugin()` 方法
  - 支持从文件和字符串加载

  **Acceptance Criteria**:
  - [ ] 可以从 .lua 文件加载插件
  - [ ] 插件 Hook 可以注册到管理器

  **Commit**: `feat(plugins): 实现 Lua 插件加载器`

- [ ] 5. 创建内置 Lua 插件

  **What to do**:
  - 创建 `modfetch/plugins/builtin/progress.lua`
  - 创建 `modfetch/plugins/builtin/filter.lua`
  - 创建 `modfetch/plugins/builtin/notify.lua`

  **Acceptance Criteria**:
  - [ ] 所有内置插件可以用 Lua 实现
  - [ ] 功能与 Python 版本一致

  **Commit**: `feat(plugins): 添加内置 Lua 插件`

- [ ] 6. 修改 CLI 支持 Lua 插件

  **What to do**:
  - 修改 `modfetch/cli.py`
  - 从配置加载 Lua 插件
  - 使用新的 Lua 插件加载器

  **Acceptance Criteria**:
  - [ ] 配置文件中的插件可以加载
  - [ ] CLI 可以列出已加载的 Lua 插件

  **Commit**: `feat(cli): 支持 Lua 插件加载`

- [ ] 7. 验证和测试

  **What to do**:
  - 编写测试脚本
  - 验证所有 Hook 类型
  - 测试 Nuitka 打包兼容性

  **Acceptance Criteria**:
  - [ ] 所有测试通过
  - [ ] Nuitka 打包后插件正常工作

  **Commit**: `test(plugins): 添加 Lua 插件系统测试`

## Success Criteria

### 验证命令
```bash
# 1. 验证 Lua 运行时
uv run python -c "from modfetch.plugins.lua import LuaRuntime; r = LuaRuntime(); print(r.execute('return 1+1'))"

# 2. 验证插件加载
uv run python -c "
from modfetch.plugins.lua import LuaPluginLoader
loader = LuaPluginLoader()
plugin = loader.load_file('modfetch/plugins/builtin/progress.lua')
print(f'加载插件: {plugin.name}')
"

# 3. 验证配置加载
uv run python -c "
from modfetch.models import ModFetchConfig, MinecraftConfig
config = ModFetchConfig(
    minecraft=MinecraftConfig(version=['1.21.1'], mods=['sodium']),
    plugins={'enabled': ['progress']}
)
print(f'插件配置: {config.plugins}')
"
```

### 预期结果
- Lua 代码可以正常执行
- 插件可以从 Lua 文件加载
- 配置文件中的插件列表能正确解析
- Nuitka 打包后一切正常

## Migration Guide

### 从 Python 插件迁移

Python 插件:
```python
class MyPlugin(ModFetchPlugin):
    name = "myplugin"
    def on_config_loaded(self, ctx):
        return HookResult(success=True)
```

Lua 插件:
```lua
local plugin = {
    name = "myplugin"
}

function plugin.on_config_loaded(ctx)
    return { success = true }
end

return plugin
```

### 配置不变
配置文件格式完全兼容，无需修改。

## Notes

### Lua 版本
使用 Lua 5.4（lupa 默认）

### 安全考虑
- 禁用危险的 Lua 函数（如 `os.execute`）
- 限制文件系统访问
- 限制网络访问

### 性能
- Lua 插件性能足够用于 Hook 回调
- 大量计算应在 Python 端完成
