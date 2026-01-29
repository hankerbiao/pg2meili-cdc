import os
import json
from typing import Any, Dict, List

import requests


BASE_URL = os.getenv("SEARCH_BASE_URL", "http://localhost:8091")
TOKEN_FILE = os.getenv("SEARCH_TOKEN_FILE", os.path.join(os.path.dirname(__file__), "token.txt"))


def load_token() -> str:
    token = os.getenv("SEARCH_JWT")
    if token:
        return token.strip()
    with open(TOKEN_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def call_search(payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{BASE_URL}/search"
    token = load_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=30)
    resp.raise_for_status()
    return resp.json()


def print_example_result(label: str, result: Dict[str, Any]) -> None:
    hits: List[Dict[str, Any]] = result.get("hits", [])
    print("=" * 80)
    print(label)
    print("hits:", len(hits))
    if not hits:
        return
    doc = hits[0]
    print("id:", doc.get("id"))
    print("ext_id:", doc.get("ext_id"))
    print("name:", doc.get("name"))
    print("summary:", doc.get("summary"))
    print("tags:", doc.get("tags"))
    if "_formatted" in doc:
        print("_formatted.name:", doc["_formatted"].get("name"))
        print("_formatted.summary:", doc["_formatted"].get("summary"))


def search_simple() -> None:
    payload = {
        "q": "电源",
    }
    result = call_search(payload)
    print_example_result("simple search: q=电源", result)


def search_with_highlight() -> None:
    payload = {
        "q": "电源",
        "attributesToHighlight": ["*"],
    }
    result = call_search(payload)
    print_example_result("search with highlight: q=电源, attributesToHighlight=*", result)


def search_filter_by_tag() -> None:
    payload = {
        "q": "电源",
        "filter": ['tags = "BMC"'],
    }
    result = call_search(payload)
    print_example_result('search filter by tag: q=电源, filter=tags = "BMC issue"', result)


def search_with_pagination(page: int = 1, page_size: int = 10) -> None:
    offset = (page - 1) * page_size
    payload = {
        "q": "电源",
        "offset": offset,
        "limit": page_size,
    }
    result = call_search(payload)
    print_example_result(f"search with pagination: page={page}, page_size={page_size}", result)


def main() -> None:
    search_simple()
    search_with_highlight()
    search_filter_by_tag()
    search_with_pagination(page=1, page_size=5)


if __name__ == "__main__":
    main()
