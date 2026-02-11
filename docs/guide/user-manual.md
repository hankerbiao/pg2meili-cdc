# 用户引导手册

本指南面向首次接触 **UniData** 的使用者，覆盖从申请 Token 到写入与搜索的完整流程。

## 适用人群

| 角色 | 场景 |
| :--- | :--- |
| **业务开发** | 接入数据管理与搜索能力，构建业务应用 |
| **运维/管理员** | 审核 Token、监控数据流向 |
| **测试/运营** | 验证数据写入情况，体验搜索效果 |


## 系统架构与数据流转

**核心流程概览：**

1.  **写入**：通过 API 将文档写入 PostgreSQL。
2.  **监听**：Debezium 捕获数据库变更并写入 Kafka。
3.  **同步**：Go 服务消费消息并同步到 Meilisearch 节点。
4.  **搜索**：请求就近访问搜索节点，获取低延迟结果。

 
## 快速上手（4 步）

### 1. 申请 Token

1.  访问自助申请页面：`http://后端服务:8080/app/register`
2.  填写申请信息：
    *   `app_name`：应用唯一标识（建议与服务名一致）
    *   `失效日期`：Token 过期时间
    *   `接收人 ITCode`：Token 下发目标用户
3.  提交后等待管理员审核（状态 `pending` -> `approved`）。
4.  审核通过后，Token 将通过内部光圈下发。
![token 获取.png](../public/images/token%20%E8%8E%B7%E5%8F%96.png))
**验证方式：**  
拿到 Token 后，可用 curl 验证连通性（替换 `<API_HOST>` 与 `<jwt>`）：

```bash
curl -X GET "http://<API_HOST>/api/v1/health" \
  -H "Authorization: Bearer <jwt>"
```
看到成功响应说明鉴权与网络正常。

::: tip 💡 核心概念：URL 与 Token 对应关系
请务必区分 **管理端** 与 **搜索端**。由于架构上的解耦，两者的访问地址与权限令牌是不同的：

| 类型 | 常用 URL 示例 | 对应 Token 权限 | 适用场景 |
| :--- | :--- | :--- | :--- |
| **管理** | `http://<API_HOST>/api/v1/data/{collection}` | `data:read`, `data:write` | 索引创建、数据上报、后台管理 |
| **搜索** | `http://<SEARCH_HOST>/search?collection=xxx` | `search:read` | 前端搜索界面、极速检索请求 |
:::



### 2. 选择集合与索引

*   **写入时**：确定集合名（`collection`），如 `testcases`、`requirements`。
*   **搜索时**：确认索引名（通常与集合名一致）。

### 3. 写入第一条数据

有了 Token 和集合名后，写入一条测试数据：

**接口地址**：`POST /api/v1/data/{collection}`

```http
POST /api/v1/data/demo_collection
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "id": "hello_world_001",
  "title": "Hello UniData",
  "content": "这是我的第一条数据，希望能被搜到。"
}
```

### 4. 发起搜索

数据同步通常在数秒内完成。随后可通过搜索服务检索数据。  
**注意**：搜索服务通常与写入服务分开部署，可通过 UniData 查询在线搜索节点。

```http
POST http://<SEARCH_HOST>/search?collection=demo_collection
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "q": "第一条数据",
  "limit": 5
}
```

若返回刚才写入的数据，说明流程已跑通。

**最佳实践（选择最优 Search IP）：**

1. 前端定期调用 UniData 的在线节点接口（`/api/v1/agents/online`）获取可用的搜索节点 IP 列表。
2. 获取 IP 列表的方法与示例请参考「搜索接口说明」中的 **代理节点在线列表** 部分。
3. 对候选 IP 进行轻量测速（如 `/health` 或一次空搜索请求），选择响应最快的节点。
4. 将最佳节点地址保存到本地缓存（如 localStorage），后续搜索请求优先使用该地址。
5. 可设置定时刷新（例如每 10~30 分钟）重新评估节点，保证持续可用与低延迟。


## 排障指南

常见问题可按以下清单排查：

### 401 / 403 鉴权失败
*   Token 是否过期
*   Token 与 `app_name` 是否匹配
*   请求头是否包含 `Authorization: Bearer ...`

### 写入成功但搜不到
*   CDC 同步存在延迟
*   写入的 `collection` 与搜索 `index` 是否一致
*   关键词是否存在于 `content` / `title`

### 请求超时 / 5xx
*   服务是否存活，可访问 `/health` 验证
*   网络链路是否可达（VPN/防火墙）


## 相关文档

更多文档：

*   [数据管理 API 详解](/management/index)
*   [搜索 API 高级用法](/search/index)
*   [部署与运维指南](/deployment/index)
