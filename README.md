# DataDog Clone — Distributed Tracing & Observability Platform

A ground-up reimplementation of core Datadog APM concepts: high-throughput
span ingestion, real-time anomaly detection, time-series storage, and a live
streaming dashboard.

---

## Architecture

```
Services (simulated)
    │  POST /spans
    ▼
Ingestion API (FastAPI) ──► Redis Streams (spans:raw)
                                  │
                    ┌─────────────┼──────────────────┐
                    ▼             ▼                   ▼
            counter-worker   anomaly-worker     mongo-writer
            (RPS, p95,       (threshold check,  (persist raw
             error rate →     publish alert →    spans →
             Redis sorted     Redis pub/sub)     MongoDB)
             sets)                │                   │
                    │             │                   ▼
                    │             │            rollup-worker (cron)
                    │             │                   │
                    │             │                   ▼
                    │             │            PostgreSQL
                    │             │            (hourly rollups,
                    │             │             service dep map)
                    ▼             ▼
              websocket-gateway
              (polls Redis counters + subscribes to pub/sub alerts)
                    │
                    ▼
              React Dashboard
```

## The Three Data Paths

| Path | Storage | Purpose | Latency |
|---|---|---|---|
| **Hot** | Redis (sorted sets, counters) | Live RPS, p95, error rate | sub-second |
| **Cold** | MongoDB | Raw span storage, trace lookup | on-demand |
| **Warm** | PostgreSQL | Pre-aggregated hourly rollups for graphs | periodic |

## Services

| Service | Port | Role |
|---|---|---|
| `ingestion-service` | 8000 | Accepts span payloads; publishes to Redis Stream `spans:raw` |
| `counter-worker` | — | Consumer group on `spans:raw`; maintains Redis sorted sets for p95/RPS/error rate |
| `anomaly-worker` | — | Consumer group on `spans:raw`; threshold checks; publishes to Redis pub/sub `alerts` |
| `mongo-writer` | — | Consumer group on `spans:raw`; persists raw spans to MongoDB |
| `rollup-worker` | — | Cron job; reads MongoDB, computes hourly rollups, writes to PostgreSQL |
| `websocket-gateway` | 8080\* | Subscribes to Redis pub/sub + polls counters; fans out to dashboard clients |
| `query-api` | 8002 | REST API for trace lookup and historical queries |
| `dashboard` | 3000 | React + Vite real-time monitoring UI |
| `load-generator` | — | Synthetic traffic tool; emits realistic multi-service traces |

## Infrastructure

| Component | Port | Role |
|---|---|---|
| Redis 7 | 6379 | Streams (queue), sorted sets (metrics), pub/sub (alerts) |
| MongoDB 7 | 27017 | Raw span storage (cold path) |
| PostgreSQL 16 | 5432 | Hourly rollups, service dependency map (warm path) |
| RedisInsight | 8001 | Redis visual debugger |

\* If port 8080 is already taken on your machine, set `WS_HOST_PORT=8090`
(or any free port) in a root `.env` file before running `docker compose up` —
the compose file falls back to `${WS_HOST_PORT:-8080}` for websocket-gateway's
host port mapping. Update `dashboard/.env`'s `VITE_WS_URL` to match if you do.

## Quick Start

```bash
# 1. Start infrastructure + all application services
docker compose up -d

# 2. Verify all healthy
docker compose ps

# 3. Run load generator (once ingestion-service is up)
cd load-generator
pip install -r requirements.txt
python generator.py --rps 5 --chaos
```

## Span Contract

Every service emits spans in this shape:

```json
{
  "traceId":      "4bf92f3577b34da6a3ce929d0e0e4736",
  "spanId":       "00f067aa0ba902b7",
  "parentSpanId": null,
  "service":      "orders",
  "resource":     "POST /checkout",
  "type":         "web",
  "start":        1718700000000000000,
  "duration":     8000000000,
  "error":        0,
  "meta": {
    "http.method": "POST"
  },
  "metrics": {
    "http.status_code": 200
  }
}
```

`start` and `duration` are Unix epoch nanoseconds. `parentSpanId` is omitted for root spans.
`spanId`/`parentSpanId` together define the trace tree — required for waterfall rendering.
See [`contracts/span.json`](contracts/span.json) for the full schema.

## WebSocket Message Contract

```json
{
  "type": "metric_update",
  "timestamp": 1718700000000,
  "service": "payments",
  "resource": "POST /checkout",
  "metrics": {
    "requestCount": 120,
    "errorCount": 4,
    "p50LatencyMs": 85,
    "p95LatencyMs": 340,
    "p99LatencyMs": 610,
    "throughputRps": 12
  }
}
{
  "type": "anomaly_alert",
  "timestamp": 1718700000000,
  "service": "payments",
  "resource": "POST /checkout",
  "severity": "high",
  "description": "Error rate crossed 5%",
  "value": 0.07,
  "baseline": 0.02
}
{ "type": "heartbeat", "timestamp": 1718700000000 }
```

See [`contracts/ws_messages.json`](contracts/ws_messages.json) for the full schema.

## Development

Each service is independently runnable. Navigate into the service directory
and follow its own `README.md`.

```
ingestion-service/   → FastAPI (Python)
workers/
  counter-worker/    → Python
  anomaly-worker/    → Python
  mongo-writer/      → Python
  rollup-worker/     → Python
websocket-gateway/   → Python / Node.js
query-api/           → FastAPI (Python)
dashboard/           → React + Vite
load-generator/      → Python
contracts/           → Canonical span + WS message schemas
```


## License

MIT
