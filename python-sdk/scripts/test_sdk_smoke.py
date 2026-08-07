#!/usr/bin/env python3
"""UniData SDK 数据写入/读取/搜索 smoke 测试。

全链路通过 SDK 完成：
  1. 写入：data_client.upsert_document()            （backend-data key, data:write）
  2. 读回：data_client.get_document()                （backend-data key, data:read）
  3. 搜索：search_client.search()                    （frontend-search key, search:read）
     —— 写入经 outbox → Debezium → Kafka → Go Sync → Meilisearch 异步同步

搜索带重试机制，最多等待 30s 等 CDC 管道完成同步。
"""
import os
import time
import uuid

from unidata_sdk import UniDataClient

# ---- 配置 ----
BASE_URL = os.getenv("UNIDATA_BASE_URL", "http://127.0.0.1:8080")
SEARCH_URL = os.getenv("UNIDATA_SEARCH_URL", "http://127.0.0.1:8091")

WRITE_KEY = os.environ["UNIDATA_WRITE_KEY"]
SEARCH_KEY = os.environ["UNIDATA_SEARCH_KEY"]

COLLECTION = "smoke_cases"

# 生成一些 mock 测试数据
MOCK_DOCS = [
    {"id": f"case-{uuid.uuid4().hex[:8]}", "title": "Power management test case",
     "status": "active", "priority": "P1"},
    {"id": f"case-{uuid.uuid4().hex[:8]}", "title": "Network connectivity test",
     "status": "draft", "priority": "P2"},
    {"id": f"case-{uuid.uuid4().hex[:8]}", "title": "Disk I/O performance test",
     "status": "active", "priority": "P1"},
]


def step(name: str) -> None:
    print(f"\n=== {name} ===")


def main() -> None:
    data_client = UniDataClient(base_url=BASE_URL, api_key=WRITE_KEY)
    search_client = UniDataClient(base_url=BASE_URL, api_key=SEARCH_KEY,
                                   search_url=SEARCH_URL)

    # ── 1. 批量写入 mock 数据 ──
    step("1. 写入 mock 文档 (data:write)")
    doc_ids: list[str] = []
    for doc in MOCK_DOCS:
        result = data_client.upsert_document(COLLECTION, doc)
        assert result.status == "success", f"写入失败: {result.status}"
        doc_ids.append(result.id)
        print(f"  ✅ {result.id}  title={doc['title'][:30]}  priority={doc['priority']}")

    # ── 2. 按 ID 逐个读回 ──
    step("2. 按 ID 读回验证 (data:read)")
    for i, doc_id in enumerate(doc_ids):
        fetched = data_client.get_document(COLLECTION, doc_id)
        expected = MOCK_DOCS[i]
        assert fetched["id"] == expected["id"], f"ID 不一致: {fetched['id']}"
        assert fetched["title"] == expected["title"], f"title 不一致"
        print(f"  ✅ {doc_id} → {fetched['title'][:30]}")

    # ── 3. 搜索验证 (带重试，等待 CDC) ──
    step("3. 搜索验证 (search:read)，等待 CDC 同步（最多 30s）")
    for doc in MOCK_DOCS:
        query = doc["title"].split()[0]
        found = False
        for attempt in range(1, 11):
            time.sleep(3)
            try:
                sr = search_client.search(COLLECTION, query=query, limit=20)
                hit_ids = [h.get("id") for h in sr.hits]
                if doc["id"] in hit_ids:
                    print(f"  ✅ '{query}' → {doc['id']} (attempt {attempt})")
                    found = True
                    break
                print(f"  ⏳ '{query}' [{attempt}/10] not yet — {sr.estimated_total_hits} hits")
            except Exception as e:
                print(f"  ⏳ '{query}' [{attempt}/10] {e}")
        assert found, f"搜索超时: {doc['id']} 未在 30s 内被 CDC 同步"

    print(f"\n✅ 全链路通过：{len(MOCK_DOCS)} 篇文档 → 写入/读回/搜索 全部一致")


if __name__ == "__main__":
    main()
