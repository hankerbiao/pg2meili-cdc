"""简单的 JWT 生成脚本，和 app.core.auth 使用相同的 HS256 签名方式。"""
import argparse
import os
import sys
from typing import List

# 确保可以从项目根目录导入 app 包
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from app.core.auth import generate_jwt


# 常用 TTL 值常量（秒）
TTL_SHORT = 3600           # 1 小时
TTL_DAY = 86400            # 1 天
TTL_WEEK = 604800          # 1 周
TTL_MONTH = 2592000        # 30 天
TTL_YEAR = 31536000        # 1 年
TTL_LONGTERM = 315360000   # 10 年（长期有效）


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate JWT for UniData apps",
        epilog="""
常见 TTL 示例:
  --ttl 3600       1 小时（默认）
  --ttl 86400      1 天
  --ttl 604800     1 周
  --ttl 2592000    30 天
  --ttl 31536000   1 年
  --ttl 315360000  10 年（长期）

示例:
  python scripts/generate_jwt.py --app-name myapp --scopes read,write --ttl 86400
  python scripts/generate_jwt.py --app-name myapp --ttl 315360000  # 10 年有效
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--app-name", required=True, help="应用名称，对应 JWT 中的 app_name")
    parser.add_argument(
        "--scopes",
        default="",
        help="以逗号分隔的权限列表，例如: testcases:write,indexes:read",
    )
    parser.add_argument(
        "--ttl",
        type=int,
        default=TTL_LONGTERM,
        help=f"令牌有效期（秒），默认 {TTL_LONGTERM}（10年）",
    )

    args = parser.parse_args()

    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]

    token = generate_jwt(args.app_name, scopes, args.ttl)
    print(token)


if __name__ == "__main__":
    main()
