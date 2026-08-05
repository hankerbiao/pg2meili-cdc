"""静态资源与简单页面注册。"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings, get_settings


class ImmutableStaticFiles(StaticFiles):
    """为 Vite 带内容哈希的静态资源设置长期缓存。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def open_platform_dist_dir(settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    configured = settings.open_platform_dist_dir.strip()
    return (
        Path(configured)
        if configured
        else repository_root() / "open-platform-web" / "dist"
    )


def open_platform_assets_ready(settings: Settings | None = None) -> bool:
    dist = open_platform_dist_dir(settings)
    return (dist / "index.html").is_file() and (dist / "assets").is_dir()


def validate_runtime_assets(settings: Settings) -> None:
    if settings.open_platform_dist_dir.strip() and not open_platform_assets_ready(
        settings
    ):
        raise RuntimeError("开放平台前端构建产物不存在")


def mount_static(app: FastAPI, settings: Settings | None = None) -> None:
    """挂载静态资源目录。"""
    settings = settings or get_settings()
    open_platform_assets = open_platform_dist_dir(settings) / "assets"
    if open_platform_assets.exists():
        app.mount(
            "/open-platform/assets",
            ImmutableStaticFiles(directory=open_platform_assets),
            name="open-platform-assets",
        )


def register_pages(app: FastAPI, settings: Settings | None = None) -> None:
    """注册简单 HTML 页面路由。"""
    settings = settings or get_settings()
    open_platform_index = open_platform_dist_dir(settings) / "index.html"

    def open_platform_spa():
        if not open_platform_index.exists():
            return PlainTextResponse(
                "开放平台前端尚未构建，请先在 open-platform-web 执行 npm run build。",
                status_code=503,
            )
        return FileResponse(open_platform_index, headers={"Cache-Control": "no-cache"})

    @app.get("/", include_in_schema=False)
    async def app_home_page():
        return RedirectResponse(url="/open-platform", status_code=307)

    @app.get("/open-platform", include_in_schema=False)
    async def open_platform_page():
        return open_platform_spa()

    @app.get("/open-platform/{spa_path:path}", include_in_schema=False)
    async def open_platform_spa_page(spa_path: str):
        return open_platform_spa()

    # OA 单点登录相关前端路由：整页访问（springboard 回跳 / 直接刷新）时需 fallback 到 SPA
    @app.get("/oa", include_in_schema=False)
    async def oa_spa_page():
        return open_platform_spa()

    @app.get("/oa/{spa_path:path}", include_in_schema=False)
    async def oa_spa_sub_page(spa_path: str):
        return open_platform_spa()

    # 其他前端路由（登录页 / 控制台）整页访问时同样 fallback 到 SPA
    @app.get("/login", include_in_schema=False)
    async def login_spa_page():
        return open_platform_spa()

    @app.get("/console/{spa_path:path}", include_in_schema=False)
    async def console_spa_page(spa_path: str):
        return open_platform_spa()
