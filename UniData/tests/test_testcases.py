"""通用接口与健康检查的测试模块。"""
from httpx import AsyncClient

from app.main import app


class TestHealthCheck:
    async def test_health_check(self, clean_client: AsyncClient):
        response = await clean_client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"


class TestAPIRoutes:
    def test_generic_documents_endpoint_exists(self):
        routes = [r for r in app.routes if hasattr(r, "path")]
        documents_routes = [r for r in routes if "/api/v1/data" in r.path]
        assert len(documents_routes) > 0


class TestGenericDocumentsEndpoints:
    async def test_create_document_success(self, client: AsyncClient):
        payload = {"id": "doc-1", "name": "文档1"}
        response = await client.post(
            "/api/v1/data/test_collection",
            json=payload,
        )
        assert response.status_code in (200, 201)
        data = response.json()["data"]
        assert data["status"] == "success"
        assert data["id"] == "doc-1"
