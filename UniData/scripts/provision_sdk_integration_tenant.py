"""Create an isolated short-lived tenant for SDK local-stack tests."""
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import timedelta

from app.core.database import get_db_context
from app.services.open_platform_service import open_platform_service, utc_now


KEY_SCOPES = (
    ("full", ["data:read", "data:write", "search:read"]),
    ("data", ["data:read", "data:write"]),
    ("search", ["search:read"]),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("app_name")
    return parser.parse_args()


async def provision(app_name: str) -> dict[str, object]:
    async with get_db_context() as db:
        app = await open_platform_service.create_app(
            db,
            app_name=app_name,
            display_name="SDK local integration",
            owner_itcode="sdk-integration",
            description="temporary pytest tenant",
            actor="integration-test",
            source_ip=None,
        )
        expires_at = utc_now() + timedelta(days=1)
        keys: dict[str, str] = {}
        for name, scopes in KEY_SCOPES:
            _, keys[name] = await open_platform_service.create_key(
                db,
                app_id=app.id,
                name=f"sdk-it-{name}",
                scopes=scopes,
                expires_at=expires_at,
                actor="integration-test",
                source_ip=None,
            )

    return {"app_id": app.id, "app_name": app.app_name, "keys": keys}


def main() -> None:
    print(json.dumps(asyncio.run(provision(parse_args().app_name))))


if __name__ == "__main__":
    main()
