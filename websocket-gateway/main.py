"""
WebSocket gateway — fans out live metrics and alerts to dashboard clients.

  • Polls Redis snapshot:* keys every POLL_INTERVAL_S seconds → metric_update messages
  • Subscribes to Redis pub/sub channel 'alerts' → anomaly_alert messages
  • Sends heartbeat every HEARTBEAT_S seconds
"""
import asyncio
import json
import os
import time

import redis.asyncio as aredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
POLL_INTERVAL_S = float(os.getenv("POLL_INTERVAL_S", "2"))
HEARTBEAT_S = float(os.getenv("HEARTBEAT_S", "30"))

app = FastAPI(title="WebSocket Gateway")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

_clients: set[WebSocket] = set()
_redis: aredis.Redis | None = None


def get_redis() -> aredis.Redis:
    global _redis
    if _redis is None:
        _redis = aredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def _broadcast(message: dict):
    if not _clients:
        return
    data = json.dumps(message)
    dead = set()
    for ws in list(_clients):
        try:
            await ws.send_text(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


async def _poll_snapshots():
    r = get_redis()
    while True:
        await asyncio.sleep(POLL_INTERVAL_S)
        if not _clients:
            continue
        try:
            keys = await r.keys("snapshot:*")
            for key in keys:
                snap = await r.hgetall(key)
                if not snap:
                    continue
                await _broadcast({
                    "type": "metric_update",
                    "timestamp": int(time.time() * 1000),
                    "service": snap.get("service", ""),
                    "resource": snap.get("resource", ""),
                    "metrics": {
                        "requestCount":  int(snap.get("count", 0)),
                        "errorCount":    int(snap.get("error_count", 0)),
                        "p95LatencyMs":  float(snap.get("p95_ms", 0)),
                        "throughputRps": float(snap.get("rps", 0)),
                    },
                })
        except Exception as e:
            print(f"[ws-gateway] Snapshot poll error: {e}")


async def _subscribe_alerts():
    r = aredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    await pubsub.subscribe("alerts")
    print("[ws-gateway] Subscribed to Redis pub/sub 'alerts'")
    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        try:
            alert = json.loads(message["data"])
            await _broadcast(alert)
        except Exception as e:
            print(f"[ws-gateway] Alert parse error: {e}")


async def _heartbeat():
    while True:
        await asyncio.sleep(HEARTBEAT_S)
        await _broadcast({"type": "heartbeat", "timestamp": int(time.time() * 1000)})


@app.on_event("startup")
async def startup():
    asyncio.create_task(_poll_snapshots())
    asyncio.create_task(_subscribe_alerts())
    asyncio.create_task(_heartbeat())
    print("[ws-gateway] Background tasks started")


@app.get("/health")
async def health():
    return {"status": "ok", "clients": len(_clients)}


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    _clients.add(ws)
    print(f"[ws-gateway] Client connected ({len(_clients)} total)")
    try:
        while True:
            # Keep connection alive; client can send pong or anything
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _clients.discard(ws)
        print(f"[ws-gateway] Client disconnected ({len(_clients)} total)")
