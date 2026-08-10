# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Distributed CDC-based search synchronization system enabling "single-source write + multi-region search" architecture.

```
业务数据 → MeliData (FastAPI) → PostgreSQL → Debezium (CDC) → Kafka → Go Sync Service → Meilisearch
```

## Service Components

| Directory | Language | Purpose |
|-----------|----------|---------|
| `UniData/` | Python/FastAPI | MeliData producer service - writes data to PostgreSQL |
| `meilisearch-sync-service/` | Go | Kafka consumer - syncs changes to Meilisearch |
| `python-sdk/` | Python | Client SDK for document operations |

## Commands

### MeliData (Python/FastAPI)

```bash
cd UniData

# Setup
uv venv && source .venv/bin/activate
uv pip install -e .

# Run (development)
python main.py
# or
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Run tests
pytest
pytest tests/test_documents.py -v          # single test file
pytest tests/ -k "test_name_pattern"       # pattern match
```

### Go Sync Service

```bash
cd meilisearch-sync-service

# Build (Linux static binary for deployment)
./build.sh

# Run (development)
go run main.go
```

### Docker Compose (Full Stack)

```bash
cp .env.docker.example .env.docker

# Generate admin password hash, paste output into .env.docker with single quotes
docker compose --env-file .env.docker run --rm unidata \
  python scripts/hash_admin_password.py

# Start all services
docker compose --env-file .env.docker up -d --build

# Watch for code changes (hot reload)
docker compose --env-file .env.docker watch unidata

# Debug: Start Kafka UI
docker compose --env-file .env.docker --profile debug up -d kafka-ui
```

### Python SDK

```bash
cd python-sdk
pip install -e ".[test]"
pytest tests/ -v
```

## Architecture Notes

### CDC Pipeline

1. MeliData writes to `uni_documents` table in PostgreSQL
2. Debezium captures WAL changes via replication slot
3. CDC events flow to Kafka topic (`public.uni_documents`)
4. Go sync service consumes events and updates Meilisearch
5. Soft deletes use `is_delete` field - deleted docs are marked, not removed from DB

### Multi-Region Deployment

Each region runs an independent Go sync service with its own Kafka consumer group (`{KAFKA_GROUP_PREFIX}_{REGION_ID}`). Region ID is set via `REGION_ID` env var; legacy deployments without it use `KAFKA_GROUP_ID`.

### API Key Authentication

Open platform uses Bearer token auth. Apps and API Keys are managed via the `/api/v1/open-platform` API. All data APIs require `Authorization: Bearer <api_key>` header.

### SDK Serving

The Python SDK archive is served from the `PYTHON_SDK_ARCHIVE` path.

## Key Configuration Files

- `.env.docker` - Docker Compose environment (copy from `.env.docker.example`)
- `UniData/.env` - MeliData local development (copy from `.env.example`)
- `meilisearch-sync-service/.env` - Go service config (copy from `.env.example`)
- `docker-compose.yml` - Full stack orchestration with PostgreSQL, Kafka, Meilisearch

## Health Endpoints (running service)

- MeliData: `http://localhost:8080/health`
- API Docs: `http://localhost:8080/docs`
- Kafka Connect: `http://localhost:8083/connectors/pg-cdc-connector/status`
- Kafka UI: `http://localhost:8085` (debug profile only)
