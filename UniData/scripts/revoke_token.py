"""撤销指定 token 的脚本（按 jti）。

用法示例：
  1) 传完整串，只撤销 search：
     python scripts/revoke_token.py --jti "search:21a4c4fb...;data:cb58fbb0..." --target search
  2) 传完整串，只撤销 data：
     python scripts/revoke_token.py --jti "search:21a4c4fb...;data:cb58fbb0..." --target data
  3) 传完整串，撤销两条（默认）：
     python scripts/revoke_token.py --jti "search:21a4c4fb...;data:cb58fbb0..."
  4) 传单个 jti：
     python scripts/revoke_token.py --jti 21a4c4fb-ba18-4797-b38c-5bdbbf265029
"""
import argparse
import os
import sys

import requests

from dotenv import load_dotenv
load_dotenv()

# 确保可以从项目根目录导入 app 包
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Revoke a token by jti via UniData API",
        epilog="""
示例:
  python scripts/revoke_token.py --base-url http://localhost:8080 \\
    --admin-token <JWT> --jti <JTI> --reason "安全撤销"
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=os.getenv("UNIDATA_URL", "http://localhost:8080"),
        help="UniData 服务地址，默认读取 UNIDATA_URL 或 http://localhost:8080",
    )
    parser.add_argument(
        "--admin-token",
        default=os.getenv("UNIDATA_ADMIN_TOKEN", ""),
        help="具有撤销权限的 JWT，默认读取 UNIDATA_ADMIN_TOKEN",
    )
    parser.add_argument(
        "--jti",
        required=True,
        help="需要撤销的 jti，支持单个 jti 或完整串（如 search:xxx;data:yyy）",
    )
    parser.add_argument(
        "--target",
        choices=["search", "data", "all"],
        default="all",
        help="当 jti 为 search:xxx;data:yyy 时，选择撤销哪一个",
    )
    parser.add_argument("--reason", default="", help="撤销原因（可选）")

    args = parser.parse_args()

    if not args.admin_token:
        print("缺少 --admin-token 或 UNIDATA_ADMIN_TOKEN")
        raise SystemExit(1)

    base = args.base_url.rstrip("/")
    url = f"{base}/api/v1/auth/tokens/revoke"
    def extract_jtis(raw: str) -> dict[str, str]:
        parts = {}
        for item in raw.split(";"):
            item = item.strip()
            if not item:
                continue
            if ":" in item:
                key, value = item.split(":", 1)
                parts[key.strip()] = value.strip()
        return parts

    raw_jti = args.jti.strip()
    jt_map = extract_jtis(raw_jti)
    if jt_map:
        targets = ["search", "data"] if args.target == "all" else [args.target]
        jt_list = []
        for t in targets:
            if t not in jt_map:
                print(f"jti 串中未找到 {t}")
                raise SystemExit(1)
            jt_list.append(jt_map[t])
    else:
        jt_list = [raw_jti]

    for jti in jt_list:
        payload = {"jti": jti}
        if args.reason:
            payload["reason"] = args.reason

        resp = requests.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {args.admin_token}"},
            timeout=10,
        )
        try:
            data = resp.json()
        except ValueError:
            print(f"HTTP {resp.status_code}: {resp.text}")
            raise SystemExit(1)

        if resp.status_code >= 400:
            print(f"HTTP {resp.status_code}: {data}")
            raise SystemExit(1)

        print(data)


if __name__ == "__main__":
    main()
