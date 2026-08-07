#!/usr/bin/env python3
"""UniData 数据写入/读取/搜索 最小 smoke 测试（纯 requests，不依赖 SDK）。

流程：
  1. 写入：POST /api/v1/data/{collection}             （backend-data key, data:write）
  2. 读回：GET  /api/v1/data/{collection}/{id}         （backend-data key, data:read）
  3. 搜索：POST /api/v1/collections/{collection}/search（frontend-search key, search:read）
     —— 写入经 outbox -> Kafka -> Meilisearch 异步同步，先 sleep 等 CDC 落库
"""
import json
import os
import time
import uuid

import requests

# ---- 配置 ----
BASE_URL = "http://127.0.0.1:8080"   # UniData control-plane (FastAPI)
SEARCH_URL = "http://127.0.0.1:8091"  # Meilisearch Sync Service (Go Agent)

WRITE_KEY = os.environ["UNIDATA_WRITE_KEY"]  # data:read, data:write
SEARCH_KEY = os.environ["UNIDATA_SEARCH_KEY"]  # search:read

COLLECTION = "smoke_cases"
DOC = {
    "id": f"case-{uuid.uuid4().hex[:8]}",
    "title": "Power management test case",
    "status": "active",
    "priority": "P1",
}


def headers(key: str) -> dict:
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def step(name: str) -> None:
    print(f"\n=== {name} ===")


step("1. 写入文档 (data:write)")
r = requests.post(
    f"{BASE_URL}/api/v1/data/{COLLECTION}",
    headers=headers(WRITE_KEY),
    json=DOC,
    timeout=10,
)
print(f"POST {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2))
r.raise_for_status()
doc_id = r.json()["data"]["id"]

step("2. 按 ID 读回 (data:read)")
r = requests.get(
    f"{BASE_URL}/api/v1/data/{COLLECTION}/{doc_id}",
    headers=headers(WRITE_KEY),
    timeout=10,
)
print(f"GET {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2))
r.raise_for_status()
assert r.json()["data"]["title"] == DOC["title"], "读回内容不一致"

step(f"3. 搜索 '{DOC['title'].split()[0]}' (search:read)  —— 等待 CDC 同步 3s")
time.sleep(3)
r = requests.post(
    f"{SEARCH_URL}/api/v1/collections/{COLLECTION}/search",
    headers={**headers(SEARCH_KEY), "X-Request-ID": uuid.uuid4().hex},
    json={"q": DOC["title"].split()[0], "limit": 10},
    timeout=10,
)
print(f"POST {r.status_code}")
print(json.dumps(r.json(), ensure_ascii=False, indent=2))
r.raise_for_status()
hits = r.json()["data"].get("hits", [])
assert any(h.get("id") == doc_id for h in hits), f"搜索未命中 {doc_id}"

print(f"\n✅ 全部通过：写入 {doc_id} -> 读回一致 -> 搜索命中")
