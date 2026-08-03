# UniData Python SDK

`unidata-sdk` provides synchronous and asynchronous Python clients for the
UniData document API and its distributed search Agents.

## Installation

```bash
pip install unidata-sdk
```

To install the package from this repository:

```bash
pip install ./python-sdk
```

Python 3.10 or newer is required.

## Synchronous client

```python
import os

from unidata_sdk import UniDataClient


with UniDataClient(
    "https://unidata.example.com",
    os.environ["UNIDATA_API_KEY"],
    region="shanghai",
) as client:
    client.upsert_document(
        "articles",
        {
            "id": "article-1",
            "title": "Power management",
            "status": "published",
        },
    )

    result = client.search(
        "articles",
        query="power",
        limit=20,
        filter='status = "published"',
        attributes_to_highlight=["title"],
    )

    for hit in result.hits:
        print(hit["id"], hit.get("_formatted", {}).get("title"))
    print(result.meta.request_id, result.meta.region)
```

When `search_url` is omitted, the SDK reads online Agents from
`GET /api/v1/agents/online`, strictly filters them by `region`, and selects a
node using its configured weight. The list is cached for 30 seconds by default.
Retryable search failures are sent to a different Agent when one is available.

For a fixed search endpoint, pass it explicitly:

```python
client = UniDataClient(
    "https://unidata.example.com",
    api_key,
    search_url="https://search-shanghai.example.com",
)
```

## Asynchronous client

`AsyncUniDataClient` has the same business methods as `UniDataClient`:

```python
from unidata_sdk import AsyncUniDataClient


async with AsyncUniDataClient(
    "https://unidata.example.com",
    api_key,
    region="shanghai",
) as client:
    await client.upsert_documents(
        "articles",
        [
            {"id": "article-1", "title": "First"},
            {"id": "article-2", "title": "Second"},
        ],
    )
    result = await client.search("articles", query="first")
```

## API overview

Both clients expose:

- `health()`
- `upsert_document()` and `upsert_documents()`
- `get_document()`, `list_documents()`, and `delete_document()`
- `list_indexes()`, `delete_index()`, and `update_index_settings()`
- `list_agents()`
- `search()`
- `request()` for control-plane endpoints not yet covered by a dedicated method

Search uses the stable endpoint
`POST /api/v1/collections/{collection}/search`. Common Meilisearch parameters
have Python-style names. Less common parameters can be passed without waiting
for an SDK release:

```python
result = client.search(
    "articles",
    query="power",
    raw_parameters={
        "matchingStrategy": "all",
        "facets": ["status"],
    },
)
```

Explicit keyword arguments take precedence over `raw_parameters` when both
specify the same field. Documents and search hits remain dictionaries so
application-specific fields are preserved.

## Generic requests

Use `request()` when a new UniData control-plane endpoint is available before
the SDK adds a dedicated method. It uses the same Bearer authentication,
timeouts, retries, error mapping, and response-envelope parsing as the built-in
methods, and returns the response's `data` value:

```python
data = client.request(
    "POST",
    "/api/v1/data/articles",
    params={"source": "import"},
    json={"id": "article-3", "title": "Generic request"},
    headers={"X-Request-ID": "import-2026-07-30"},
)
```

Paths must begin with exactly one `/` and cannot be absolute URLs. The SDK
owns the `Authorization` and `User-Agent` headers, so callers cannot override
them. Use `await client.request(...)` with `AsyncUniDataClient`.

Collection names must match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`. Documents sent
through upsert methods must contain a non-empty string `id`.

## Errors and retries

All SDK exceptions inherit from `UniDataError`:

```python
from unidata_sdk import RateLimitError, UniDataError


try:
    result = client.search("articles", query="power")
except RateLimitError as error:
    print(error.retry_after, error.request_id)
except UniDataError as error:
    print(error)
```

API exceptions preserve `status_code`, `code`, `retryable`, `request_id`, and
`retry_after` when the service supplies them. The SDK never includes the Bearer
API key in its own exception messages.

By default, retryable operations receive two retries, for at most three total
attempts. Retries use exponential backoff with jitter and honor `Retry-After`.
Search retries are limited to transport errors, HTTP 429/502/503/504, or errors
explicitly marked as retryable. Validation, authentication, permission, and
not-found responses are not retried. Configure the behavior with
`max_retries` and `agent_cache_ttl`.

## Required scopes

| Operation | Scope |
|---|---|
| Read documents and list indexes | `data:read` |
| Upsert/delete documents and manage indexes | `data:write` |
| Discover Agents and search | `search:read` |

Application and API key administration, and Agent registration, are operational
workflows and are intentionally outside the SDK.

## Custom HTTP clients

An existing `httpx.Client` or `httpx.AsyncClient` can be supplied through
`http_client` to configure proxies, certificates, or custom transports. The
SDK does not close an injected client. Clients created by the SDK are closed by
`close()`, `aclose()`, or their context manager.
