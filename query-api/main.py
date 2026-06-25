import os
from typing import Optional

import asyncpg
from fastapi import FastAPI, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as aredis

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "tracing")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PG_DSN = os.getenv("PG_DSN", "postgresql://admin:admin@localhost:5432/tracing")

app = FastAPI(title="Query API")

_mongo: AsyncIOMotorClient | None = None
_redis: aredis.Redis | None = None
_pg: asyncpg.Pool | None = None


def get_db():
    global _mongo
    if _mongo is None:
        _mongo = AsyncIOMotorClient(MONGO_URL)
    return _mongo[MONGO_DB]


async def get_redis() -> aredis.Redis:
    global _redis
    if _redis is None:
        _redis = aredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def get_pg() -> asyncpg.Pool:
    global _pg
    if _pg is None:
        _pg = await asyncpg.create_pool(PG_DSN, min_size=1, max_size=5)
    return _pg


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/traces/{trace_id}")
async def get_trace(trace_id: str):
    """Return all spans for a trace, sorted by start time."""
    db = get_db()
    cursor = db["spans"].find(
        {"traceId": trace_id},
        {"_id": 0, "_stream_id": 0},
    ).sort("start", 1)
    spans = await cursor.to_list(length=1000)
    if not spans:
        raise HTTPException(status_code=404, detail="Trace not found")
    return {"traceId": trace_id, "spans": spans}


@app.get("/spans/{span_id}")
async def get_span(span_id: str):
    """Return a single span by spanId."""
    db = get_db()
    span = await db["spans"].find_one({"spanId": span_id}, {"_id": 0, "_stream_id": 0})
    if not span:
        raise HTTPException(status_code=404, detail="Span not found")
    return span


@app.get("/services")
async def list_services():
    """Return distinct service names that have active snapshots in Redis."""
    r = await get_redis()
    keys = await r.keys("snapshot:*")
    services = sorted({k.split(":")[1] for k in keys if len(k.split(":")) >= 2})
    return {"services": services}


@app.get("/services/{service}/spans")
async def get_service_spans(
    service: str,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    error_only: bool = False,
):
    """Recent spans for a service, newest first."""
    db = get_db()
    query: dict = {"service": service}
    if error_only:
        query["error"] = 1
    cursor = (
        db["spans"]
        .find(query, {"_id": 0, "_stream_id": 0})
        .sort("start", -1)
        .skip(offset)
        .limit(limit)
    )
    spans = await cursor.to_list(length=limit)
    return {"service": service, "total": len(spans), "spans": spans}


@app.get("/metrics/live")
async def live_metrics(service: Optional[str] = None):
    """Return current snapshots from Redis for all (or one) service."""
    r = await get_redis()
    pattern = f"snapshot:{service}:*" if service else "snapshot:*"
    keys = await r.keys(pattern)

    snapshots = []
    for key in keys:
        snap = await r.hgetall(key)
        if snap:
            snapshots.append({
                "service": snap.get("service"),
                "resource": snap.get("resource"),
                "rps": float(snap.get("rps", 0)),
                "error_rate": float(snap.get("error_rate", 0)),
                "p95_ms": float(snap.get("p95_ms", 0)),
                "count": int(snap.get("count", 0)),
                "error_count": int(snap.get("error_count", 0)),
                "updated_at": int(snap.get("updated_at", 0)),
            })

    snapshots.sort(key=lambda s: (s["service"], s["resource"]))
    return {"snapshots": snapshots}


@app.get("/metrics/history")
async def metrics_history(
    service: str,
    resource: Optional[str] = None,
    hours: int = Query(default=24, le=168),
):
    """Return hourly rollups from PostgreSQL for a service (last N hours)."""
    pg = await get_pg()
    if resource:
        rows = await pg.fetch(
            """
            SELECT hour, service, resource, span_count, error_count,
                   total_dur_ns, p50_ns, p95_ns, p99_ns
            FROM hourly_rollups
            WHERE service = $1 AND resource = $2
              AND hour >= NOW() - ($3 || ' hours')::interval
            ORDER BY hour ASC
            """,
            service, resource, str(hours),
        )
    else:
        rows = await pg.fetch(
            """
            SELECT hour, service, resource, span_count, error_count,
                   total_dur_ns, p50_ns, p95_ns, p99_ns
            FROM hourly_rollups
            WHERE service = $1
              AND hour >= NOW() - ($2 || ' hours')::interval
            ORDER BY hour ASC, resource ASC
            """,
            service, str(hours),
        )
    return {"service": service, "rollups": [dict(r) for r in rows]}


@app.get("/dependencies")
async def service_dependencies():
    """Return the service dependency map from PostgreSQL."""
    pg = await get_pg()
    rows = await pg.fetch(
        "SELECT parent_service, child_service, call_count, last_seen FROM service_dependencies ORDER BY call_count DESC"
    )
    return {"edges": [dict(r) for r in rows]}
