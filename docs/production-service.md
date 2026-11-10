# Current Production Service

This is an operational snapshot of the service checked on **2026-11-09**. Refresh the status and deployed revision after a deployment; this file is not a substitute for the server's secret configuration.

## Host and project

| Item | Value |
| --- | --- |
| Host address | `10.17.158.114` |
| Host name | `tj-s5-meilisearch` |
| SSH account / local alias | `root` / `melidata114` |
| Project directory | `/data/pg2meili-cdc` |
| Compose project | `pg2meili` |
| Public domain | `meilisearch.1oa.com.cn` |
| Nginx | Active; listens on HTTP 80 and HTTPS 443 |

The `melidata114` alias and its SSH key are configured on the operator's local machine. On a machine without that alias, use its approved SSH configuration for `root@10.17.158.114`.

## Public routing

Nginx routes the domain to services on the host:

| URL path | Upstream | Purpose |
| --- | --- | --- |
| `/` | `127.0.0.1:8080` | UniData control plane and API |
| `/open-platform/` | `127.0.0.1:8080` | Open Platform web UI |
| `/documents/` | `127.0.0.1:8091` | Search Agent public route |
| `/aigateway` | `127.0.0.1:8001` | Separately managed host service; outside this Compose project |

The corresponding public origin is `https://meilisearch.1oa.com.cn`. Internal data services should be reached over SSH or the host's Docker network, not through the public domain.

## Running Compose services

At the time of inspection, the eight long-running containers below were up. The three HTTP health endpoints checked locally on the host returned `200`.

| Compose service | Image | Status | Host port binding |
| --- | --- | --- | --- |
| `unidata` | `unidata:local` | healthy | `0.0.0.0:8080` |
| `meilisearch-sync` | `pg2meili-meilisearch-sync` | healthy | `0.0.0.0:8091` |
| `postgres` | `postgres:16` | healthy | `0.0.0.0:5432` |
| `kafka` | `quay.io/debezium/kafka:2.4` | healthy | `0.0.0.0:9092` |
| `meilisearch` | `getmeili/meilisearch:v1.8` | healthy | `0.0.0.0:7700` |
| `redis` | `redis:7-alpine` | healthy | `0.0.0.0:16379` → container `6379` |
| `connect` | `quay.io/debezium/connect:2.4` | up | `0.0.0.0:8083` |
| `zookeeper` | `quay.io/debezium/zookeeper:2.4` | up | `0.0.0.0:2181` |

The host port bindings above were observed on the live machine. They are broader than the loopback-only bindings defined by `docker-compose.prod.yml`; do not assume that file is currently applied. Review host firewall and network access before changing port bindings.

## Inspect and operate

```bash
ssh melidata114
```

After logging in to the host:

```bash
cd /data/pg2meili-cdc

# View service state and recent logs
docker compose ps
docker compose logs --tail=100 unidata

# Check local health endpoints on the host
curl -fsS http://127.0.0.1:8080/health
curl -fsS http://127.0.0.1:8091/health
curl -fsS http://127.0.0.1:7700/health
```

Compose also defines one-time setup services (`postgres-role-init`, `unidata-migrate`, `postgres-cdc-init`, `kafka-init`, and `connect-init`). Their absence from `docker compose ps` after successful startup is expected.

## Deployment revision and source state

The server checkout reported commit `18d35eb` on branch `main`; the repository checkout where this note was written reported `abf2370` on `main`. The server working tree also had modified and untracked files. Therefore, the checked-in commit alone does not fully identify the code and configuration currently present on the server.

Secret-bearing files such as `.env` and `.env.docker` are present on the server and must stay out of this repository. Record required configuration names or operational facts here, never secret values, tokens, connection strings, or private keys.
