## 概览

本目录包含一个基于 React + TypeScript + Vite 开发的前端小工具，用于对接后端 Meilisearch 搜索服务，方便进行接口调试和浏览器式搜索体验。

- 技术栈：React 18、TypeScript、Vite
- 运行方式：纯前端 SPA，依赖后端暴露的 `/search` HTTP 接口
- 主要功能：
  - 接口测试模式：构造任意搜索请求、查看原始返回
  - 浏览器模式：以“搜索引擎结果页”的方式展示搜索结果

> 注意：代码中默认写死的 JWT 仅用于本地调试，请根据实际环境自行替换。

## 目录结构

```bash
frontend/
├── public/               # 静态资源
├── src/
│   ├── components/
│   │   ├── SearchTester.tsx       # 接口测试模式页面
│   │   └── BrowserSearchPage.tsx  # 浏览器模式页面
│   ├── App.tsx                    # 页面模式切换入口
│   ├── api.ts                     # 搜索 API 类型和请求封装
│   ├── index.css                  # 全局样式（两种模式共享）
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
  - 使用 `useState<ViewMode>` 维护当前模式：`'tester' | 'browser'`
  - 顶部有两个切换按钮：
    - “接口测试模式”：渲染 `SearchTester`
    - “浏览器模式”：渲染 `BrowserSearchPage`

### 2. API 封装（`src/api.ts`）

- 类型定义：
  - `SearchRequest`：封装 Meilisearch 搜索参数（`q`、`offset`、`limit`、`filter`、`attributesToHighlight` 等）。
  - `SearchHit`：单条搜索结果结构（`id`、`ext_id`、`name`、`summary`、`tags`、`_formatted`）。
  - `SearchResponse`：搜索结果列表，包含分页和耗时信息。
- 预设场景：
  - `PRESET_SCENARIOS`：定义多种常用搜索场景（简单关键字、高亮、分页、标签过滤、空关键字获取全部等），供 `SearchTester` 使用。
- 请求函数：
  - `search(baseUrl, token, request)`：
    - 向 `{baseUrl}/search` 发送 `POST` 请求
    - Header:
      - `Authorization: Bearer <JWT>`
      - `Content-Type: application/json`
    - 对非 2xx 响应抛出错误并附带返回文本

### 3. 接口测试模式（`src/components/SearchTester.tsx`）

目标：给后端 / 搜索工程师一个灵活的接口调试面板。

- 状态：
  - `baseUrl`：搜索服务基础地址（默认指向某测试环境）
  - `token`：JWT Token，初始值为 `DEFAULT_TOKEN`
  - `selectedScenario`：当前选中的预设场景索引
  - `customRequest`：当前编辑中的请求体 JSON 字符串
  - `curlText`：当前生成/编辑后的 cURL 命令
  - `response` / `error` / `loading`：请求结果与状态
- 关键逻辑：
  - `buildCurl(baseUrl, token, body)`：
    - 生成对 `/search` 的 `curl -X POST` 命令
    - 自动填充 `Authorization` 和 `Content-Type` header
    - 处理单引号以兼容 shell
  - `parseCurlCommand(cmd)`：
    - 反向从一段 cURL 文本中解析出：
      - `baseUrl`（从 URL origin 提取）
      - `token`（`Authorization: Bearer`）
      - `body`（`--data-raw/-d` 部分）
  - `executeSearch(request, overrideBaseUrl?, overrideToken?)`：
    - 封装实际的 `search` 调用与 loading/error 状态管理
  - `handleScenarioChange(index)`：
    - 切换预设场景，刷新 `customRequest`
    - 自动触发一次搜索请求
  - `handleManualSearch()`：
    - 从当前 `curlText` 解析出请求，更新 baseUrl/token
    - 发起搜索
- UI 布局：
  - 左侧 Sidebar：预设场景列表（名称 + 描述）
  - 右侧：
    - “配置”区域：输入 API 地址和 JWT Token
    - “请求参数”区域：
      - 展示基础请求信息（POST、Headers）
      - 可编辑的 cURL 文本框（Realtime 同步 baseUrl/token/customRequest）
    - “执行”按钮：触发搜索
    - 结果区域：
      - 列表卡片展示搜索命中（ext_id / name / summary / tags）
      - 高亮解析 `<em>...</em>` 标签并在界面中用 `<em>` 元素包裹
      - “加载更多”按钮，根据当前 `offset/limit` 进行分页追加

### 4. 浏览器模式（`src/components/BrowserSearchPage.tsx`）

目标：模拟一个简化版“搜索引擎结果页”，用于业务侧体验搜索效果。

- 状态：
  - `baseUrl`：搜索 API 基础地址
  - `token`：JWT Token（默认来自 `DEFAULT_TOKEN`）
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
    - 搜索按钮（受 `loading`/`token` 控制 disabled 状态）
  - 子工具栏：
    - 过滤条件输入框
    - 高亮开关复选框
    - JWT 输入框
    - “cURL” 按钮，用于展开/收起 cURL 预览
  - 内容区：
    - 错误提示条
    - 结果列表：仿浏览器搜索结果样式的卡片列表

### 5. 样式（`src/index.css`）

全局使用单一 CSS 文件，覆盖：

- 顶部模式切换导航（`.top-nav` 等）
- 接口测试布局（`.search-tester`、`.sidebar`、`.content`、`.hit-card` 等）
- 浏览器模式布局（`.browser-page`、`.browser-toolbar`、`.browser-hit` 等）
- 响应式处理：在窄屏下将左右分栏改为上下布局。

## 使用说明

1. 启动后端 Meilisearch 同步服务，并确保 `/search` 接口可访问。
2. 在浏览器打开前端（`npm run dev` 默认地址通常为 `http://localhost:5173`）。
3. 切换模式：
   - “接口测试模式”：适合开发/排查问题，能看到更原始的请求体和响应。
   - “浏览器模式”：适合业务同学从“用户视角”体验搜索效果。
4. 根据需要修改：
   - API 地址（baseUrl）
   - JWT Token（替换为你环境的有效 Token）
   - 搜索关键字、过滤条件、高亮开关等。

## 安全与配置建议

- 不要在生产环境前端代码中保留有效的长生命周期 JWT。
- 建议将默认 Token 替换为占位符，并通过环境变量或后端下发方式注入真实 Token。
- 当前项目主要面向内网调试/验证场景，如要对外使用，需补充鉴权、错误处理和 UI 细节。

