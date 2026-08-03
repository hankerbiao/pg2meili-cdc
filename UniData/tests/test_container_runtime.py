from contextlib import asynccontextmanager
import importlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1.endpoints.sdk import (
    configured_python_sdk_archive,
    python_sdk_download_filename,
    python_sdk_available,
    validate_python_sdk_archive,
)
from app.core.config import Settings
from app.web.static import (
    open_platform_assets_ready,
    open_platform_dist_dir,
    validate_runtime_assets,
)


def test_container_runtime_paths_are_configurable(tmp_path: Path):
    dist = tmp_path / "portal"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    sdk_archive = tmp_path / "unidata-sdk-0.1.0.zip"
    sdk_archive.write_bytes(b"zip")
    settings = Settings(
        open_platform_dist_dir=str(dist),
        python_sdk_archive=str(sdk_archive),
    )

    assert open_platform_dist_dir(settings) == dist
    assert open_platform_assets_ready(settings)
    assert configured_python_sdk_archive(settings) == sdk_archive
    assert python_sdk_available(settings)
    validate_runtime_assets(settings)
    validate_python_sdk_archive(settings)


def test_explicit_missing_container_assets_fail_validation(tmp_path: Path):
    settings = Settings(
        open_platform_dist_dir=str(tmp_path / "missing-portal"),
        python_sdk_archive=str(tmp_path / "missing-sdk.zip"),
    )

    with pytest.raises(RuntimeError, match="开放平台"):
        validate_runtime_assets(settings)
    with pytest.raises(RuntimeError, match="Python SDK"):
        validate_python_sdk_archive(settings)


def test_container_sdk_download_keeps_versioned_filename(tmp_path: Path):
    archive = tmp_path / "unidata-sdk.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as package:
        package.writestr(
            "pyproject.toml",
            '[project]\nname = "unidata-sdk"\nversion = "1.2.3"\n',
        )

    assert python_sdk_download_filename(archive) == "unidata-sdk-1.2.3.zip"


def test_secret_file_overrides_direct_setting(tmp_path: Path, monkeypatch):
    secret_file = tmp_path / "session-secret"
    secret_file.write_text("file-session-secret-value", encoding="utf-8")
    monkeypatch.setenv("OPEN_PLATFORM_SESSION_SECRET_FILE", str(secret_file))

    settings = Settings(open_platform_session_secret="environment-value")

    assert settings.open_platform_session_secret == "file-session-secret-value"


@pytest.mark.asyncio
async def test_readiness_reports_container_dependencies(tmp_path: Path, monkeypatch):
    dist = tmp_path / "portal"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html></html>", encoding="utf-8")
    sdk_archive = tmp_path / "unidata-sdk-0.1.0.zip"
    sdk_archive.write_bytes(b"zip")
    settings = Settings(
        open_platform_dist_dir=str(dist),
        python_sdk_archive=str(sdk_archive),
        open_platform_admin_password_hash="$argon2id$configured",
        open_platform_session_secret="s" * 32,
        agent_registration_token="agent-secret",
        log_file_enabled=False,
    )

    class FakeSession:
        async def execute(self, _statement):
            return None

    @asynccontextmanager
    async def fake_db_context():
        yield FakeSession()

    main_module = importlib.import_module("app.main")
    monkeypatch.setattr(main_module, "get_db_context", fake_db_context)
    application = main_module.create_app(settings)

    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert all(response.json()["data"]["checks"].values())
