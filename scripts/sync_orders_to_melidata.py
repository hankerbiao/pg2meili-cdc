#!/usr/bin/env python3
"""MES 订单数据 -> MeliData(Meilisearch) 全流程同步脚本。

链路:
    orders API  --(拉取全量分页)-->  本脚本  --(批量 upsert)-->
    MeliData /api/v1/data/{collection}/batch  --(Postgres -> Debezium CDC)-->
    区域 Agent 索引  --(区域搜索接口)-->  命中验证

依赖: 仅标准库（urllib），无需 pip install。

常用用法:
    export MELIDATA_API_KEY="ud_live_ak_xxx.yyy"
    python3 scripts/sync_orders_to_melidata.py                     # 全量同步 + 校验
    python3 scripts/sync_orders_to_melidata.py --limit 200         # 只同步前 200 条试跑
    python3 scripts/sync_orders_to_melidata.py --only-verify       # 跳过写入，只做校验
    python3 scripts/sync_orders_to_melidata.py --dry-run           # 只打印计划不写

安全: API Key 只从环境变量 / --api-key / --env-file 读取，不落仓库。

运维要点（2026-11-11 实测，10.17.158.114）:
    * 写入侧（MeliData API）很快，21457 条 22 批约 1 分钟。
    * 真正决定全量耗时的是 CDC 落索引速率，瓶颈在 Meilisearch 每批任务的
      LMDB 提交（该机为机械盘，fsync 约 69ms）。MEILI_BATCH_SIZE=100 时约
      10 docs/s，调成 1000 后约 50-60 docs/s，故同步大批量前建议：
          echo 'MEILI_BATCH_SIZE=1000' >> .env.docker
          docker compose up -d --no-deps meilisearch-sync
    * 索引全部可见用 `POST /documents/api/v1/collections/{c}/search` 采样验证；
      该接口 maxTotalHits 固定 1000，空查询的 estimatedTotalHits 到 1000 即封顶，
      不能当总量用 —— 总量请取 `GET /indexes/{uid}/stats`（需 master key）。
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

DEFAULT_SOURCE_URL = "http://10.17.150.235:5174/api/orders"
DEFAULT_BASE_URL = "https://meilisearch.1oa.com.cn"
DEFAULT_COLLECTION = "mes_orders"

MAX_BATCH_ITEMS = 1000          # 服务端硬限制
MAX_BATCH_BYTES = 5 * 1024 * 1024  # 5 MiB
SOURCE_PAGE_SIZE_MAX = 100      # 源接口 >100 会回退到 20

SEARCHABLE_ATTRIBUTES = [
    "finalUser", "materialDescription", "productionModel",
    "salesOrder", "aufnr", "customerId", "sourceKey", "id",
]
FILTERABLE_ATTRIBUTES = [
    "source", "customerId", "productionModel", "inventoryLocation",
    "plannedStartDate", "aufnr", "salesOrder", "id",
]
SORTABLE_ATTRIBUTES = ["plannedStartDate", "orderQuantity", "storageQuantity"]


# --------------------------------------------------------------------------- #
# HTTP 基础设施
# --------------------------------------------------------------------------- #
def http_json(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: Any | None = None,
    timeout: float = 30.0,
    retries: int = 5,
    retry_on: tuple[int, ...] = (408, 425, 429, 500, 502, 503, 504),
) -> tuple[int, Any]:
    """发起请求，对限流/临时故障做有限次指数退避重试。返回 (status, json)。"""
    data = None
    hdrs = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)

    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if raw else None)
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                parsed = json.loads(payload) if payload else None
            except json.JSONDecodeError:
                parsed = payload.decode("utf-8", "replace")
            if e.code in retry_on and attempt < retries:
                time.sleep(min(2 ** attempt, 20) + random.random())
                last_err = e
                continue
            return e.code, parsed
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            if attempt < retries:
                time.sleep(min(2 ** attempt, 20) + random.random())
                continue
            raise

    raise RuntimeError(f"request failed after {retries} attempts: {url}: {last_err}")


class MeliData:
    def __init__(self, base_url: str, api_key: str, collection: str) -> None:
        self.base = base_url.rstrip("/")
        self.key = api_key
        self.collection = collection

    def _h(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.key}"}

    # --- 管理面 ---
    def agents_online(self) -> list[dict]:
        st, body = http_json("GET", f"{self.base}/api/v1/agents/online", headers=self._h())
        if st != 200:
            raise RuntimeError(f"agents/online 失败 HTTP {st}: {body}")
        return (body or {}).get("data") or []

    def apply_settings(self) -> dict:
        payload = {
            "searchableAttributes": SEARCHABLE_ATTRIBUTES,
            "filterableAttributes": FILTERABLE_ATTRIBUTES,
            "sortableAttributes": SORTABLE_ATTRIBUTES,
        }
        st, body = http_json(
            "POST",
            f"{self.base}/api/v1/indexes/{urllib.parse.quote(self.collection)}/settings",
            headers=self._h(),
            body=payload,
        )
        return {"status": st, "body": body}

    # --- 数据面 ---
    def upsert_batch(self, items: list[dict]) -> dict:
        st, body = http_json(
            "POST",
            f"{self.base}/api/v1/data/{urllib.parse.quote(self.collection)}/batch",
            headers=self._h(),
            body={"items": items},
            timeout=60,
        )
        if st not in (200, 201):
            raise RuntimeError(f"批量写入失败 HTTP {st}: {str(body)[:500]}")
        return body.get("data") or {}

    def get_doc(self, doc_id: str) -> dict | None:
        st, body = http_json(
            "GET",
            f"{self.base}/api/v1/data/{urllib.parse.quote(self.collection)}/{urllib.parse.quote(doc_id)}",
            headers=self._h(),
        )
        return (body or {}).get("data") if st == 200 else None

    def list_docs(self, limit: int = 100, offset: int = 0) -> list[dict]:
        st, body = http_json(
            "GET",
            f"{self.base}/api/v1/data/{urllib.parse.quote(self.collection)}"
            f"?limit={limit}&offset={offset}",
            headers=self._h(),
        )
        if st != 200:
            raise RuntimeError(f"读取文档失败 HTTP {st}: {str(body)[:300]}")
        return (body or {}).get("data") or []

    def region_search(self, payload: dict) -> dict:
        st, body = http_json(
            "POST",
            f"{self.base}/documents/api/v1/collections/"
            f"{urllib.parse.quote(self.collection)}/search",
            headers=self._h(),
            body=payload,
        )
        if st != 200:
            raise RuntimeError(f"区域搜索失败 HTTP {st}: {str(body)[:300]}")
        return body


# --------------------------------------------------------------------------- #
# 源数据抓取与转换
# --------------------------------------------------------------------------- #
def fetch_page(source_url: str, page: int, page_size: int) -> dict:
    sep = "&" if "?" in source_url else "?"
    url = f"{source_url}{sep}page={page}&pageSize={page_size}"
    st, body = http_json("GET", url, timeout=60)
    if st != 200 or not isinstance(body, dict):
        raise RuntimeError(f"源接口失败 HTTP {st}: {str(body)[:300]}")
    return body


def fetch_all_orders(source_url: str, page_size: int, workers: int, limit: int | None) -> tuple[list[dict], int]:
    first = fetch_page(source_url, 1, page_size)
    total = int(first.get("total") or 0)
    items = list(first.get("items") or [])
    got = len(items)
    print(f"[fetch] total={total} 首批 {got} 条 (pageSize={first.get('pageSize')})")

    effective_ps = int(first.get("pageSize") or page_size)
    pages = (total + effective_ps - 1) // effective_ps
    if limit:
        pages = min(pages, (limit + effective_ps - 1) // effective_ps)

    if pages > 1:
        def _one(p: int) -> dict:
            return fetch_page(source_url, p, effective_ps)

        done = 1
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_one, p): p for p in range(2, pages + 1)}
            for fut in concurrent.futures.as_completed(futures):
                page_items = fut.result().get("items") or []
                items.extend(page_items)
                got += len(page_items)
                done += 1
                if done % 20 == 0 or done == pages:
                    print(f"[fetch] {done}/{pages} 页, 累计 {got} 条", flush=True)

    if limit:
        items = items[:limit]
    return items, total


def sanitize_doc_id(source_key: str) -> str:
    """Meilisearch 文档 id 只允许 [A-Za-z0-9_-]，'SG:10350750' -> 'SG-10350750'。"""
    out = []
    for ch in source_key:
        out.append(ch if (ch.isalnum() or ch in "-_") else "-")
    return "".join(out)


def transform(item: dict, synced_at: str) -> dict:
    raw = item.get("raw") or {}
    sap = raw.get("data") if isinstance(raw, dict) else None
    source_key = str(item.get("id") or "")
    doc: dict[str, Any] = {
        "id": sanitize_doc_id(source_key),
        "sourceKey": source_key,
        "source": item.get("source"),
        "aufnr": item.get("aufnr"),
        "salesOrder": item.get("salesOrder"),
        "customerId": item.get("customerId"),
        "finalUser": item.get("finalUser"),
        "materialDescription": item.get("materialDescription"),
        "productionModel": item.get("productionModel"),
        "inventoryLocation": item.get("inventoryLocation"),
        "plannedStartDate": item.get("plannedStartDate"),
        "orderQuantity": item.get("orderQuantity"),
        "storageQuantity": item.get("storageQuantity"),
        "recordCount": item.get("recordCount"),
        "syncedAt": synced_at,
    }
    if isinstance(sap, dict):
        doc["sap"] = sap
        if isinstance(raw.get("records"), list):
            doc["sapRecords"] = raw["records"]
    # 去掉 None，避免污染索引与体积
    return {k: v for k, v in doc.items() if v is not None}


def build_batches(docs: list[dict]) -> list[list[dict]]:
    """按条数与 5MiB 双约束切批，并保证批内 id 唯一。"""
    batches: list[list[dict]] = []
    cur: list[dict] = []
    cur_ids: set[str] = set()
    cur_bytes = 12  # {"items":[]} 骨架

    for d in docs:
        size = len(json.dumps(d, ensure_ascii=False).encode("utf-8")) + 1
        need_new = (
            len(cur) >= MAX_BATCH_ITEMS
            or (cur and cur_bytes + size > MAX_BATCH_BYTES)
            or d["id"] in cur_ids
        )
        if need_new:
            batches.append(cur)
            cur, cur_ids, cur_bytes = [], set(), 12
        cur.append(d)
        cur_ids.add(d["id"])
        cur_bytes += size
    if cur:
        batches.append(cur)
    return batches


# --------------------------------------------------------------------------- #
# 校验：中心库 + 区域索引 + CDC 状态
# --------------------------------------------------------------------------- #
def verify_center_sample(meli: MeliData, sample_ids: list[str], workers: int = 8) -> dict:
    """抽样按 id 读中心库（列表接口 offset 分页不稳定，不做全量翻页）。"""
    def _one(did: str) -> bool:
        try:
            return meli.get_doc(did) is not None
        except Exception:  # noqa: BLE001
            return False

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        res = list(pool.map(_one, sample_ids))
    found = [s for s, ok in zip(sample_ids, res) if ok]
    missing = [s for s, ok in zip(sample_ids, res) if not ok]
    return {"sample": len(sample_ids), "found": len(found), "missing": missing[:10]}


def verify_region(meli: MeliData, sample_ids: list[str], timeout: int) -> dict:
    """轮询区域索引，直到抽样文档全部可被 filter 命中或超时。"""
    deadline = time.time() + timeout
    attempt = 0
    t0 = time.time()
    last: dict = {}
    while True:
        attempt += 1
        hits_cap = meli.region_search({"q": "", "limit": 1})["data"].get("estimatedTotalHits")
        found, missing = [], []
        for did in sample_ids:
            res = meli.region_search({"q": "", "limit": 1, "filter": f'id = "{did}"'})["data"]
            (found if res.get("hits") else missing).append(did)
        last = {
            "estimatedTotalHits_capped": hits_cap,
            "sample_found": len(found),
            "sample_total": len(sample_ids),
            "missing_ids": missing[:10],
            "attempts": attempt,
            "waited_s": round(time.time() - t0, 1),
        }
        print(
            f"[verify-region] 轮询 #{attempt}: 抽样命中 {len(found)}/{len(sample_ids)}, "
            f"索引计数={hits_cap}(≤1000 为引擎 maxTotalHits 上限), 已等 {last['waited_s']}s",
            flush=True,
        )
        if not missing:
            return last
        if time.time() >= deadline:
            print(f"[verify-region] 超时 {timeout}s，仍有 {len(missing)} 条未出现在区域索引（CDC 滞后/丢事件）")
            return last
        time.sleep(5)


def cdc_health(meli: MeliData) -> dict:
    agents = meli.agents_online()
    summary = []
    for a in agents:
        summary.append({
            "id": a.get("id"),
            "region": a.get("region"),
            "status": a.get("status"),
            "last_seen_at": a.get("last_seen_at"),
            "base_url": a.get("base_url"),
        })
    ready = [a for a in summary if a["status"] == "ready"]
    return {"agents": summary, "ready_count": len(ready), "total": len(summary)}


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def load_env_file(path: str) -> None:
    if not os.path.exists(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def main() -> int:
    # 先解析 --env-file 并加载，保证后续 argparse 的 env 默认值有效
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--env-file", default=os.getenv(
        "MELIDATA_ENV_FILE",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.melidata-sync"),
    ))
    pre_args, _ = pre.parse_known_args()
    load_env_file(pre_args.env_file)

    ap = argparse.ArgumentParser(description="MES 订单 -> MeliData 全量同步与校验")
    ap.add_argument("--source-url", default=os.getenv("ORDERS_API_URL", DEFAULT_SOURCE_URL))
    ap.add_argument("--base-url", default=os.getenv("MELIDATA_API_BASE", DEFAULT_BASE_URL))
    ap.add_argument("--collection", default=os.getenv("MELIDATA_COLLECTION", DEFAULT_COLLECTION))
    ap.add_argument("--api-key", default=os.getenv("MELIDATA_API_KEY"))
    ap.add_argument(
        "--env-file",
        default=pre_args.env_file,
        help="本地凭据文件（默认 scripts/.env.melidata-sync，已在 .gitignore 内）",
    )
    ap.add_argument("--page-size", type=int, default=100)
    ap.add_argument("--fetch-workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=None, help="只同步前 N 条（试跑）")
    ap.add_argument("--verify-timeout", type=int, default=900, help="等待区域索引追平的秒数")
    ap.add_argument("--verify-sample", type=int, default=40)
    ap.add_argument("--skip-settings", action="store_true")
    ap.add_argument("--only-verify", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.api_key:
        args.api_key = os.getenv("MELIDATA_API_KEY")
    if not args.api_key:
        print("缺少 API Key：请 export MELIDATA_API_KEY=... 或传 --api-key/--env-file", file=sys.stderr)
        return 2

    started = time.time()
    meli = MeliData(args.base_url, args.api_key, args.collection)
    report: dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "source_url": args.source_url,
        "collection": args.collection,
        "base_url": args.base_url,
    }

    # 0. CDC/Agent 健康快照
    try:
        report["cdc_before"] = cdc_health(meli)
        print(f"[cdc] 在线 Agent: {report['cdc_before']['ready_count']}/{report['cdc_before']['total']}")
    except Exception as e:  # noqa: BLE001
        print(f"[cdc] agents/online 探测失败: {e}")
        report["cdc_before"] = {"error": str(e)}

    # 1. 索引设置（过滤/排序/检索字段）
    if not args.only_verify and not args.skip_settings:
        res = meli.apply_settings()
        report["settings"] = res
        print(f"[settings] HTTP {res['status']} -> {res['body']}")

    # 2. 全量拉取（--only-verify 也拉，只用于生成抽样池）
    docs_raw, source_total = fetch_all_orders(
        args.source_url, args.page_size, args.fetch_workers, args.limit
    )
    synced_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    docs = [transform(it, synced_at) for it in docs_raw]
    before = len(docs)
    seen_ids: set[str] = set()
    uniq = []
    for d in docs:
        if d["id"] in seen_ids:
            continue
        seen_ids.add(d["id"])
        uniq.append(d)
    if len(uniq) != before:
        print(f"[transform] id 去重: {before} -> {len(uniq)}")
    docs = uniq
    all_ids = [d["id"] for d in docs]
    report["fetched"] = len(docs)
    report["source_total"] = source_total
    print(f"[transform] 待写入 {len(docs)} 条")

    # 3. 批量写入
    batches = build_batches(docs) if (docs and not args.only_verify) else []
    if args.only_verify:
        print("[write] --only-verify：跳过写入")
    elif docs and args.dry_run:
        print(f"[dry-run] {len(batches)} 个批次，跳过写入")
    elif batches:
        written = 0
        t0 = time.time()
        for i, batch in enumerate(batches, 1):
            data = meli.upsert_batch(batch)
            written += int(data.get("count") or len(batch))
            if i % 5 == 0 or i == len(batches):
                el = time.time() - t0
                print(
                    f"[write] {i}/{len(batches)} 批, {written}/{len(docs)} docs, "
                    f"{el:.1f}s ({written / el:.0f} docs/s)",
                    flush=True,
                )
        report["written"] = written
        report["batch_count"] = len(batches)
        print(f"[write] 完成：{written} 条写入 {args.collection}")

    # 4. 校验：中心库抽样 + 区域索引抽样 + 关键字检索 + CDC 健康
    if not args.dry_run:
        # 分层抽样：均匀覆盖全量（含首尾，能暴露尾部滞后）
        step = max(len(all_ids) // args.verify_sample, 1)
        sample = all_ids[::step][: args.verify_sample]
        report["sample_size"] = len(sample)

        try:
            center = verify_center_sample(meli, sample)
            report["center"] = {"sample": center["sample"], "found": center["found"],
                                "missing": center["missing"]}
            print(f"[verify-center] 抽样 {center['sample']} 条，中心库命中 {center['found']}")
        except Exception as e:  # noqa: BLE001
            print(f"[verify-center] 失败: {e}")
            report["center_error"] = str(e)

        if sample:
            try:
                report["region"] = verify_region(meli, sample, args.verify_timeout)
            except Exception as e:  # noqa: BLE001
                print(f"[verify-region] 失败: {e}")
                report["region_error"] = str(e)

        try:
            kw = meli.region_search({"q": "腾讯", "limit": 3})["data"]
            report["keyword_check"] = {
                "q": "腾讯",
                "estimatedTotalHits_capped": kw.get("estimatedTotalHits"),
                "first_hit": (kw.get("hits") or [{}])[0].get("finalUser") if kw.get("hits") else None,
            }
            print(f"[verify-search] q=腾讯 命中 {kw.get('estimatedTotalHits')} 条（≤1000 为上限）")
        except Exception as e:  # noqa: BLE001
            print(f"[verify-search] 失败: {e}")

        try:
            report["cdc_after"] = cdc_health(meli)
        except Exception as e:  # noqa: BLE001
            report["cdc_after"] = {"error": str(e)}

    report["elapsed_s"] = round(time.time() - started, 1)
    print("\n===== 同步报告 =====")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
