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
| `websocket-gateway` | 8001 | Subscribes to Redis pub/sub + polls counters; fans out to dashboard clients |
| `query-api` | 8002 | REST API for trace lookup and historical queries |
| `dashboard` | 3000 | React + Vite real-time monitoring UI |
| `load-generator` | — | Synthetic traffic tool; emits realistic multi-service traces |

## Infrastructure

| Component | Port | Role |
|---|---|---|
| Redis 7 | 6379 | Streams (queue), sorted sets (metrics), pub/sub (alerts) |
| MongoDB 7 | 27017 | Raw span storage (cold path) |
| PostgreSQL 16 | 5433 | Hourly rollups, service dependency map (warm path) |
| RedisInsight | 8001 | Redis visual debugger |

## Quick Start

```bash
# 1. Start infrastructure
docker compose up -d

# 2. Verify all healthy
docker compose ps

# 3. Run load generator (once ingestion service is up)
cd load-generator
pip install -r requirements.txt
python generator.py --rps 5 --chaos
```

## Span Contract

Every service emits spans in this shape:

```json
{
  "traceId":      "abc123xyz",
  "spanId":       "span-001",
  "parentSpanId": null,
  "service":      "orders",
  "operation":    "checkout",
  "startTime":    1718700000000,
  "duration_ms":  8000,
  "status":       "ok",
  "tags": {
    "http.method": "POST"
  }
}
```

`startTime` is Unix milliseconds. `parentSpanId` is `null` for root spans.
`spanId`/`parentSpanId` together define the trace tree — required for waterfall rendering.

## WebSocket Message Contract

```json
{ "type": "metrics_update", "service": "payments", "rps": 12, "errorRate": 0.03, "p95_ms": 340 }
{ "type": "alert", "service": "payments", "message": "Error rate crossed 5%", "timestamp": 1718700000000 }
```

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

## Roadmap

- [x] Phase 0 — Repo skeleton + docker-compose + contracts
- [ ] Phase 1 — Ingestion service (FastAPI → Redis Stream)
- [ ] Phase 2 — Counter worker + anomaly worker (Redis sorted sets, pub/sub)
- [ ] Phase 3 — Mongo writer + trace reconstruction API
- [ ] Phase 4 — Rollup worker + PostgreSQL schema
- [ ] Phase 5 — WebSocket gateway
- [ ] Phase 6 — React dashboard (waterfall, live charts, alert feed)
- [ ] Phase 7 — Load generator benchmarks + perf writeup

## License

MIT
