# Go Agent Build Guide

This file is the source of truth for an AI agent building or validating the
`meilisearch-sync-service` binary. Work from this directory, not the repository
root:

```bash
cd meilisearch-sync-service
```

## Prerequisites

### Required to build

- Go `1.25.4` or newer. The exact module requirement is in `go.mod`.
- Network access to the configured Go module proxy on the first build, or a
  pre-populated Go module cache containing the dependencies in `go.sum`.
- A POSIX shell. The documented commands work on Linux and macOS.

Docker is optional. It is only needed when building the container image or
running the complete local CDC stack.

### Required to run the binary

- A reachable Kafka cluster with the CDC, command, API-key, and DLQ topics.
- A reachable Meilisearch instance.
- A reachable Redis instance for the regional API-key registry.
- A reachable UniData control plane and the matching agent registration token.

Do not put real secrets in `.env.example`, source files, build logs, or agent
output. Use a local `.env` file or injected environment variables.

## Build

Run the following from `meilisearch-sync-service/`:

```bash
go version
go mod download
go test ./...
go vet ./...
CGO_ENABLED=0 go build -trimpath -ldflags="-s -w" -o ./bin/meilisearch-sync-service ./main.go
```

The resulting executable is `./bin/meilisearch-sync-service`. `CGO_ENABLED=0`
produces a portable static Go binary, matching the Docker build. Do not run
`go get` or change `go.mod`/`go.sum` merely to build the existing project.

For race detection during a code change, run:

```bash
go test -race ./...
```

## Container Build

Build from this directory because the Dockerfile copies this Go module as its
build context:

```bash
docker build -t melidata/meilisearch-sync-service:local .
```

The Dockerfile uses `golang:1.25-alpine`, runs `go mod download`, compiles the
same static binary, and executes it as the unprivileged `melidata` user.

## Runtime Configuration

Start from the checked-in template without committing the generated file:

```bash
cp .env.example .env
```

The executable loads `.env` from its current working directory, then reads the
same values from the process environment. Environment variables are suitable
for deployments; do not rely on `.env` being available inside a container.

Minimum operational settings are:

| Variable | Purpose |
| --- | --- |
| `KAFKA_BROKERS` | Comma-separated reachable Kafka bootstrap addresses. |
| `KAFKA_TOPIC` | CDC outbox topic, normally `pg.public.search_outbox`. |
| `REGION_ID` and `KAFKA_GROUP_PREFIX` | Derive a region-specific consumer group. Regions must not share a group. |
| `MEILI_HOST` and `MEILI_API_KEY` | Private Meilisearch endpoint and server-side credential. |
| `UNIDATA_URL` and `AGENT_REGISTRATION_TOKEN` | Agent registration and API-key snapshot source. |
| `AGENT_PUBLIC_URL`, or `AGENT_IP` and `AGENT_PORT` | Address advertised to UniData for client discovery. |
| `REDIS_ADDR`, `REDIS_PASSWORD`, `REDIS_DB` | Regional API-key registry. |
| `HTTP_ADDR` | Agent HTTP listen address, default `:8091`. |

The service also reads `KAFKA_COMMAND_TOPIC`, `KAFKA_API_KEY_TOPIC`, and
`KAFKA_DLQ_TOPIC`; their defaults are defined in `internal/config/config.go`.
Set `AGENT_PUBLIC_URL` for a stable externally reachable address. If it is not
set, provide the appropriate agent IP and port settings for registration.

### CDC Batch Write Settings

Batch writes are enabled by default. Use these values when testing throughput:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MEILI_BATCH_ENABLED` | `true` | Set `false` for single-record compatibility mode. |
| `MEILI_BATCH_SIZE` | `100` | Flush after this many CDC events in one topic partition. |
| `MEILI_BATCH_FLUSH_MS` | `100` | Low-traffic collection window after the first CDC event. |
| `MEILI_BATCH_MAX_BYTES` | `5242880` | Maximum serialized Meilisearch request payload per sub-batch. |

All three numeric batch settings must be positive. The agent logs its resolved
batch settings at startup and emits `[meili-batch]` records with flush reasons,
batch size, source bytes, and task completion duration.

## Run and Validate

Run the locally built binary from the directory containing `.env`:

```bash
./bin/meilisearch-sync-service
```

In a separate shell, verify the HTTP server:

```bash
curl --fail http://127.0.0.1:8091/health
```

A healthy response is `{"status":"healthy"}`. A successful process start
does not prove CDC delivery: confirm Kafka consumer lag, the Agent logs, and
Meilisearch document counts when validating an end-to-end deployment.

## Constraints for Automated Changes

- Preserve the write path: `UniData -> PostgreSQL -> outbox -> Debezium ->
  Kafka -> Go Agent -> Meilisearch`. Do not bypass it with direct writes.
- Keep Kafka offset commits after the corresponding Meilisearch task succeeds.
- Preserve strict ordering within each Kafka topic partition.
- Run `go test ./...`, `go vet ./...`, and `go build ./...` after Go changes.
- Do not modify generated binaries, `.env`, or production credentials as part
  of a source change.
