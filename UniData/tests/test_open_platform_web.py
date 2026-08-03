from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_open_platform_spa_routes_and_cache_headers():
    dist = Path(__file__).resolve().parents[2] / "open-platform-web" / "dist"
    assert (dist / "index.html").exists(), "先在 open-platform-web 执行 npm run build"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        home = await client.get("/", follow_redirects=False)
        root = await client.get("/open-platform")
        nested = await client.get("/open-platform/console/apps/app-1")
        legacy_docs = await client.get("/docs/brief", follow_redirects=False)
        assert home.status_code == 307
        assert home.headers["location"] == "/open-platform"
        assert root.status_code == 200
        assert nested.status_code == 200
        assert legacy_docs.status_code == 404
        assert "UniData 开放平台" in root.text
        assert root.headers["cache-control"] == "no-cache"

        asset = next((dist / "assets").iterdir()).name
        response = await client.get(f"/open-platform/assets/{asset}")
        assert response.status_code == 200
        assert (
            response.headers["cache-control"] == "public, max-age=31536000, immutable"
        )
