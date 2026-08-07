# WEB (Vue 3 Frontend)

独立前端工程（Vue 3 + TypeScript + Vite + Pinia + vue-router），**pnpm 管理**（`web/pnpm-lock.yaml` 已提交，与后端 uv.lock 策略不同）。
通过 REST + WebSocket 对接后端 FastAPI。⚠️ **未纳入 CI**（build.yml/release.yml 均无 Node/pnpm 步骤）。

## STRUCTURE
```
web/src/
├── api/          # 后端对接: client.ts (axios) / jobs.ts / meta.ts / search.ts
├── stores/       # Pinia: build.ts (+内嵌 build.test.ts) / config.ts / search.ts
├── composables/  # useWebSocket.ts / useModTypes.ts
├── types/        # api.ts / config.ts / events.ts —— ⚠️ 手动镜像后端 Pydantic schemas，无代码生成
├── router/       # index.ts
├── views/        # BuildView / ConfigView / ResultsView / SearchView
├── components/
│   ├── config/   # 配置表单: ModList / LoaderSelector / VersionSelector / OutputForm ...
│   ├── build/    # 构建状态: DownloadItem / PhaseIndicator / StatsCard
│   ├── search/   # SearchBar / SearchResultCard
│   ├── layout/   # AppSidebar / AppTopBar / AppBackground
│   └── ui/       # 设计系统原语: McBadge/McButton/McCard/McCheckbox/McInput/McModal/McProgress/McSelect/McTag
└── styles/       # main.css / animations.css
```

## COMMANDS
```bash
pnpm install       # 安装依赖
pnpm dev           # Vite dev server
pnpm build         # vue-tsc -b && vite build → dist/
pnpm test          # vitest run
```

## CONVENTIONS
- `<script setup>` SFC；UI 原语统一 `Mc*` 前缀（components/ui/）
- 状态管理用 Pinia（stores/）；构建事件流走 `useWebSocket`（composables/）
- 类型安全严格：`vue-tsc -b` 在 build 里强制执行类型检查
- 测试用 Vitest（stores/ 内联 `*.test.ts`，无需独立 tests/ 目录）

## ANTI-PATTERNS
- 在前端硬编码后端 API 契约 —— `types/` 需与后端 `server/schemas.py` 同步维护（无代码生成）
- 绕过 Pinia stores 直接改共享状态
- 新增非 `Mc*` 命名的通用 UI 组件（应进 components/ui/）

## GOTCHAS
- 前端 `dist/` 默认构建到 `web/dist`；后端 `server/app.py` 静态挂载路径当前有误（指向 `modfetch/web/dist`，待修复为项目根 `web/dist`）
- 后端 CORS `allow_origins=["*"]` + credentials 组合非法，联调时可能遇跨域问题