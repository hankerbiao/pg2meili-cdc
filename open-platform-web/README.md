# UniData Open Platform Web

开放平台文档与管理员控制台，基于 React、TypeScript 和 Vite。

## 开发

```bash
npm install
npm run dev
```

开发服务默认监听 `http://127.0.0.1:3100/open-platform/`，并将 `/api` 与 `/openapi.json` 代理到 `http://127.0.0.1:8080`。

## 构建与测试

```bash
npm run test
npm run build
npm run test:e2e:mock
```

Playwright 的 mock 套件不依赖后端，覆盖桌面、平板和移动端。真实后端 smoke 需要先启动 UniData，并注入管理员密码：

```bash
BASE_URL=http://127.0.0.1:8081/open-platform/ \
PLATFORM_PASSWORD='your-password' \
npm run test:e2e:integration
```

失败时会保留 screenshot、video 和 trace 到 `e2e/test-results/`；HTML 报告位于 `playwright-report/`。
本地默认使用系统 Chrome；可通过 `PLAYWRIGHT_CHANNEL` 指定其他已安装的 Playwright 浏览器通道。

UniData 直接托管 `dist`。生产启动 Python 服务前必须先执行 `npm run build`。

使用仓库根目录 Dockerfile 时，`dist` 会在 Node 构建阶段生成并复制到最终 UniData 镜像，不需要单独运行前端容器。执行 `docker compose watch unidata` 时，前端源码变化会触发镜像重建；Python 后端源码则直接同步并重启容器。
