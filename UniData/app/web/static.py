"""静态资源与简单页面注册。"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_static(app: FastAPI) -> None:
    """挂载静态资源目录。"""
    repo_root = Path(__file__).resolve().parents[3]
    libs_dir = repo_root / "libs"
    if libs_dir.exists():
        app.mount("/libs", StaticFiles(directory=libs_dir), name="libs")


def register_pages(app: FastAPI) -> None:
    """注册简单 HTML 页面路由。"""
    templates_dir = Path(__file__).resolve().parents[1] / "templates"

    @app.get("/", include_in_schema=False)
    async def app_home_page():
        html_path = templates_dir / "app_home.html"
        return FileResponse(html_path)

    @app.get("/app/register", include_in_schema=False)
    async def app_register_page():
        html_path = templates_dir / "app_token_register.html"
        return FileResponse(html_path)

    @app.get("/app/review", include_in_schema=False)
    async def app_review_page():
        html_path = templates_dir / "app_token_review.html"
        return FileResponse(html_path)
