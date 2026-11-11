#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""search_outbox -> Meilisearch 历史存量回补脚本。

背景
----
修复 pg-search-outbox-connector 后，Debezium snapshot 把 14 万历史事件全部推入
Kafka，sync 服务逐条 + 等任务串行消费，全量回放约需 30 小时。本脚本绕开 Kafka，
直接从 PostgreSQL 的 search_outbox 读取每个文档的最新状态，按 app_id + collection
分组（对应 Meilisearch 索引）、复用 sync 服务的索引命名与主键约定批量写入，
几分钟内完成存量回补，且与流水线幂等（后续重放/新写入按同一 _meili_id 合并）。

约定（与 Go sync 服务模型严格一致，请勿改动）
----------------------------------------------
  - 索引 UID : "t_" + sha256(app_id).hexdigest()[:16] + "__" + collection
  - 主键字段 : _meili_id = "d_" + urlsafe_base64(document_id)（无 padding）
  - 文档转换 : document 去掉 app_name/app_id/collection/is_delete，再写入
               id = document_id 与 _meili_id（与 handlers.go 一致）
  - 每个 (app_id, collection, document_id) 只取最新 event_version；
    最新 operation=delete 的文档会从 Meilisearch 删除。

依赖：仅 Python 3 标准库（urllib/hashlib/base64）。读取 PostgreSQL 采用
`docker exec <pg容器> psql` 导出；如本机没有 docker，可先用任意方式导出
JSONL 文件再 --jsonl 传入。

用法
----
  # 全量回补（docker 内 postgres）
  python3 scripts/backfill_search_outbox.py --meili-key <MEILI_MASTER_KEY>

  # 只回补指定 collection，并预先查看计划（不实际写入）
  python3 scripts/backfill_search_outbox.py --meili-key xxx \
      --groups sales_orders_sap,cpl_parts --dry-run

  # 使用预导出的 JSONL（无需 docker）
  python3 scripts/backfill_search_outbox.py --meili-key xxx --jsonl outbox.jsonl
"""
import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STRIP_KEYS = ("app_name", "app_id", "collection", "is_delete")
DEFAULT_BATCH = 500
TASK_TIMEOUT_S = 300


# --------------------------------------------------------------------------- #
# 索引 / 主键 / 文档转换（与 meilisearch-sync-service/internal/model 一致）
# --------------------------------------------------------------------------- #
def index_uid(app_id, collection):
    """与 model.IndexUID 一致：t_{sha256(app_id)[:16]}__{collection}。"""
    digest = hashlib.sha256(app_id.encode("utf-8")).hexdigest()[:16]
    return "t_{}__{}".format(digest, collection)


def meili_document_id(document_id):
    """与 model.MeiliDocumentID 一致：d_ + urlsafe_base64(无 padding)。"""
    raw = base64.urlsafe_b64encode(document_id.encode("utf-8")).decode("ascii")
    return "d_" + raw.rstrip("=")


def to_meili_doc(row):
    document = row.get("document")
    if not isinstance(document, dict):
        return None
    doc = dict(document)
    for k in STRIP_KEYS:
        doc.pop(k, None)
    doc["id"] = row["document_id"]
    doc["_meili_id"] = meili_document_id(row["document_id"])
    return doc


# --------------------------------------------------------------------------- #
# 数据源加载
# --------------------------------------------------------------------------- #
DUMP_SQL = """
SELECT row_to_json(t) FROM (
  SELECT DISTINCT ON (app_id, collection, document_id)
         app_id, collection, document_id, operation, document
  FROM public.search_outbox
  ORDER BY app_id, collection, document_id, event_version DESC
) t
"""


def load_from_psql(pg_container, pg_user, pg_db):
    sql = DUMP_SQL.replace("\n", " ").strip()
    cmd = [
        "docker", "exec", pg_container,
        "psql", "-U", pg_user, "-d", pg_db, "-q", "-t", "-A", "-c", sql,
    ]
    print(".. 执行 psql 导出: {}".format(" ".join(cmd[:4])), file=sys.stderr)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError("psql 导出失败: " + (proc.stderr or proc.stdout)[-2000:])
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def load_from_jsonl(path):
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


# --------------------------------------------------------------------------- #
# Meilisearch HTTP 交互（stdlib，绕开本机 http_proxy）
# --------------------------------------------------------------------------- #
class Meili:
    def __init__(self, base_url, api_key):
        self.base = base_url.rstrip("/")
        self.headers = {"Authorization": "Bearer {}".format(api_key)}
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})  # 不使用环境代理
        )

    def _request(self, method, path, body=None):
        url = self.base + path
        headers = dict(self.headers)
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=120) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read() or b""
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"message": raw.decode("utf-8", "replace")}
        except urllib.error.URLError as exc:
            raise RuntimeError("Meilisearch 连接失败 {}: {}".format(self.base, exc))

    def index_pk(self, uid):
        status, payload = self._request("GET", "/indexes/" + urllib.parse.quote(uid))
        if status == 404:
            return None, False
        if status != 200:
            raise RuntimeError("GET /indexes/{} 失败 {}: {}".format(uid, status, payload))
        return payload.get("primaryKey"), True

    def wait_task(self, uid, task_uid):
        deadline = time.time() + TASK_TIMEOUT_S
        while time.time() < deadline:
            status, task = self._request("GET", "/tasks/{}".format(task_uid))
            if status == 200 and task.get("status") in ("succeeded", "failed", "canceled"):
                return task
            time.sleep(0.3)
        raise RuntimeError("等待任务超时 index={} task={}".format(uid, task_uid))

    def add_docs(self, uid, docs):
        path = "/indexes/{}/documents?primaryKey=_meili_id".format(urllib.parse.quote(uid))
        _, payload = self._request("POST", path, docs)
        task_uid = (payload or {}).get("taskUid")
        if not task_uid:
            raise RuntimeError("提交文档未返回 taskUid: {}".format(payload))
        return self.wait_task(uid, task_uid)

    def delete_docs(self, uid, meili_ids):
        path = "/indexes/{}/documents/delete-batches".format(urllib.parse.quote(uid))
        _, payload = self._request("POST", path, meili_ids)
        task_uid = (payload or {}).get("taskUid")
        if not task_uid:
            raise RuntimeError("删除文档未返回 taskUid: {}".format(payload))
        return self.wait_task(uid, task_uid)

    def existing_ids(self, uid, field="_meili_id", page=1000):
        """分页拉取索引中已有的 field 值集合（用于断点续传跳过已写入文档）。"""
        path = "/indexes/{}/documents/fetch".format(urllib.parse.quote(uid))
        seen = set()
        offset = 0
        while True:
            body = {"fields": [field], "limit": page, "offset": offset}
            status, payload = self._request("POST", path, body)
            if status != 200:
                raise RuntimeError("fetch {} 失败 {}: {}".format(uid, status, payload))
            batch = payload or []
            if not batch:
                break
            seen.update(d.get(field) for d in batch if isinstance(d, dict))
            if len(batch) < page:
                break
            offset += page
        return seen


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def main():
    ap = argparse.ArgumentParser(description="search_outbox 存量回补 Meilisearch")
    ap.add_argument("--pg-container", default=os.environ.get("PG_CONTAINER", "pg2meili-postgres-1"))
    ap.add_argument("--pg-user", default=os.environ.get("POSTGRES_USER", "postgres"))
    ap.add_argument("--pg-db", default=os.environ.get("POSTGRES_DB", "postgres"))
    ap.add_argument("--jsonl", default=None, help="预导出的 JSONL 文件，跳过 psql")
    ap.add_argument("--meili-url", default=os.environ.get("MEILI_URL", "http://localhost:7700"))
    ap.add_argument("--meili-key", default=os.environ.get("MEILI_MASTER_KEY", ""))
    ap.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    ap.add_argument("--groups", default=None, help="逗号分隔的 collection 白名单")
    ap.add_argument("--skip-existing", action="store_true",
                    help="跳过索引中已有的文档（_meili_id 去重），适合断点续传")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划，不写入")
    args = ap.parse_args()

    if not args.meili_key:
        ap.error("缺少 Meilisearch key：--meili-key 或环境变量 MEILI_MASTER_KEY")

    groups = set(g.strip() for g in (args.groups or "").split(",") if g.strip()) or None
    rows = load_from_psql(args.pg_container, args.pg_user, args.pg_db) if not args.jsonl \
        else load_from_jsonl(args.jsonl)
    print("共读取 {} 条最新文档状态".format(len(rows)))

    by_group = {}
    for row in rows:
        key = (row.get("app_id"), row.get("collection"))
        if groups and row.get("collection") not in groups:
            continue
        by_group.setdefault(key, []).append(row)

    meili = Meili(args.meili_url, args.meili_key)
    summary = []
    for (app_id, collection), group in sorted(by_group.items()):
        uid = index_uid(app_id, collection)
        upserts = [r for r in group if r.get("operation") == "upsert"]
        deletes = [r for r in group if r.get("operation") == "delete"]
        docs = []
        skipped_bad = 0
        for r in upserts:
            doc = to_meili_doc(r)
            if doc is None:
                skipped_bad += 1
                continue
            docs.append(doc)
        print("\n[{}] collection={} 待写 docs={} 待删={} (坏文档跳过={})".format(
            uid, collection, len(docs), len(deletes), skipped_bad))

        if args.dry_run:
            summary.append((uid, len(docs), len(deletes), "dry-run"))
            continue

        pk, exists = meili.index_pk(uid)
        if exists and pk not in (None, "_meili_id"):
            print("  !! 跳过：索引已存在且主键为 '{}'，与 _meili_id 冲突（旧链路建立的索引）".format(pk))
            summary.append((uid, 0, 0, "skipped: pk={}".format(pk)))
            continue

        if args.skip_existing and exists:
            existing = set(meili.existing_ids(uid))
            before = len(docs)
            docs = [d for d in docs if d["_meili_id"] not in existing]
            skipped = before - len(docs)
            if skipped:
                print("  .. 跳过已有 {} 条（共 {} 条）".format(skipped, before))

        added = 0
        for batch in chunked(docs, args.batch_size):
            task = meili.add_docs(uid, batch)
            if task.get("status") != "succeeded":
                print("  !! 批次失败 status={} error={}".format(
                    task.get("status"), task.get("error") or {}))
                summary.append((uid, added, 0, "partial-fail"))
                added = -1
                break
            added += len(batch)
            print("  .. {}/{} 已写入".format(added, len(docs)))

        removed = 0
        del_ids = [meili_document_id(r["document_id"]) for r in deletes]
        for batch in chunked(del_ids, 1000):
            if not batch:
                continue
            task = meili.delete_docs(uid, batch)
            if task.get("status") != "succeeded":
                print("  !! 删除批次失败 {}".format(task.get("error") or {}))
            else:
                removed += len(batch)
        summary.append((uid, added, removed, "ok"))

    print("\n==== 汇总 ====")
    for uid, added, removed, note in summary:
        print("{:<48} added={:<6} deleted={:<4} {}".format(uid, added, removed, note))


if __name__ == "__main__":
    main()
