# Dashboard

React + Vite real-time monitoring UI for the DataDog clone. Connects to
`websocket-gateway` for live metrics/alerts and to `query-api` for historical
trace lookup.

## Development

```bash
npm install
npm run dev
```

Runs on `http://localhost:3000` (see `vite.config.ts`).

## Environment

Configured via `.env` (see `.env` in this directory, or `.env.example` at the
repo root):

| Variable | Purpose |
|---|---|
| `VITE_WS_URL` | WebSocket URL for `websocket-gateway` (e.g. `ws://localhost:8080/ws`) — consumed in [`src/hooks/useWebSocket.ts`](src/hooks/useWebSocket.ts) for live `metric_update` / `anomaly_alert` / `heartbeat` messages |
| `VITE_QUERY_URL` | REST base URL for `query-api` (e.g. `http://localhost:8002`) — consumed in [`src/components/TraceWaterfall.tsx`](src/components/TraceWaterfall.tsx) for trace lookups |

## Build

```bash
npm run build
npm run preview
```

## Docker

```bash
docker build -t dashboard .
```

Served on port 80 in the container (mapped to `3000` in the root
`docker-compose.yml`).
