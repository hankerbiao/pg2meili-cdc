"""测试用例端点的测试模块。"""
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app


class TestHealthCheck:
    """健康检查端点测试类。"""

    @pytest.fixture
    async def client(self) -> AsyncClient:
        """创建测试客户端。"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            yield ac

    async def test_health_check(self, client: AsyncClient):
        """测试健康检查端点。"""
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAPIRoutes:
    """API 路由结构验证测试类（无数据库）。"""

    @pytest.fixture
    async def client(self) -> AsyncClient:
        """创建测试客户端。"""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=True,
        ) as ac:
            yield ac

    def test_testcases_endpoint_exists(self, client: AsyncClient):
        """验证 testcases POST 端点已注册。"""
        # 检查路由是否在应用的路由中
        routes = [r for r in app.routes if hasattr(r, 'path')]
        testcases_routes = [r for r in routes if '/testcases' in r.path]
        assert len(testcases_routes) > 0, "testcases 端点应该已注册"

    def test_delete_endpoint_exists(self, client: AsyncClient):
        """验证 testcases DELETE 端点已注册。"""
        routes = [r for r in app.routes if hasattr(r, 'path')]
        delete_routes = [r for r in routes if '/testcases/{id}' in r.path and hasattr(r, 'methods') and 'DELETE' in r.methods]
        assert len(delete_routes) > 0, "DELETE /testcases/{id} 端点应该已注册"

    def test_post_endpoint_methods(self, client: AsyncClient):
        """验证 testcases POST 端点接受 POST 方法。"""
        routes = [r for r in app.routes if hasattr(r, 'path')]
        post_routes = [r for r in routes if '/testcases' in r.path and hasattr(r, 'methods') and 'POST' in r.methods]
        assert len(post_routes) > 0, "POST /testcases 端点应该接受 POST 方法"