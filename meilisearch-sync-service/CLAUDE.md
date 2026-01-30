# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A real-time data synchronization service that consumes Debezium CDC messages from Kafka and syncs them to Meilisearch. Implements a "single-source writing + multi-region searching" architecture for distributed search deployment.

## Build Commands

```bash
# Development
go run main.go

# Production build (static binary)
CGO_ENABLED=0 go build -a -ldflags "-s -w" -o meilisearch-sync-service main.go

# Install dependencies
go mod tidy

# Run tests
go test ./...
```

## Architecture

```
PostgreSQL → Debezium CDC → Kafka → meilisearch-sync-service → Meilisearch
```

### Core Components

| File | Purpose |
|------|---------|
| `main.go` | Entry point; initializes Kafka client, Meilisearch client, HTTP server |
| `internal/service/sync.go` | Kafka consumer loop; processes Debezium messages |
| `internal/handler/handler.go` | HTTP `/search` endpoint with JWT authentication |
| `internal/auth/auth.go` | HS256 JWT validation; extracts `app_name` and `scopes` |
| `internal/config/config.go` | Environment variable loading |

### Data Flow

1. Kafka consumer polls for Debezium CDC messages (`internal/service/sync.go:25`)
2. Message parsed to extract operation type (`c`, `u`, `d`, `r`) and document data
3. Document synced to Meilisearch based on topic-to-index mapping
4. HTTP `/search` endpoint proxies search requests with JWT-based index access control

### Supported Operations

- `c` (create) - `AddDocuments` (upsert)
- `u` (update) - `AddDocuments` (upsert)
- `r` (snapshot) - `AddDocuments` (upsert)
- `d` (delete) - `DeleteDocument`
- Soft delete via `is_delete` field in document

### Index Naming

- Index name is derived from the document's `app_name` and `collection` fields:

```text
{app_name}_{collection}
```

- This ensures per-app, per-collection isolation on the Meilisearch side.

## Key Configuration (Environment Variables)

| Variable | Description | Default |
|----------|-------------|---------|
| `KAFKA_BROKERS` | Kafka cluster addresses | `10.17.154.252:9092` |
| `KAFKA_TOPIC` | Topics to subscribe | `test_case.public.test_cases` |
| `KAFKA_GROUP_ID` | Consumer group ID | `meilisearch-sync-service` |
| `MEILI_HOST` | Meilisearch URL | `http://10.17.154.252:7700` |
| `MEILI_API_KEY` | Meilisearch API key | (empty) |
| `MEILI_INDEX` | Default index name (deprecated) | `testcases` |
| `JWT_SECRET` | JWT signing secret | `please-change-me-in-prod` |
| `HTTP_ADDR` | HTTP server address | `:8091` |
| `DEBUG` | Enable debug logging | `false` |

## Search API

**Endpoint:** `POST /search`

**Auth:** Bearer token (JWT) with `app_name` claim

**Request:**
```json
{
  "index_uid": "optional (defaults to {app_name}_{MEILI_INDEX})",
  "q": "search query (required)",
  "offset": 0,
  "limit": 20,
  "filter": {},
  "sort": ["field:asc"]
}
```

## Related Projects

- `../UniData/` - FastAPI Python service (data producer)
- `../frontend/` - React admin interface for testing search functionality
