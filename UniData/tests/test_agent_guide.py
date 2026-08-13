"""AI Agent 集成指南后端测试."""
import pytest
import re
from httpx import AsyncClient

from app.agent_guide import (
    DATA_BASE_URL,
    GUIDE_SCHEMA_VERSION,
    PUBLIC_OPERATIONS,
    SEARCH_BASE_URL,
    build_agent_guide,
    render_llms_text,
    _is_excluded,
    _match_path,
)
from app.main import app


class TestAgentGuideModule:
    """agent_guide 模块单元测试."""

    def test_schema_version_is_1_0(self):
        """Schema 版本固定为 1.0."""
        assert GUIDE_SCHEMA_VERSION == "1.0"

    def test_public_operations_not_empty(self):
        """公开操作列表不为空."""
        assert len(PUBLIC_OPERATIONS) > 0

    @pytest.mark.parametrize(
        "pattern,path,expected",
        [
            ("/api/v1/data/{collection}", "/api/v1/data/products", True),
            ("/api/v1/data/{collection}", "/api/v1/data/orders", True),
            ("/api/v1/data/{collection}/{id}", "/api/v1/data/products/123", True),
            ("/api/v1/data/{collection}", "/api/v1/data", False),
            ("/api/v1/data/{collection}", "/api/v1/data/orders/123", False),
            ("/api/v1/open-platform/apps", "/api/v1/open-platform/apps", True),
            ("/api/v1/open-platform/apps", "/api/v1/open-platform/apps/1", False),
        ],
    )
    def test_match_path(self, pattern: str, path: str, expected: bool):
        """路径匹配逻辑正确."""
        assert _match_path(pattern, path) == expected

    @pytest.mark.parametrize(
        "path,expected",
        [
            ("/api/v1/open-platform/apps", True),
            ("/api/v1/open-platform/apps/123", True),
            ("/api/v1/auth/login", True),
            ("/api/v1/internal/sync", True),
            ("/api/v1/agents/register", True),
            ("/api/v1/agents/cleanup-confirmations", True),
            ("/health", True),
            ("/ready", True),
            ("/api/v1/data/products", False),
            ("/api/v1/indexes", False),
            ("/api/v1/agents/online", False),
        ],
    )
    def test_is_excluded(self, path: str, expected: bool):
        """排除逻辑正确."""
        assert _is_excluded(path) == expected


class TestAgentGuideEndpoints:
    """Agent Guide 端点集成测试."""

    @pytest.mark.asyncio
    async def test_agent_guide_json_returns_200(self, clean_client: AsyncClient):
        """GET /agent-guide.json 返回 200."""
        response = await clean_client.get("/agent-guide.json")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_agent_guide_json_content_type(self, clean_client: AsyncClient):
        """GET /agent-guide.json 返回 JSON Content-Type."""
        response = await clean_client.get("/agent-guide.json")
        assert "application/json" in response.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_agent_guide_json_schema_version(self, clean_client: AsyncClient):
        """响应包含 schema_version: 1.0."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        assert data.get("schema_version") == "1.0"

    @pytest.mark.asyncio
    async def test_agent_guide_json_service_info(self, clean_client: AsyncClient):
        """响应包含服务信息."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        service = data.get("service", {})
        assert service.get("name") == "MeliData"
        assert "version" in service
        assert "purpose" in service

    @pytest.mark.asyncio
    async def test_agent_guide_json_usage_policy(self, clean_client: AsyncClient):
        """响应包含使用策略，reference_only 模式."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        policy = data.get("usage_policy", {})
        assert policy.get("mode") == "reference_only"
        assert policy.get("direct_agent_execution") is False
        assert policy.get("authorization_required_for_real_requests") is True
        assert "instruction" in policy

    @pytest.mark.asyncio
    async def test_agent_guide_json_links(self, clean_client: AsyncClient):
        """响应包含权威链接."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        links = data.get("links", {})
        assert "/openapi.json" in links.get("openapi", "")
        assert "/docs" in links.get("human_docs", "")
        assert "/llms.txt" in links.get("llms", "")
        assert "/api/v1/sdk/python/download" in links.get("python_sdk_download", "")

    @pytest.mark.asyncio
    async def test_agent_guide_json_search_contract(self, clean_client: AsyncClient):
        data = (await clean_client.get("/agent-guide.json")).json()
        endpoints = data["endpoints"]
        assert endpoints["data_base_url"] == DATA_BASE_URL
        assert endpoints["search_base_url"] == SEARCH_BASE_URL
        assert endpoints["search_path_template"] == "{search_base_url}/api/v1/collections/{collection}/search"

    @pytest.mark.asyncio
    async def test_agent_guide_json_architecture(self, clean_client: AsyncClient):
        """响应包含架构信息."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        arch = data.get("architecture", {})
        assert "write_path" in arch
        assert "search_path" in arch
        assert len(arch["write_path"]) > 0
        assert len(arch["search_path"]) > 0

    @pytest.mark.asyncio
    async def test_agent_guide_json_authentication(self, clean_client: AsyncClient):
        """响应包含认证信息."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        auth = data.get("authentication", {})
        assert auth.get("scheme") == "Bearer"
        assert auth.get("header") == "Authorization"
        assert "scopes" in auth
        assert "data:read" in auth["scopes"]
        assert "data:write" in auth["scopes"]
        assert "search:read" in auth["scopes"]

    @pytest.mark.asyncio
    async def test_agent_guide_json_workflows(self, clean_client: AsyncClient):
        """响应包含固定工作流."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        workflows = data.get("workflows", [])
        workflow_ids = [w["id"] for w in workflows]
        assert "write_document" in workflow_ids
        assert "read_document" in workflow_ids
        assert "configure_index" in workflow_ids
        assert "regional_search" in workflow_ids

    @pytest.mark.asyncio
    async def test_agent_guide_json_operations(self, clean_client: AsyncClient):
        """响应包含公开操作列表."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        operations = data.get("operations", [])
        assert len(operations) > 0

        # 验证包含预期的操作
        paths = [op["path"] for op in operations]
        methods = [op["method"] for op in operations]

        # 核心 CRUD 操作
        assert "/api/v1/data/{collection}" in paths
        assert "/api/v1/data/{collection}/{id}" in paths
        assert "/api/v1/indexes" in paths

        # search:read 操作
        online_ops = [op for op in operations if "online" in op["path"]]
        assert len(online_ops) > 0
        assert online_ops[0]["required_scopes"] == ["search:read"]

    @pytest.mark.asyncio
    async def test_agent_guide_json_no_admin_operations(self, clean_client: AsyncClient):
        """不包含管理端点."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        operations = data.get("operations", [])
        paths = [op["path"] for op in operations]

        # 明确排除的路径不应出现
        excluded_paths = [
            "/api/v1/open-platform/",
            "/api/v1/auth/",
            "/api/v1/internal/",
        ]
        for excluded in excluded_paths:
            for path in paths:
                assert not path.startswith(excluded), f"意外包含: {path}"

        # 精确排除的路径
        assert "/api/v1/agents/register" not in paths
        assert "/api/v1/agents/cleanup-confirmations" not in paths

    @pytest.mark.asyncio
    async def test_agent_guide_json_examples(self, clean_client: AsyncClient):
        """响应包含代码示例."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        examples = data.get("examples", [])
        assert len(examples) > 0

        languages = [e["language"] for e in examples]
        assert "python" in languages
        assert "typescript" in languages

    @pytest.mark.asyncio
    async def test_agent_guide_json_non_targets(self, clean_client: AsyncClient):
        """响应包含非目标说明."""
        response = await clean_client.get("/agent-guide.json")
        data = response.json()
        non_targets = data.get("non_targets", [])
        assert len(non_targets) > 0

        # 验证关键类别存在
        categories = [nt["category"] for nt in non_targets]
        assert "开放平台管理" in categories
        assert "内部同步" in categories
        assert "区域节点运维" in categories

    @pytest.mark.asyncio
    async def test_agent_guide_json_no_secrets(self, clean_client: AsyncClient):
        """响应不包含密钥、密码或内部 IP."""
        response = await clean_client.get("/agent-guide.json")
        text = response.text

        # 不应包含密钥样式
        assert "ud_live_ak_" not in text
        # 不应包含明显密码
        assert "password" not in text.lower() or "api_key_password" not in text.lower()
        # 不应包含内网 IP
        assert not re.search(r"192\.168\.\d+\.\d+", text)
        assert not re.search(r"10\.\d+\.\d+\.\d+", text)
        assert not re.search(r"172\.(1[6-9]|2\d|3[01])\.\d+\.\d+", text)

    @pytest.mark.asyncio
    async def test_llms_txt_returns_200(self, clean_client: AsyncClient):
        """GET /llms.txt 返回 200."""
        response = await clean_client.get("/llms.txt")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_llms_txt_content_type(self, clean_client: AsyncClient):
        """GET /llms.txt 返回纯文本 Content-Type."""
        response = await clean_client.get("/llms.txt")
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type
        assert "charset=utf-8" in content_type

    @pytest.mark.asyncio
    async def test_llms_txt_contains_links(self, clean_client: AsyncClient):
        """llms.txt 包含权威链接."""
        response = await clean_client.get("/llms.txt")
        text = response.text

        assert "/agent-guide.json" in text
        assert "/openapi.json" in text
        assert "/docs" in text
        assert "/api/v1/sdk/python/download" in text

    @pytest.mark.asyncio
    async def test_llms_txt_contains_reference_only(self, clean_client: AsyncClient):
        """llms.txt 包含边界说明."""
        response = await clean_client.get("/llms.txt")
        text = response.text.lower()

        assert "reference" in text or "boundary" in text or "not a tool" in text

    @pytest.mark.asyncio
    async def test_llms_txt_render_function(self):
        """render_llms_text 函数输出稳定."""
        text1 = render_llms_text()
        text2 = render_llms_text()
        assert text1 == text2
        assert "# MeliData" in text1
        assert "## Start here" in text1


class TestBuildAgentGuideFunction:
    """build_agent_guide 函数单元测试."""

    def test_build_raises_on_missing_operation(self):
        """当 allowlist 中的路径在 OpenAPI 中缺失时抛出 ValueError."""
        # 模拟一个缺失关键路径的 OpenAPI
        openapi = {
            "paths": {
                "/api/v1/data/{collection}": {
                    "post": {
                        "operationId": "upsert_document",
                        "summary": "创建文档",
                        "description": "创建或更新文档",
                    }
                }
                # 缺少其他 allowlist 中的路径
            }
        }
        with pytest.raises(ValueError, match="Agent Guide allowlist 中配置的路径在当前 OpenAPI 中不存在"):
            build_agent_guide(openapi, "1.0.0")

    def test_build_includes_sdk_download_operation(self):
        """SDK 下载操作始终包含，即使不在 OpenAPI 中."""
        # 使用真实的完整 OpenAPI
        openapi = app.openapi()
        guide = build_agent_guide(openapi, "0.1.0")
        ops = guide["operations"]
        sdk_ops = [op for op in ops if "sdk" in op["path"].lower() or "download" in op["path"].lower()]
        assert len(sdk_ops) > 0

    def test_build_operations_have_required_fields(self):
        """每个操作都包含必填字段."""
        openapi = app.openapi()
        guide = build_agent_guide(openapi, "0.1.0")
        for op in guide["operations"]:
            assert "operation_id" in op
            assert "method" in op
            assert "path" in op
            assert "summary" in op
            assert "description" in op
            assert "required_scopes" in op
            # openapi_ref 可以为 None（SDK 下载）
            assert "openapi_ref" in op

    def test_build_workflows_have_correct_scopes(self):
        """工作流的 scope 与 allowlist 一致."""
        openapi = app.openapi()
        guide = build_agent_guide(openapi, "0.1.0")

        # regional_search 必须使用 search:read
        regional = next(
            (w for w in guide["workflows"] if w["id"] == "regional_search"),
            None,
        )
        assert regional is not None
        assert "search:read" in regional["required_scopes"]

    def test_build_operations_sorted_stably(self):
        """操作列表稳定排序."""
        openapi = app.openapi()
        guide1 = build_agent_guide(openapi, "0.1.0")
        guide2 = build_agent_guide(openapi, "0.1.0")

        ops1 = [op["operation_id"] for op in guide1["operations"]]
        ops2 = [op["operation_id"] for op in guide2["operations"]]
        assert ops1 == ops2
