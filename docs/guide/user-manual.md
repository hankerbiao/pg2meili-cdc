# UniData 快速上手指南 🚀

欢迎使用 **UniData**！本指南将带你从零开始，完成从获取 Token 到数据写入、搜索的完整流程。

## 🎯 适用人群

| 角色 | 场景 |
| :--- | :--- |
| 👨‍💻 **业务开发** | 接入数据管理与搜索能力，构建业务应用 |
| 🛡️ **运维/管理员** | 审核 Token、监控数据流向 |
| 🕵️ **测试/运营** | 验证数据写入情况，体验搜索效果 |

---

## 🏗️ 系统架构：数据是怎么流转的？


**核心流程拆解：**

1.  **写入 📝**：你调用 API 把文档存入 PostgreSQL。
2.  **监听 👂**：Debezium 发现数据库变动，把事件发到 Kafka。
3.  **同步 🔄**：Go 服务消费消息，把数据搬运到 Meilisearch 节点。
4.  **搜索 🔍**：用户发起搜索，直接从最近的 Meilisearch 节点获取毫秒级响应！

![写入/搜索链路示意](/images/write-search-flow.svg)

---

## ⚡ 极速上手：4步搞定

### 1️⃣ 申请通行证 (Token)

1.  访问 **自助申请页面**：`http://后端服务:8080/app/register`
2.  填写你的应用名称和应用信息：
    *   `app_name`：应用唯一标识（建议和服务名保持一致）
    *   `失效日期`：给 Token 设置个有效期
    *   `接收人 ITCode`：Token 发给谁
3.  提交后静待管理员审核（状态 `pending` -> `approved`）。
4.  审核通过后，Token 会通过**内部光圈**飞到你的消息列表里 📩。

**🔥 验证一下：**
拿到 Token 后，用 curl 测一下通不通（记得替换 `<API_HOST>` 和 `<jwt>`）：

```bash
curl -X GET "http://<API_HOST>/api/v1/health" \
  -H "Authorization: Bearer <jwt>"
```
看到成功的响应，就说明你已经 ready 啦！🎉

### 2️⃣ 选好你的“地盘” (Collection/Index)

*   **写入时**：想好你的集合名 (`collection`)，比如 `testcases` (测试用例) 或 `requirements` (需求文档)。
*   **搜索时**：确认索引名（通常就是集合名）。

### 3️⃣ 写入第一条数据 💾

有了 Token 和集合名，我们来写入一条测试数据。

**接口地址**：`POST /api/v1/data/{collection}`

```http
POST /api/v1/data/demo_collection
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "id": "hello_world_001",
  "title": "Hello UniData",
  "content": "这是我的第一条数据，希望能被搜到！🚀"
}
```

### 4️⃣ 搜索一下 🔎

数据同步通常只需几秒钟。现在尝试从搜索服务（Search Service）把刚才的数据找出来。

**注意**：搜索服务通常和写入服务是分开部署的，可以通过后端 UniData 服务接口获取)。

```http
POST http://<SEARCH_HOST>/search
Authorization: Bearer <jwt>
Content-Type: application/json

{
  "q": "第一条数据",
  "limit": 5
}
```

如果返回了刚才写入的内容，恭喜你，流程跑通了！🥂

---

## 🛠️ 避坑指南 & 排障 (Troubleshooting)

遇到问题别慌，对着清单查一遍：

### 🛑 401 / 403 鉴权失败
*   Token 是不是过期了？📅
*   Token 和 `app_name` 匹配吗？别拿前朝的剑斩本朝的官。
*   Header 里加了 `Authorization: Bearer ...` 吗？

### 👻 写入成功但搜不到
*   **让子弹飞一会儿**：CDC 同步有延迟，喝口水再试。
*   **索引名对吗**：写入的 `collection` 和搜索的 `index` 是一回事吗？
*   **关键词**：确定你搜的词真的在 `content` 或 `title` 里吗？

### 💥 请求超时 / 5xx
*   服务挂了吗？调一下 `/health` 看看心跳。💓
*   网通吗？是不是 VPN 没连或者防火墙挡住了。

---

## 🤝 最佳实践

1.  **先申请，后接入**：不要等到代码上线了才发现没 Token。
2.  **环境隔离**：测试环境玩坏了没关系，生产环境请谨慎。
3.  **命名规范**：集合名最好顾名思义，别叫 `temp123` 这种。

## 🚪 传送门

想要了解更多细节？请移步：

*   [📚 数据管理 API 详解](/management/index)
*   [🔎 搜索 API 高级用法](/search/index)
*   [🚢 部署与运维指南](/deployment/index)

祝你使用愉快！Happy Coding! 💻✨
