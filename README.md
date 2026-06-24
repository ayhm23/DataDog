# DataDog Clone — Real-Time Metrics Platform

A ground-up reimplementation of core DataDog concepts: high-throughput metric
ingestion, real-time anomaly detection, time-series storage, and a live
streaming dashboard.

---

## Architecture

```
                    ┌─────────────────┐
  Agents / SDK ───► │ ingestion-service│ HTTP / gRPC
                    └────────┬────────┘
                             │  Kafka: raw-metrics
          ┌──────────────────┼──────────────────────┐
          ▼                  ▼                       ▼
  ┌───────────────┐  ┌───────────────┐  ┌──────────────────┐
  │counter-worker │  │anomaly-worker │  │  mongo-writer    │
  │  (Redis HLL)  │  │  (Z-score /   │  │  (raw archive)   │
  └───────┬───────┘  │   Prophet)    │  └──────────────────┘
          │          └───────┬───────┘
          │ rollup           │ Kafka: anomalies
          ▼                  ▼
  ┌───────────────┐  ┌───────────────┐
  │rollup-worker  │  │websocket-     │
  │ (1m/5m/1h)   │  │  gateway      │◄── Dashboard (browser)
  └───────────────┘  └───────────────┘
                             ▲
                    ┌────────┴────────┐
                    │   query-api     │ REST / GraphQL
                    └─────────────────┘
                             ▲
                         MongoDB
```

## Services

| Service | Port | Role |
|---|---|---|
| `ingestion-service` | 8080 | Accepts metric payloads; publishes to Kafka |
| `counter-worker` | — | Consumes raw-metrics; maintains Redis counters & HLL cardinality |
| `anomaly-worker` | — | Z-score / rolling-window anomaly detection; publishes anomaly events |
| `mongo-writer` | — | Persists raw + rolled-up metrics to MongoDB |
| `rollup-worker` | — | Produces 1-min, 5-min, 1-hour rollup aggregates |
| `websocket-gateway` | 8081 | Pushes live metric/anomaly events to dashboard clients |
| `query-api` | 8082 | REST API for historical queries and dashboard data |
| `dashboard` | 3000 | React/Vite real-time monitoring UI |
| `load-generator` | — | Synthetic traffic tool (loadtest profile only) |

## Quick Start

```bash
# 1. Copy env template
cp .env.example .env

# 2. Start infrastructure + all services
docker compose up --build

# 3. (Optional) Run load generator
docker compose --profile loadtest up load-generator
```

## Development

Each service is independently buildable. Navigate into the service directory
and follow its own `README.md` for local dev instructions.

```
ingestion-service/   → Go / FastAPI
workers/
  counter-worker/    → Python / Go
  anomaly-worker/    → Python (numpy / statsmodels)
  mongo-writer/      → Python / Go
  rollup-worker/     → Python / Go
websocket-gateway/   → Node.js / Go
query-api/           → FastAPI / Express
dashboard/           → React + Vite
load-generator/      → Python (locust) / k6
```

## Roadmap

- [ ] Phase 0 — Repo skeleton ✅
- [ ] Phase 1 — Ingestion service + Kafka producer
- [ ] Phase 2 — Counter & rollup workers
- [ ] Phase 3 — Anomaly detection worker
- [ ] Phase 4 — Query API
- [ ] Phase 5 — WebSocket gateway
- [ ] Phase 6 — Dashboard UI
- [ ] Phase 7 — Load generator & benchmarks

## License

MIT
