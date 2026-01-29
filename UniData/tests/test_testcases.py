"""测试用例端点的测试模块。"""
from httpx import AsyncClient

from app.main import app


class TestHealthCheck:
    """健康检查端点测试类。"""

    async def test_health_check(self, clean_client: AsyncClient):
        """测试健康检查端点。"""
        response = await clean_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAPIRoutes:
    """API 路由结构验证测试类（无数据库）。"""

    def test_testcases_endpoint_exists(self):
        """验证 testcases POST 端点已注册。"""
        routes = [r for r in app.routes if hasattr(r, "path")]
        testcases_routes = [r for r in routes if "/testcases" in r.path]
        assert len(testcases_routes) > 0, "testcases 端点应该已注册"

    def test_delete_endpoint_exists(self):
        """验证 testcases DELETE 端点已注册。"""
        routes = [r for r in app.routes if hasattr(r, "path")]
        delete_routes = [
            r
            for r in routes
            if "/testcases/{id}" in r.path and hasattr(r, "methods") and "DELETE" in r.methods
        ]
        assert len(delete_routes) > 0, "DELETE /testcases/{id} 端点应该已注册"

    def test_post_endpoint_methods(self):
        """验证 testcases POST 端点接受 POST 方法。"""
        routes = [r for r in app.routes if hasattr(r, "path")]
        post_routes = [
            r
            for r in routes
            if "/testcases" in r.path and hasattr(r, "methods") and "POST" in r.methods
        ]
        assert len(post_routes) > 0, "POST /testcases 端点应该接受 POST 方法"


class TestTestCasesEndpoints:
    """testcases 端点行为测试类。"""

    async def test_create_test_case_success(self, client: AsyncClient):
        """创建测试用例成功时返回 201 和 success 状态。"""
        payload = {"id": "case-1", "name": "用例1"}
        response = await client.post(
            "/api/v1/testcases?index_uid=default",
            json=payload,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "success"
        assert data["id"] == "case-1"

    async def test_create_test_case_missing_index_uid(self, client: AsyncClient):
        """缺少 index_uid 时返回 400。"""
        payload = {"id": "case-2"}
        response = await client.post("/api/v1/testcases", json=payload)
        assert response.status_code == 400

    async def test_update_test_case_success(self, client: AsyncClient):
        """更新测试用例成功时返回 200 和 success 状态。"""
        payload = {"id": "case-3", "name": "用例3-更新"}
        response = await client.put(
            "/api/v1/testcases/case-3?index_uid=default",
            json=payload,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["id"] == "case-3"

    async def test_delete_test_case_missing_index_uid(self, client: AsyncClient):
        """删除测试用例时缺少 index_uid 返回 400。"""
        response = await client.delete("/api/v1/testcases/case-4")
        assert response.status_code == 400
