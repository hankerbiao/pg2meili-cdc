#!/usr/bin/env python3
"""极简版：MongoDB -> UniData 全量同步。

只做两件事：读 Mongo 集合，批量 upsert 进 UniData。
幂等，可重复跑。

用法:
    UNIDATA_API_KEY=<key> python sync_quality_monitoring.py
    # 或指定集合/目标:
    UNIDATA_API_KEY=<key> MONGO_COLLECTION=fault_info TARGET_COLLECTION=quality_monitoring \
        python sync_quality_monitoring.py
"""
import os
from datetime import datetime

from bson import Decimal128, ObjectId
from pymongo import MongoClient
from unidata_sdk import UniDataClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://10.17.154.252:27019")
MONGO_DB = os.environ.get("MONGO_DB", "quality_monitoring")
COLLECTION = os.environ.get("MONGO_COLLECTION", "fault_info")
TARGET = os.environ.get("TARGET_COLLECTION", COLLECTION)  # UniData 目标集合名
UNIDATA_URL = os.environ.get("UNIDATA_URL", "http://127.0.0.1:8080")
API_KEY = os.environ["UNIDATA_API_KEY"]  # 必填，勿硬编码
BATCH = 200


def clean(v):
    """递归把 BSON 类型转成 JSON 可序列化值。"""
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, Decimal128):
        return str(v.to_decimal())
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    return v


def to_doc(doc):
    """Mongo 文档 -> UniData 文档：_id 转为字符串 id。"""
    doc = clean(dict(doc))
    doc["id"] = str(doc.pop("_id"))
    return doc


def main():
    docs = list(MongoClient(MONGO_URI)[MONGO_DB][COLLECTION].find({}))
    print(f"read {len(docs)} docs from {MONGO_DB}.{COLLECTION}")

    client = UniDataClient(UNIDATA_URL, API_KEY)
    for i in range(0, len(docs), BATCH):
        batch = [to_doc(d) for d in docs[i : i + BATCH]]
        # 批内 id 去重，避免 batch 接口 422
        seen, unique = set(), []
        for d in batch:
            if d["id"] not in seen:
                seen.add(d["id"])
                unique.append(d)
        res = client.upsert_documents(TARGET, unique)
        print(f"batch {i // BATCH + 1}: {res.count or len(unique)} upserted")

    print("done")


if __name__ == "__main__":
    main()
