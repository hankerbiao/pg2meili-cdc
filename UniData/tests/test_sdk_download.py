from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.api.v1.endpoints.sdk import python_sdk_download_filename


@pytest.mark.asyncio
async def test_python_sdk_download_is_an_installable_source_archive(clean_client):
    response = await clean_client.get("/api/v1/sdk/python/download")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="unidata-sdk-0.1.0.zip"'
    )

    with ZipFile(BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "pyproject.toml" in names
        assert "README.md" in names
        assert "src/unidata_sdk/__init__.py" in names
        assert "src/unidata_sdk/client.py" in names
        assert not any("tests/" in name for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert "uv.lock" not in names


def test_python_sdk_download_is_public_in_openapi():
    from app.main import app

    operation = app.openapi()["paths"]["/api/v1/sdk/python/download"]["get"]
    assert operation["tags"] == ["sdk"]
    assert operation["summary"] == "下载 MeliData Python SDK"


def test_openapi_uses_melidata_brand_without_changing_api_paths():
    from app.main import app

    openapi = app.openapi()
    assert openapi["info"]["title"] == "MeliData 生产者服务"
    assert "/api/v1/data/{collection}" in openapi["paths"]


def test_python_sdk_download_filename_reads_version_from_stable_archive(tmp_path):
    archive_path = tmp_path / "unidata-sdk.zip"
    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr(
            "pyproject.toml",
            '[project]\nname = "unidata-sdk"\nversion = "2.3.4"\n',
        )

    assert python_sdk_download_filename(archive_path) == "unidata-sdk-2.3.4.zip"


def test_python_sdk_download_filename_falls_back_for_invalid_archive(tmp_path):
    archive_path = tmp_path / "unidata-sdk.zip"
    archive_path.write_text("not a zip", encoding="utf-8")

    assert python_sdk_download_filename(archive_path) == "unidata-sdk.zip"
