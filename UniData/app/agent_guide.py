"""AI Agent 集成指南构建模块。

本模块职责：
- 定义公开 API 路径 allowlist
- 从 FastAPI OpenAPI 提取公开操作
- 生成 /agent-guide.json 响应
- 生成 /llms.txt 文本内容

不涉及：数据库访问、用户会话、API Key 生成、审计事件。
"""
from typing import Any

# 当前 Guide Schema 版本
GUIDE_SCHEMA_VERSION = "1.0"

# 公开 API 路径 allowlist：(路径, 方法, scope)
# 与 agent-guide.md 第 4 节保持同步
PUBLIC_OPERATIONS: list[tuple[str, str, str]] = [
    ("/api/v1/data/{collection}", "POST", "data:write"),
    ("/api/v1/data/{collection}/batch", "POST", "data:write"),
    ("/api/v1/data/{collection}", "GET", "data:read"),
    ("/api/v1/data/{collection}/{id}", "GET", "data:read"),
    ("/api/v1/data/{collection}/{id}", "DELETE", "data:write"),
    ("/api/v1/indexes", "GET", "data:read"),
    ("/api/v1/indexes/{collection}", "DELETE", "data:write"),
    ("/api/v1/indexes/{collection}/settings", "POST", "data:write"),
    ("/api/v1/agents/online", "GET", "search:read"),
    ("/api/v1/sdk/python/download", "GET", None),  # 无需认证
]

# 需要筛除的路径前缀
EXCLUDED_PREFIXES = [
    "/api/v1/open-platform/",
    "/api/v1/auth/",
    "/api/v1/internal/",
]

# 需要筛除的路径（精确匹配）
EXCLUDED_PATHS_EXACT = [
    "/api/v1/agents/register",
    "/api/v1/agents/cleanup-confirmations",
]

# 平台探针（非业务功能）
EXCLUDED_PATHS_EXACT.extend(["/health", "/ready"])

# Scope 定义
SCOPES = {
    "data:read": {
        "description": "读取文档、列出集合/索引",
        "typical_users": ["后台任务", "只读服务"],
    },
    "data:write": {
        "description": "写入/删除文档、删除索引、更新索引设置",
        "typical_users": ["后端业务服务", "ETL 作业"],
    },
    "search:read": {
        "description": "发现在线区域节点，并使用同一把 Key 调用区域搜索",
        "typical_users": ["前端 BFF", "搜索服务"],
    },
}

# 固定工作流定义
WORKFLOWS = [
    {
        "id": "write_document",
        "title": "写入文档",
        "steps": [
            "在服务端读取 UNIDATA_API_KEY 环境变量",
            "带 data:write scope 调用单条或批量文档写入端点",
            "文档必须有非空 id，其余 JSON 字段可按业务模型扩展",
        ],
        "required_scopes": ["data:write"],
    },
    {
        "id": "read_document",
        "title": "读取文档",
        "steps": [
            "使用 data:read scope 调用单文档或分页列表端点",
            "业务代码从成功 envelope 的 data 字段读取结果",
        ],
        "required_scopes": ["data:read"],
    },
    {
        "id": "configure_index",
        "title": "配置索引",
        "steps": [
            "使用 data:write scope 选择 collection",
            "提交 filterableAttributes 和 sortableAttributes",
            "等待 CDC/区域同步后再依赖对应搜索能力",
        ],
        "required_scopes": ["data:write"],
    },
    {
        "id": "regional_search",
        "title": "区域搜索",
        "steps": [
            "使用 search:read 请求 GET /api/v1/agents/online，可携带目标 region 参数",
            "选择返回的 base_url",
            "将同一 Bearer Key 转发给区域节点的搜索端点",
            "区域节点不可用时重新发现或由 SDK 的节点池处理重试",
        ],
        "required_scopes": ["search:read"],
    },
]

# 代码示例（使用占位值）
EXAMPLES = [
    {
        "language": "python",
        "title": "Python SDK 示例",
        "description": "使用官方 Python SDK 进行文档写入和搜索",
        "code": '''import os
from unidata_sdk import UniDataClient

with UniDataClient(
    "https://meilisearch.1oa.com.cn",
    os.environ["UNIDATA_API_KEY"],
    region="shanghai",
) as client:
    # 写入文档
    client.upsert_document(
        "products",
        {"id": "sku-001", "name": "Mechanical Keyboard", "price": 699},
    )
    # 搜索文档
    result = client.search("products", query="keyboard", limit=10)
    print(result)
''',
    },
    {
        "language": "typescript",
        "title": "TypeScript fetch 示例",
        "description": "使用原生 fetch 进行区域搜索",
        "code": '''const API_KEY = process.env.UNIDATA_API_KEY;
const BASE_URL = "https://meilisearch.1oa.com.cn";

// 1. 写入文档
async function writeDocument(collection: string, doc: object) {
  const response = await fetch(`${BASE_URL}/api/v1/data/${collection}`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(doc),
  });
  if (!response.ok) {
    throw new Error(`写入失败: ${response.statusText}`);
  }
  return response.json();
}

// 2. 发现在线区域节点
async function findOnlineAgent(region?: string) {
  const url = region
    ? `${BASE_URL}/api/v1/agents/online?region=${region}`
    : `${BASE_URL}/api/v1/agents/online`;
  const response = await fetch(url, {
    headers: { "Authorization": `Bearer ${API_KEY}` },
  });
  if (!response.ok) {
    throw new Error(`节点发现失败: ${response.statusText}`);
  }
  const { data: agents } = await response.json();
  return agents[0]; // 选择第一个可用节点
}

// 3. 向区域节点搜索
async function regionalSearch(agentUrl: string, collection: string, query: string) {
  const response = await fetch(`${agentUrl}/api/v1/collections/${collection}/search`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ q: query, limit: 10 }),
  });
  if (!response.ok) {
    throw new Error(`搜索失败: ${response.statusText}`);
  }
  return response.json();
}
''',
    },
]

# 非目标端点说明
NON_TARGETS = [
    {
        "category": "开放平台管理",
        "paths": ["/api/v1/open-platform/*"],
        "reason": "应用、API Key、会话、审计和用户管理接口，不属于业务数据集成",
    },
    {
        "category": "内部认证",
        "paths": ["/api/v1/auth/*"],
        "reason": "管理/OA 身份认证协议，不对外暴露",
    },
    {
        "category": "内部同步",
        "paths": ["/api/v1/internal/*"],
        "reason": "控制面和同步内部接口，节点间使用",
    },
    {
        "category": "区域节点运维",
        "paths": [
            "/api/v1/agents/register",
            "/api/v1/agents/cleanup-confirmations",
        ],
        "reason": "区域节点部署协议，需要 X-Agent-Token，不对业务调用方开放",
    },
    {
        "category": "平台探针",
        "paths": ["/health", "/ready"],
        "reason": "K8s/监控系统探测接口，不是业务功能",
    },
]


def _match_path(pattern: str, path: str) -> bool:
    """路径匹配，支持 {param} 占位符."""
    if pattern == path:
        return True
    pattern_parts = pattern.strip("/").split("/")
    path_parts = path.strip("/").split("/")
    if len(pattern_parts) != len(path_parts):
        return False
    for p, a in zip(pattern_parts, path_parts):
        if p.startswith("{") and p.endswith("}"):
            continue
        if p != a:
            return False
    return True


def _is_excluded(path: str) -> bool:
    """检查路径是否应被筛除."""
    # 精确匹配
    if path in EXCLUDED_PATHS_EXACT:
        return True
    # 前缀匹配
    for prefix in EXCLUDED_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


def _find_operation(
    openapi: dict[str, Any],
    path: str,
    method: str,
) -> dict[str, Any] | None:
    """从 OpenAPI 文档中查找指定路径和方法的操作."""
    paths = openapi.get("paths", {})
    path_item = paths.get(path)
    if path_item is None:
        return None
    return path_item.get(method.lower())


def build_agent_guide(
    openapi: dict[str, Any],
    service_version: str = "0.1.0",
) -> dict[str, Any]:
    """构建 AI Agent 集成指南 JSON.

    Args:
        openapi: FastAPI app.openapi() 返回的完整 OpenAPI 文档
        service_version: 服务版本号（来自 FastAPI app.version）

    Returns:
        符合 schema_version 1.0 的 Guide JSON

    Raises:
        ValueError: allowlist 中的路径在当前 OpenAPI 中不存在
    """
    operations = []

    # 从 allowlist 提取公开操作
    for path, method, scope in PUBLIC_OPERATIONS:
        operation = _find_operation(openapi, path, method)
        if operation is None:
            # SDK 下载端点可能不在 OpenAPI 中，跳过
            if "/sdk/python/download" in path:
                operations.append({
                    "operation_id": "python_sdk_download",
                    "method": method,
                    "path": path,
                    "summary": "下载 Python SDK 源码包",
                    "description": "返回官方 Python SDK 的压缩包，供开发者集成使用。",
                    "required_scopes": [],
                    "openapi_ref": None,
                })
                continue
            raise ValueError(
                f"Agent Guide allowlist 中配置的路径在当前 OpenAPI 中不存在: "
                f"{method.upper()} {path}"
            )

        operation_id = operation.get("operationId", "")
        summary = operation.get("summary", "")
        description = operation.get("description", "")

        operations.append({
            "operation_id": operation_id,
            "method": method.upper(),
            "path": path,
            "summary": summary,
            "description": description,
            "required_scopes": [scope] if scope else [],
            "openapi_ref": f"/openapi.json#/paths/{path.replace('{', '~1').replace('}', '~1')}/{method.upper()}",
        })

    # 构建完整 Guide JSON
    return {
        "schema_version": GUIDE_SCHEMA_VERSION,
        "service": {
            "name": "MeliData",
            "version": service_version,
            "purpose": "Multi-region document storage and search integration service",
        },
        "usage_policy": {
            "mode": "reference_only",
            "direct_agent_execution": False,
            "instruction": (
                "Use this guide to generate integration code for a user. "
                "Do not call service APIs or request credentials on the user's behalf."
            ),
        },
        "links": {
            "openapi": "/openapi.json",
            "human_docs": "/docs",
            "llms": "/llms.txt",
            "python_sdk_download": "/api/v1/sdk/python/download",
        },
        "architecture": {
            "write_path": [
                {
                    "order": 1,
                    "component": "用户应用",
                    "purpose": "发起文档写入请求",
                },
                {
                    "order": 2,
                    "component": "MeliData FastAPI",
                    "purpose": "接收请求，写入 PostgreSQL",
                    "endpoint": "POST /api/v1/data/{collection}",
                },
                {
                    "order": 3,
                    "component": "Debezium CDC",
                    "purpose": "捕获 WAL 变更，发送到 Kafka",
                },
                {
                    "order": 4,
                    "component": "区域 Sync Service",
                    "purpose": "消费 Kafka，异步同步到区域 Meilisearch",
                },
            ],
            "search_path": [
                {
                    "order": 1,
                    "component": "用户应用",
                    "purpose": "请求在线区域节点",
                    "endpoint": "GET /api/v1/agents/online",
                },
                {
                    "order": 2,
                    "component": "MeliData FastAPI",
                    "purpose": "返回在线节点列表（含 base_url）",
                },
                {
                    "order": 3,
                    "component": "用户应用",
                    "purpose": "向节点 base_url 发送搜索请求",
                    "endpoint": "POST {base_url}/api/v1/collections/{collection}/search",
                },
                {
                    "order": 4,
                    "component": "区域 Meilisearch",
                    "purpose": "返回搜索结果",
                },
            ],
        },
        "authentication": {
            "scheme": "Bearer",
            "header": "Authorization",
            "scopes": SCOPES,
            "key_requirements": [
                "API Key 只应由用户的服务端或密钥管理系统保存",
                "禁止写入浏览器打包产物、前端源码、仓库、日志或示例中的常量",
                "按用途和环境分拆 Key，使用最小权限",
                "不要把数据读写和搜索只读混用",
            ],
        },
        "workflows": WORKFLOWS,
        "operations": operations,
        "examples": EXAMPLES,
        "non_targets": NON_TARGETS,
    }


def render_llms_text() -> str:
    """生成 llms.txt 纯文本内容.

    Returns:
        符合 /llms.txt 端点规范的纯文本 Markdown 格式内容
    """
    return """# MeliData

MeliData is a multi-region document storage and search integration service.
This document is reference-only for AI agents generating user integration code; it is not a tool interface.

## Start here
- Agent integration guide: /agent-guide.json
- REST API schema: /openapi.json
- Human API documentation: /docs
- Python SDK download: /api/v1/sdk/python/download

## Boundaries
Use only the public caller APIs identified by /agent-guide.json. Do not use open-platform administration, internal synchronization, or agent registration endpoints for user integrations.

## Public Operations
The following operations are available for user integrations:
- POST /api/v1/data/{collection} (data:write) - Create/update a document
- POST /api/v1/data/{collection}/batch (data:write) - Batch create/update documents
- GET /api/v1/data/{collection} (data:read) - List documents with pagination
- GET /api/v1/data/{collection}/{id} (data:read) - Get single document
- DELETE /api/v1/data/{collection}/{id} (data:write) - Soft delete a document
- GET /api/v1/indexes (data:read) - List collections/indexes
- DELETE /api/v1/indexes/{collection} (data:write) - Delete index
- POST /api/v1/indexes/{collection}/settings (data:write) - Configure index
- GET /api/v1/agents/online (search:read) - Discover online regional nodes

## Regional Search Flow
1. GET /api/v1/agents/online with Authorization: Bearer <key>
2. Select an agent's base_url from the response
3. POST {base_url}/api/v1/collections/{collection}/search with same Bearer key

## Authentication
All data operations require: Authorization: Bearer <api_key>
Keys must be stored server-side, never in client code.
"""
