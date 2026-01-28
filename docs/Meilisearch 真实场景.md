# Meilisearch 常用接口速查表（基于真实文档示例）

本文档整理了 Meilisearch 的核心接口，涵盖索引管理、文档操作及常用搜索场景。所有接口均需携带请求头 `X-Meili-API-Key`，默认端口为 7700。

---

## 一、基础配置与信息接口

### 1.1 服务启动与连接配置

| 配置项 | 说明 |
|--------|------|
| 启动命令 | `docker run -d -p 7700:7700 -e MEILI_MASTER_KEY=your_master_key getmeili/meilisearch:v1.7` |
| 接口基础地址 | `http://localhost:7700` |
| 必选请求头 | `X-Meili-API-Key: your_master_key` |
| 示例索引名 | `test_cases`（测试用例索引） |

### 1.2 基础信息接口

| 接口功能 | 请求方式 | 请求地址 | 说明 |
|----------|----------|----------|------|
| 获取版本信息 | GET | `/version` | 返回 Meilisearch 的版本号、提交 SHA 和提交日期 |
| 健康检查 | GET | `/health` | 返回服务状态，`{"status":"available"}` 表示服务正常 |

**版本信息请求示例：**
```bash
curl -X GET 'http://localhost:7700/version' \
-H 'X-Meili-API-Key: your_master_key'
```

**健康检查请求示例：**
```bash
curl -X GET 'http://localhost:7700/health' \
-H 'X-Meili-API-Key: your_master_key'
```

---

## 二、索引管理接口

索引是 Meilisearch 存储文档的容器，所有文档归属于某个索引。

### 2.1 索引管理接口列表

| 接口功能 | 请求方式 | 请求地址 | 请求体参数 | 说明 |
|----------|----------|----------|------------|------|
| 创建索引 | POST | `/indexes` | `{"uid": "test_cases", "primaryKey": "id"}` | 创建新索引，`uid` 为必填唯一标识 |
| 获取所有索引 | GET | `/indexes` | 无 | 返回当前实例下的所有索引列表 |
| 获取单个索引 | GET | `/indexes/{uid}` | 无 | 根据索引 UID 获取详细信息 |
| 删除索引 | DELETE | `/indexes/{uid}` | 无 | 永久删除指定索引及其文档 |

### 2.2 索引操作请求示例

**创建索引（指定主键）：**
```bash
curl -X POST 'http://localhost:7700/indexes' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "uid": "test_cases",
  "primaryKey": "id"
}'
```

**获取所有索引：**
```bash
curl -X GET 'http://localhost:7700/indexes' \
-H 'X-Meili-API-Key: your_master_key'
```

**获取单个索引信息：**
```bash
curl -X GET 'http://localhost:7700/indexes/test_cases' \
-H 'X-Meili-API-Key: your_master_key'
```

**删除索引：**
```bash
curl -X DELETE 'http://localhost:7700/indexes/test_cases' \
-H 'X-Meili-API-Key: your_master_key'
```

---

## 三、文档管理接口

文档是 Meilisearch 的搜索对象，以 JSON 格式存储，支持批量操作。

### 3.1 文档管理接口列表

| 接口功能 | 请求方式 | 请求地址 | 请求体参数 | 说明 |
|----------|----------|----------|------------|------|
| 批量添加文档 | POST | `/indexes/{uid}/documents` | 文档数组 | 批量添加文档，主键冲突时会自动更新 |
| 获取单个文档 | GET | `/indexes/{uid}/documents/{id}` | 无 | 根据文档主键获取完整文档信息 |
| 批量更新文档 | PUT | `/indexes/{uid}/documents` | 文档数组 | 主键匹配则更新，否则新增 |
| 批量删除文档 | POST | `/indexes/{uid}/documents/delete-batch` | 主键数组 | 根据主键数组批量删除文档 |

### 3.2 真实文档数据示例

以下文档数据用于后续所有搜索场景的演示：

```json
[
  {
    "id": "66c46c589ec5d1471b49c8d2",
    "author": "乔海丽",
    "creation_ts": "2024-08-20 18:13",
    "lab": "BMC",
    "ext_id": "BMC-88428",
    "name": "电源线缆故障监控测试",
    "summary": "当电源线缆被拔出，但电源模块仍在位发生 AC Lost 时，该电源的输入电压、输出电压、输入功耗、输出功耗及电压风扇转速均跳过监控，对应传感器放在禁用中",
    "status": "启用",
    "paths": ["PSU failure warning"],
    "updater": "陈梦洁",
    "update_ts": "2025-08-21 09:27",
    "tags": ["BHS_G60", "EVT", "DVT", "HighPassRate"],
    "phases": ["EVT", "DVT"],
    "automation": ["手动执行"],
    "full_exec_range": [15],
    "manual_exec_range": [15],
    "os_list": ["Linux"],
    "variation_settings": [],
    "videos": [],
    "scores": "不适用",
    "requirement_count": 3,
    "bug_count": 0,
    "pass_rate": 1,
    "fail_rate": 0,
    "block_rate": 0,
    "utility": 1.2,
    "executed": 5,
    "variations": 1,
    "enabled_tcv": 1,
    "disabled_tcv": 0,
    "reviewed_tcv": 1,
    "not_reviewed_tcv": 0
  },
  {
    "id": "66c46c589ec5d1471b49c8d3",
    "author": "张伟",
    "creation_ts": "2024-08-21 10:30",
    "lab": "BIOS",
    "ext_id": "BIOS-88429",
    "name": "CPU温度过高保护测试",
    "summary": "测试当CPU温度超过阈值时，系统是否能够正确触发保护机制，包括降频和关机操作",
    "status": "启用",
    "paths": ["Temperature protection"],
    "updater": "李娜",
    "update_ts": "2025-08-22 14:15",
    "tags": ["Thermal", "EVT", "HighPriority"],
    "phases": ["EVT", "DVT", "PVT"],
    "automation": ["自动执行"],
    "full_exec_range": [10, 20, 30],
    "manual_exec_range": [10, 20],
    "os_list": ["Linux", "Windows"],
    "variation_settings": [],
    "videos": [],
    "scores": "95",
    "requirement_count": 5,
    "bug_count": 1,
    "pass_rate": 0.95,
    "fail_rate": 0.05,
    "block_rate": 0,
    "utility": 2.5,
    "executed": 20,
    "variations": 3,
    "enabled_tcv": 3,
    "disabled_tcv": 1,
    "reviewed_tcv": 2,
    "not_reviewed_tcv": 1
  },
  {
    "id": "66c46c589ec5d1471b49c8d4",
    "author": "王芳",
    "creation_ts": "2024-08-22 09:00",
    "lab": "BMC",
    "ext_id": "BMC-88430",
    "name": "内存ECC错误检测测试",
    "summary": "验证BMC能够正确检测和报告内存ECC错误，包括单比特错误和双比特错误",
    "status": "启用",
    "paths": ["Memory error detection"],
    "updater": "王芳",
    "update_ts": "2025-08-23 11:45",
    "tags": ["Memory", "DVT", "ECC"],
    "phases": ["DVT"],
    "automation": ["手动执行"],
    "full_exec_range": [5],
    "manual_exec_range": [5],
    "os_list": ["Linux"],
    "variation_settings": [],
    "videos": [],
    "scores": "88",
    "requirement_count": 8,
    "bug_count": 2,
    "pass_rate": 0.8,
    "fail_rate": 0.15,
    "block_rate": 0.05,
    "utility": 1.8,
    "executed": 40,
    "variations": 1,
    "enabled_tcv": 1,
    "disabled_tcv": 0,
    "reviewed_tcv": 0,
    "not_reviewed_tcv": 1
  }
]
```

### 3.3 文档操作请求示例

**批量添加文档：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/documents' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '[
  {
    "id": "66c46c589ec5d1471b49c8d2",
    "author": "乔海丽",
    "creation_ts": "2024-08-20 18:13",
    "lab": "BMC",
    "ext_id": "BMC-88428",
    "name": "电源线缆故障监控测试",
    "summary": "当电源线缆被拔出，但电源模块仍在位发生 AC Lost 时，该电源的输入电压、输出电压、输入功耗、输出功耗及电压风扇转速均跳过监控，对应传感器放在禁用中",
    "status": "启用",
    "paths": ["PSU failure warning"],
    "updater": "陈梦洁",
    "update_ts": "2025-08-21 09:27",
    "tags": ["BHS_G60", "EVT", "DVT", "HighPassRate"],
    "phases": ["EVT", "DVT"],
    "automation": ["手动执行"],
    "full_exec_range": [15],
    "manual_exec_range": [15],
    "os_list": ["Linux"],
    "variation_settings": [],
    "videos": [],
    "scores": "不适用",
    "requirement_count": 3,
    "bug_count": 0,
    "pass_rate": 1,
    "fail_rate": 0,
    "block_rate": 0,
    "utility": 1.2,
    "executed": 5,
    "variations": 1,
    "enabled_tcv": 1,
    "disabled_tcv": 0,
    "reviewed_tcv": 1,
    "not_reviewed_tcv": 0
  },
  {
    "id": "66c46c589ec5d1471b49c8d3",
    "author": "张伟",
    "creation_ts": "2024-08-21 10:30",
    "lab": "BIOS",
    "ext_id": "BIOS-88429",
    "name": "CPU温度过高保护测试",
    "summary": "测试当CPU温度超过阈值时，系统是否能够正确触发保护机制，包括降频和关机操作",
    "status": "启用",
    "paths": ["Temperature protection"],
    "updater": "李娜",
    "update_ts": "2025-08-22 14:15",
    "tags": ["Thermal", "EVT", "HighPriority"],
    "phases": ["EVT", "DVT", "PVT"],
    "automation": ["自动执行"],
    "full_exec_range": [10, 20, 30],
    "manual_exec_range": [10, 20],
    "os_list": ["Linux", "Windows"],
    "variation_settings": [],
    "videos": [],
    "scores": "95",
    "requirement_count": 5,
    "bug_count": 1,
    "pass_rate": 0.95,
    "fail_rate": 0.05,
    "block_rate": 0,
    "utility": 2.5,
    "executed": 20,
    "variations": 3,
    "enabled_tcv": 3,
    "disabled_tcv": 1,
    "reviewed_tcv": 2,
    "not_reviewed_tcv": 1
  }
]'
```

**获取单个文档：**
```bash
curl -X GET 'http://localhost:7700/indexes/test_cases/documents/66c46c589ec5d1471b49c8d2' \
-H 'X-Meili-API-Key: your_master_key'
```

**批量更新文档：**
```bash
curl -X PUT 'http://localhost:7700/indexes/test_cases/documents' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '[
  {
    "id": "66c46c589ec5d1471b49c8d2",
    "status": "禁用",
    "updater": "王芳",
    "update_ts": "2025-08-24 16:30",
    "pass_rate": 0.9,
    "executed": 10
  }
]'
```

**批量删除文档：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/documents/delete-batch' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '["66c46c589ec5d1471b49c8d3", "66c46c589ec5d1471b49c8d4"]'
```

---

## 四、搜索场景接口（核心功能）

搜索接口地址为 `/indexes/{index_uid}/search`，支持 GET 和 POST 两种方式。POST 方式适合传递复杂参数。

### 4.1 搜索场景速查表

| 场景 | 搜索地址 | 关键参数 | 前置配置 |
|------|----------|----------|----------|
| 基础全文搜索 | `/indexes/test_cases/search` | `q`: 搜索关键词 | 无 |
| 分页搜索 | `/indexes/test_cases/search` | `q`, `hitsPerPage`, `page` | 无 |
| 过滤搜索 | `/indexes/test_cases/search` | `q`, `filter` | 设置 `filterableAttributes` |
| 排序搜索 | `/indexes/test_cases/search` | `q`, `sort` | 设置 `sortableAttributes` |
| 模糊搜索 | `/indexes/test_cases/search` | `q`, `fuzzy` | 无 |
| 高亮显示 | `/indexes/test_cases/search` | `q`, `highlight` | 无 |
| 限制返回字段 | `/indexes/test_cases/search` | `q`, `attributesToRetrieve` | 无 |

### 4.2 场景1：基础全文搜索

搜索包含指定关键词的所有测试用例。

| 参数 | 类型 | 说明 |
|------|------|------|
| q | String | 搜索关键词，会在所有可搜索字段中匹配 |

**请求示例（搜索包含"电源"的测试用例）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "电源"
}'
```

**请求示例（搜索包含"BMC"的测试用例）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "BMC"
}'
```

### 4.3 场景2：分页搜索

支持按页码和每页数量进行分页查询。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| q | String | 空字符串 | 搜索关键词 |
| hitsPerPage | Integer | 20 | 每页返回的结果数量 |
| page | Integer | 1 | 页码，从 1 开始 |

**请求示例（搜索"测试"，每页2条，获取第1页）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "测试",
  "hitsPerPage": 2,
  "page": 1
}'
```

### 4.4 场景3：过滤搜索

根据指定条件筛选结果，支持等于、范围、包含等语法。

**前置配置：**
```bash
curl -X PUT 'http://localhost:7700/indexes/test_cases/settings' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "filterableAttributes": ["lab", "status", "phases", "automation", "os_list", "pass_rate", "executed", "requirement_count"]
}'
```

**过滤语法说明：**

| 语法类型 | 示例 | 说明 |
|----------|------|------|
| 等于 | `lab = BMC` | 精确匹配字段值 |
| 等于 | `status = 启用` | 精确匹配状态 |
| 包含 | `phases IN ["EVT", "DVT"]` | 在指定数组中匹配 |
| 包含 | `os_list IN ["Linux"]` | 操作系统列表中包含Linux |
| 范围 | `pass_rate >= 0.9` | 通过率大于等于0.9 |
| 范围 | `executed >= 10 AND executed <= 50` | 执行次数在指定范围内 |

**请求示例（过滤BMC实验室的测试用例）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "filter": ["lab = BMC"]
}'
```

**请求示例（过滤EVT或DVT阶段的测试用例）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "filter": ["phases IN [\"EVT\", \"DVT\"]"]
}'
```

**请求示例（过滤高通过率的测试用例）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "filter": ["pass_rate >= 0.9"]
}'
```

**请求示例（组合过滤：BMC实验室 + 启用状态 + Linux系统）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "filter": ["lab = BMC", "status = 启用", "os_list IN [\"Linux\"]"]
}'
```

### 4.5 场景4：排序搜索

根据指定字段对搜索结果进行排序。

**前置配置：**
```bash
curl -X PUT 'http://localhost:7700/indexes/test_cases/settings' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "sortableAttributes": ["pass_rate", "executed", "requirement_count", "bug_count", "creation_ts"]
}'
```

| 排序标识 | 说明 |
|----------|------|
| `pass_rate:desc` | 按通过率降序（从高到低） |
| `pass_rate:asc` | 按通过率升序（从低到高） |
| `executed:desc` | 按执行次数降序 |
| `requirement_count:asc` | 按需求数量升序 |

**请求示例（按通过率降序排序）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "sort": ["pass_rate:desc"]
}'
```

**请求示例（按执行次数降序、需求数量升序排序）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "sort": ["executed:desc", "requirement_count:asc"]
}'
```

### 4.6 场景5：模糊搜索（容错输入错误）

处理用户输入错误，支持配置最大编辑距离和前缀长度。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| fuzzy.maxEdits | Integer | 1 | 允许的字符编辑次数（0/1/2） |
| fuzzy.prefixLength | Integer | 1 | 前缀固定长度（前N个字符不模糊） |

**请求示例（搜索"电源线"，允许1个字符编辑错误）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "电源线",
  "fuzzy": {
    "maxEdits": 1,
    "prefixLength": 1
  }
}'
```

### 4.7 场景6：高亮显示匹配内容

在返回结果中标记匹配的关键词，便于用户识别匹配位置。

| 参数 | 类型 | 说明 |
|------|------|------|
| highlight.enabled | Boolean | 是否启用高亮功能 |
| highlight.attributes | Array | 需要高亮的字段列表 |
| highlight.preTag | String | 高亮开始标签，默认 `<em>` |
| highlight.postTag | String | 高亮结束标签，默认 `</em>` |

**请求示例：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "电源",
  "highlight": {
    "enabled": true,
    "attributes": ["name", "summary"],
    "preTag": "<em>",
    "postTag": "</em>"
  }
}'
```

**返回示例：** `"name": "<em>电源</em>线缆故障监控测试"`

### 4.8 场景7：限制返回字段

只返回指定字段，减少网络传输数据量。

| 参数 | 类型 | 说明 |
|------|------|------|
| attributesToRetrieve | Array | 需要返回的字段列表，数组形式 |

**请求示例（只返回 id、name、lab、status、pass_rate 字段）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "",
  "attributesToRetrieve": ["id", "name", "lab", "status", "pass_rate"]
}'
```

### 4.9 场景8：综合搜索示例

结合全文搜索、过滤、排序、字段限制的综合搜索场景。

**请求示例（搜索包含"监控"的测试用例，筛选BMC实验室，按执行次数排序，只返回核心字段）：**
```bash
curl -X POST 'http://localhost:7700/indexes/test_cases/search' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "q": "监控",
  "filter": ["lab = BMC"],
  "sort": ["executed:desc"],
  "hitsPerPage": 10,
  "attributesToRetrieve": ["id", "name", "author", "pass_rate", "executed"]
}'
```

---

## 五、索引设置管理

### 5.1 设置相关接口

| 接口功能 | 请求方式 | 请求地址 | 说明 |
|----------|----------|----------|------|
| 更新索引设置 | PUT | `/indexes/{uid}/settings` | 更新可过滤、可排序、可搜索等属性 |
| 重置设置 | DELETE | `/indexes/{uid}/settings` | 将索引设置恢复为默认值 |

### 5.2 常用设置参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| filterableAttributes | Array | 可用于过滤的字段列表 |
| sortableAttributes | Array | 可用于排序的字段列表 |
| searchableAttributes | Array | 搜索时参与匹配的字段列表及权重 |
| displayedAttributes | Array | 搜索结果中返回的完整字段列表 |

### 5.3 推荐配置示例

```bash
curl -X PUT 'http://localhost:7700/indexes/test_cases/settings' \
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
-d '{
  "filterableAttributes": [
    "lab",
    "status",
    "phases",
    "automation",
    "os_list",
    "tags",
    "pass_rate",
    "executed",
    "requirement_count",
    "bug_count"
  ],
  "sortableAttributes": [
    "pass_rate",
    "executed",
    "requirement_count",
    "bug_count",
    "creation_ts",
    "update_ts"
  ],
  "searchableAttributes": [
    "name^5",
    "summary^3",
    "ext_id^4",
    "tags^2",
    "author",
    "updater",
    "paths"
  ],
  "displayedAttributes": [
    "*"
  ]
}'
```

**参数说明：**
- **filterableAttributes**: 定义哪些字段可用于过滤搜索，支持精确匹配、范围查询和数组包含
- **sortableAttributes**: 定义哪些字段可用于排序，支持升序和降序
- **searchableAttributes**: 定义搜索时参与匹配的字段及权重，`^` 后面的数字表示权重倍数
- **displayedAttributes**: 定义搜索结果中返回的完整字段，`["*"]` 表示返回所有字段

**重置所有设置为默认值：**
```bash
curl -X DELETE 'http://localhost:7700/indexes/test_cases/settings' \
-H 'X-Meili-API-Key: your_master_key'
```

---

## 六、完整请求头模板

所有接口均需携带以下请求头：

```bash
-H 'X-Meili-API-Key: your_master_key' \
-H 'Content-Type: application/json' \
```

**注意：** `Content-Type` 请求头仅在发送请求体时需要携带。

---

## 七、字段索引速查

| 字段名 | 类型 | 可搜索 | 可过滤 | 可排序 | 说明 |
|--------|------|--------|--------|--------|------|
| id | String | ✓ | ✓ | - | 文档唯一标识 |
| author | String | ✓ | ✓ | - | 作者 |
| creation_ts | String | ✓ | - | ✓ | 创建时间 |
| lab | String | ✓ | ✓ | - | 实验室 |
| ext_id | String | ✓ | ✓ | - | 外部ID |
| name | String | ✓ | - | - | 名称/标题 |
| summary | String | ✓ | - | - | 摘要描述 |
| status | String | ✓ | ✓ | - | 状态 |
| paths | Array[String] | ✓ | - | - | 路径 |
| updater | String | ✓ | ✓ | - | 更新者 |
| update_ts | String | ✓ | - | ✓ | 更新时间 |
| tags | Array[String] | ✓ | ✓ | - | 标签列表 |
| phases | Array[String] | ✓ | ✓ | - | 阶段列表 |
| automation | Array[String] | ✓ | ✓ | - | 自动化类型 |
| full_exec_range | Array[Number] | - | ✓ | - | 完整执行范围 |
| manual_exec_range | Array[Number] | - | ✓ | - | 手动执行范围 |
| os_list | Array[String] | ✓ | ✓ | - | 操作系统列表 |
| scores | String/Number | - | ✓ | - | 分数 |
| requirement_count | Number | - | ✓ | ✓ | 需求数量 |
| bug_count | Number | - | ✓ | ✓ | Bug数量 |
| pass_rate | Number | - | ✓ | ✓ | 通过率 |
| fail_rate | Number | - | ✓ | ✓ | 失败率 |
| block_rate | Number | - | ✓ | ✓ | 阻塞率 |
| utility | Number | - | - | - | 效用值 |
| executed | Number | - | ✓ | ✓ | 已执行次数 |
| variations | Number | - | - | ✓ | 变体数量 |
| enabled_tcv | Number | - | - | ✓ | 启用的TCV |
| disabled_tcv | Number | - | - | ✓ | 禁用的TCV |
| reviewed_tcv | Number | - | - | ✓ | 已审查的TCV |
| not_reviewed_tcv | Number | - | - | ✓ | 未审查的TCV |

---

## 八、总结

| 类别 | 核心接口 | 关键说明 |
|------|----------|----------|
| 索引管理 | 创建、查询、删除索引 | 索引是文档的容器，需先建索引再操作文档 |
| 文档管理 | 添加、更新、删除文档 | 支持批量操作，主键冲突时自动更新 |
| 全文搜索 | 基础搜索、分页、高亮 | 无需配置即可使用，适合简单搜索场景 |
| 高级搜索 | 过滤、排序 | 需先配置对应属性（filterableAttributes、sortableAttributes） |
| 搜索优化 | 字段权重、模糊匹配 | 提升搜索结果相关性和用户体验 |

**使用建议：**
1. 根据实际业务需求，合理配置 `searchableAttributes` 的字段权重，提升搜索结果相关性
2. 将常用的过滤字段（如 lab、status、phases）加入 `filterableAttributes`，提高过滤效率
3. 将常用的排序字段（如 pass_rate、executed）加入 `sortableAttributes`，支持多维度排序
4. 对于复杂搜索场景，建议组合使用过滤、排序、字段限制等参数