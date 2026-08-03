"""Public downloads for official UniData SDKs."""

from io import BytesIO
from pathlib import Path
import tomllib
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse, Response

from app.core.config import Settings, get_settings


router = APIRouter()
REPOSITORY_ROOT = Path(__file__).resolve().parents[5]
PYTHON_SDK_ROOT = REPOSITORY_ROOT / "python-sdk"


def configured_python_sdk_archive(settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    configured = settings.python_sdk_archive.strip()
    return Path(configured) if configured else None


def python_sdk_available(settings: Settings | None = None) -> bool:
    archive = configured_python_sdk_archive(settings)
    if archive is not None:
        return archive.is_file()
    return (
        (PYTHON_SDK_ROOT / "pyproject.toml").is_file()
        and (PYTHON_SDK_ROOT / "README.md").is_file()
        and (PYTHON_SDK_ROOT / "src" / "unidata_sdk").is_dir()
    )


def validate_python_sdk_archive(settings: Settings) -> None:
    if settings.python_sdk_archive.strip() and not python_sdk_available(settings):
        raise RuntimeError("Python SDK 下载包不存在")


def python_sdk_download_filename(archive: Path) -> str:
    try:
        with ZipFile(archive) as package:
            project = tomllib.loads(package.read("pyproject.toml").decode("utf-8"))
        return f"unidata-sdk-{project['project']['version']}.zip"
    except (
        BadZipFile,
        KeyError,
        OSError,
        UnicodeDecodeError,
        tomllib.TOMLDecodeError,
    ):
        return archive.name


def build_python_sdk_archive() -> tuple[bytes, str]:
    pyproject = PYTHON_SDK_ROOT / "pyproject.toml"
    readme = PYTHON_SDK_ROOT / "README.md"
    package_root = PYTHON_SDK_ROOT / "src" / "unidata_sdk"
    if not pyproject.is_file() or not readme.is_file() or not package_root.is_dir():
        raise RuntimeError("Python SDK source is not available")

    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    version = project["project"]["version"]
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(pyproject, "pyproject.toml")
        archive.write(readme, "README.md")
        for source in sorted(package_root.rglob("*")):
            if (
                source.is_file()
                and "__pycache__" not in source.parts
                and source.suffix != ".pyc"
            ):
                archive.write(source, source.relative_to(PYTHON_SDK_ROOT).as_posix())
    return buffer.getvalue(), f"unidata-sdk-{version}.zip"


@router.get(
    "/python/download",
    response_class=Response,
    summary="下载 UniData Python SDK",
    description="下载可通过 pip 安装的官方 Python SDK 源码包。",
)
async def download_python_sdk() -> Response:
    archive = configured_python_sdk_archive()
    if archive is not None:
        if not archive.is_file():
            return JSONResponse(
                status_code=503,
                content={"data": None, "message": "Python SDK 下载包不存在"},
            )
        return FileResponse(
            archive,
            media_type="application/zip",
            filename=python_sdk_download_filename(archive),
            headers={"Cache-Control": "public, max-age=300"},
        )
    try:
        content, filename = build_python_sdk_archive()
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={"data": None, "message": f"Python SDK 源码包暂不可用：{exc}"},
        )
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "public, max-age=300",
        },
    )
