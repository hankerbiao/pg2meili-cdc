## 概览

本目录包含一个基于 React + TypeScript + Vite 开发的内部调试工具，用于搜索接口验证、浏览器式搜索体验和文档管理。

- 技术栈：React 18、TypeScript、Vite
- 运行方式：纯前端 SPA，依赖 Go Agent 的搜索接口与 UniData 文档接口
- 主要功能：
  - 接口测试模式：构造任意搜索请求、查看原始返回
  - 浏览器模式：以“搜索引擎结果页”的方式展示搜索结果
  - 文档管理：查看、新建、编辑和删除文档与索引

> 默认 API Key 和服务地址通过 Vite 环境变量配置，示例见 `.env.example`。

## 目录结构

```bash
frontend/
├── src/
│   ├── components/
│   │   ├── SearchTester.tsx           # 接口测试模式页面
│   │   ├── BrowserSearchPage.tsx      # 浏览器模式页面
│   │   ├── DocumentManager.tsx        # 文档管理状态与操作
│   │   └── DocumentManagerPanels.tsx  # 文档管理展示面板
│   ├── App.tsx                    # 页面模式切换入口
│   ├── api.ts                     # 搜索与文档 API 封装
│   ├── searchUtils.tsx            # cURL 与高亮展示工具
│   ├── index.css                  # 全局样式
│   └── main.tsx                   # 应用入口（ReactDOM 渲染）
├── index.html
├── package.json
├── tsconfig.json
└── vite.config.ts
```

## 启动与构建

在 `frontend` 目录下执行：

```bash
# 安装依赖
npm install

# 本地开发（默认 Vite dev server）
npm run dev

# 构建生产包
npm run build

# 预览构建产物
npm run preview
```

## 核心模块说明

### 1. 入口与路由切换

- `src/main.tsx`：使用 `ReactDOM.createRoot` 挂载到 `#root`，引入全局样式 `index.css` 和根组件 `App`。
- `src/App.tsx`：
  - 使用 `useState<ViewMode>` 维护当前模式：`'tester' | 'browser' | 'manager'`
  - 顶部提供三个视图入口：
    - “接口测试模式”：渲染 `SearchTester`
    - “浏览器模式”：渲染 `BrowserSearchPage`
    - “文档管理”：渲染 `DocumentManager`

### 2. API 封装（`src/api.ts`）

- 类型定义：
  - `SearchRequest`：封装 Meilisearch 搜索参数（`q`、`offset`、`limit`、`filter`、`attributesToHighlight` 等）。
  - `SearchHit`：单条搜索结果结构（`id`、`ext_id`、`name`、`summary`、`tags`、`_formatted`）。
  - `SearchResponse`：搜索结果列表，包含分页和耗时信息。
- 预设场景：
  - `PRESET_SCENARIOS`：定义多种常用搜索场景（简单关键字、高亮、分页、标签过滤、空关键字获取全部等），供 `SearchTester` 使用。
- 请求函数：
  - `search(baseUrl, apiKey, request)`：
    - 向 `{baseUrl}/search` 发送 `POST` 请求
    - Header:
      - `Authorization: Bearer <API_KEY>`
      - `Content-Type: application/json`
    - 对非 2xx 响应抛出错误并附带返回文本

### 3. 接口测试模式（`src/components/SearchTester.tsx`）

目标：给后端 / 搜索工程师一个灵活的接口调试面板。

- 状态：
  - `baseUrl`：搜索服务基础地址（默认指向某测试环境）
  - `apiKey`：开放平台 API Key，初始值为 `DEFAULT_API_KEY`
  - `selectedScenario`：当前选中的预设场景索引
  - `request`：当前结构化搜索请求
  - `curlText`：当前生成/编辑后的 cURL 命令
  - `response` / `error` / `loading`：请求结果与状态
- 关键逻辑：
  - `buildSearchCurl(baseUrl, apiKey, request)`：
    - 生成对 `/search` 的 `curl -X POST` 命令
    - 自动填充 `Authorization` 和 `Content-Type` header
    - 处理单引号以兼容 shell
  - `parseSearchCurl(command)`：
    - 反向从一段 cURL 文本中解析出：
      - `baseUrl`（从 URL origin 提取）
      - `apiKey`（`Authorization: Bearer`）
      - `body`（`--data-raw/-d` 部分）
  - `executeSearch(request, overrideBaseUrl?, overrideApiKey?)`：
    - 封装实际的 `search` 调用与 loading/error 状态管理
  - `handleScenarioChange(index)`：
    - 切换预设场景，刷新 `request`
    - 自动触发一次搜索请求
  - `handleManualSearch()`：
    - 从当前 `curlText` 解析出请求，更新 baseUrl/apiKey
    - 发起搜索
- UI 布局：
  - 左侧 Sidebar：预设场景列表（名称 + 描述）
  - 右侧：
    - “配置”区域：输入 API 地址和 API Key
    - “请求参数”区域：
      - 展示基础请求信息（POST、Headers）
      - 可编辑的 cURL 文本框（同步 baseUrl/apiKey/request）
    - “执行”按钮：触发搜索
    - 结果区域：
      - 列表卡片展示搜索命中（ext_id / name / summary / tags）
      - 高亮解析 `<em>...</em>` 标签并在界面中用 `<em>` 元素包裹
      - “加载更多”按钮，根据当前 `offset/limit` 进行分页追加

### 4. 浏览器模式（`src/components/BrowserSearchPage.tsx`）

目标：模拟一个简化版“搜索引擎结果页”，用于业务侧体验搜索效果。

- 状态：
  - `baseUrl`：搜索 API 基础地址
  - `apiKey`：开放平台 API Key（默认来自 `DEFAULT_API_KEY`）
  - `query`：搜索关键字
  - `filter`：过滤条件（例如：`lab = "BMC"`）
  - `highlight`：是否开启高亮（`attributesToHighlight = ['*']`）
  - `response` / `error` / `loading` / `showCurl`
- 关键逻辑：
  - `buildCurl()`：根据当前输入自动生成 cURL 命令（支持高亮和 filter）。
  - `handleSearch()`：组装 `SearchRequest` 并调用 `search`。
  - `handleKeyDown()`：在输入框按 Enter 直接触发搜索。
  - `parseHighlight(text, enableHighlight)`：
    - 解析字符串中的 `<em>...</em>` 高亮片段，返回 React 节点数组
    - 当 `enableHighlight` 关闭时，仅去掉标签、保留内容。
  - `renderHit(hit)`：
    - 使用 `_formatted.name`/`_formatted.summary` 优先展示高亮文本
    - 根据 `ext_id` 生成展示用“URL”（非真实跳转）
    - 渲染 tags 标签。
- UI 布局：
  - 顶部导航条：Tab 切换（当前均为 Mock）
  - 工具栏：
    - 地址栏（搜索关键字）
    - 搜索按钮（受 `loading`/`apiKey` 控制 disabled 状态）
  - 子工具栏：
    - 过滤条件输入框
    - 高亮开关复选框
    - API Key 输入框
    - “cURL” 按钮，用于展开/收起 cURL 预览
  - 内容区：
    - 错误提示条
    - 结果列表：仿浏览器搜索结果样式的卡片列表

### 5. 文档管理（`src/components/DocumentManager.tsx`）

文档管理视图对接 UniData API，支持按集合查看、新建、编辑和删除 JSON 文档，
并支持查看或删除集合索引。展示面板拆分在 `DocumentManagerPanels.tsx` 中。

### 6. 样式（`src/index.css`）

全局使用单一 CSS 文件，覆盖：

- 顶部模式切换导航（`.top-nav` 等）
- 接口测试布局（`.search-tester`、`.sidebar`、`.content`、`.hit-card` 等）
- 浏览器模式布局（`.browser-page`、`.browser-toolbar`、`.browser-hit` 等）
- 文档管理布局（`.manager-*` 等）
- 响应式处理：在窄屏下将左右分栏改为上下布局。

## 使用说明

1. 启动后端 Meilisearch 同步服务，并确保 `/search` 接口可访问。
2. 在浏览器打开前端（`npm run dev` 默认地址通常为 `http://localhost:5173`）。
3. 切换模式：
   - “接口测试模式”：适合开发/排查问题，能看到更原始的请求体和响应。
   - “浏览器模式”：适合业务同学从“用户视角”体验搜索效果。
   - “文档管理”：用于维护集合文档和索引。
4. 根据需要修改：
   - API 地址（baseUrl）
   - API Key（替换为你环境的有效 Key）
   - 搜索关键字、过滤条件、高亮开关等。

## 安全与配置建议

- 不要在生产环境前端代码中内置有效 API Key。
- 使用 `VITE_DEFAULT_API_KEY`、`VITE_DEFAULT_SEARCH_BASE_URL`、`VITE_AGENTS_API_BASE` 和 `VITE_UNIDATA_API_BASE` 配置调试环境。
- 当前项目主要面向内网调试/验证场景，如要对外使用，需补充鉴权、错误处理和 UI 细节。
