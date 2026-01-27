"""应用身份校验模块。"""
import json
from dataclasses import dataclass
from typing import Dict

from fastapi import Header, HTTPException, status

from app.core.config import get_settings


@dataclass
class AppIdentity:
    app_name: str


def _load_app_tokens() -> Dict[str, str]:
    settings = get_settings()
    raw = getattr(settings, "app_tokens_json", "") or ""
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    tokens: Dict[str, str] = {}
    for key, value in data.items():
        tokens[str(key)] = str(value)
    return tokens


APP_TOKENS = _load_app_tokens()


async def get_current_app(
    x_app_name: str = Header(default="", alias="X-App-Name"),
    x_app_token: str = Header(default="", alias="X-App-Token"),
) -> AppIdentity:
    if not x_app_name or not x_app_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="缺少应用身份信息",
        )

    expected_token = APP_TOKENS.get(x_app_name)
    if not expected_token or expected_token != x_app_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="应用身份校验失败",
        )

    return AppIdentity(app_name=x_app_name)

