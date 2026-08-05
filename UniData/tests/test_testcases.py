"""通用接口与健康检查的测试模块。"""
import pytest
from fastapi import HTTPException
from httpx import AsyncClient
from pydantic import ValidationError

from app.api.v1.validation import valid_collection_name
from app.main import app
from app.schemas.document import DocumentBatchUpsertRequest, DocumentCreateRequest


class TestHealthCheck:
    async def test_health_check(self, clean_client: AsyncClient):
        response = await clean_client.get("/health")
        assert response.status_code == 200
        assert response.json()["data"]["status"] == "healthy"


class TestAPIRoutes:
    def test_generic_documents_endpoint_exists(self):
        assert "/api/v1/data/{collection}" in app.openapi()["paths"]

    async def test_agents_online_requires_search_token(self, clean_client: AsyncClient):
        response = await clean_client.get("/api/v1/agents/online")
        assert response.status_code == 401

    async def test_agent_registration_requires_service_token(
        self, clean_client: AsyncClient, monkeypatch
    ):
        from app.core.config import get_settings

        # 本地 .env 可能已配置 token，测试固定走“未配置”分支，保证结果与环境无关。
        monkeypatch.setattr(get_settings(), "agent_registration_token", "")
        response = await clean_client.post(
            "/api/v1/agents/register",
            json={"ip": "127.0.0.1", "port": 8091},
        )
        assert response.status_code == 503


class TestCollectionValidation:
    def test_accepts_supported_collection_name(self):
        assert valid_collection_name("release_notes-2026") == "release_notes-2026"

    def test_rejects_path_like_collection_name(self):
        with pytest.raises(HTTPException) as exc_info:
            valid_collection_name("../private")
        assert exc_info.value.status_code == 400

    def test_rejects_empty_document_id(self):
        with pytest.raises(ValidationError):
            DocumentCreateRequest(id="")

    def test_rejects_empty_batch(self):
        with pytest.raises(ValidationError):
            DocumentBatchUpsertRequest(items=[])

    def test_rejects_duplicate_batch_document_ids(self):
        with pytest.raises(ValidationError, match="文档 id 不能重复"):
            DocumentBatchUpsertRequest(
                items=[
                    DocumentCreateRequest(id="duplicate"),
                    DocumentCreateRequest(id="duplicate"),
                ]
            )


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
