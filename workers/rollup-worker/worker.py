"""
Rollup worker — runs every hour (or on-demand via ROLLUP_INTERVAL_S).
Reads raw spans from MongoDB for the previous complete hour,
computes p50/p95/p99 + error counts, and upserts into PostgreSQL.
Also refreshes the service_dependencies map.
"""
import asyncio
import math
import os
import time
from datetime import datetime, timezone

import asyncpg
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "tracing")
PG_DSN = os.getenv(
    "PG_DSN",
    "postgresql://admin:admin@localhost:5432/tracing",
)
ROLLUP_INTERVAL_S = int(os.getenv("ROLLUP_INTERVAL_S", "3600"))


def _hour_bucket(ts_ns: int) -> datetime:
    ts_s = ts_ns / 1_000_000_000
    dt = datetime.fromtimestamp(ts_s, tz=timezone.utc)
    return dt.replace(minute=0, second=0, microsecond=0)


def _percentile(sorted_values: list[int], p: float) -> int:
    if not sorted_values:
        return 0
    idx = min(math.floor(p * len(sorted_values)), len(sorted_values) - 1)
    return sorted_values[idx]


async def _apply_schema(pg: asyncpg.Connection):
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    with open(schema_path) as f:
        await pg.execute(f.read())


async def rollup_hour(mongo_db, pg: asyncpg.Connection, hour: datetime):
    hour_ns_start = int(hour.timestamp() * 1_000_000_000)
    hour_ns_end = hour_ns_start + 3_600_000_000_000

    pipeline = [
        {"$match": {"start": {"$gte": hour_ns_start, "$lt": hour_ns_end}}},
        {"$sort": {"service": 1, "resource": 1, "duration": 1}},
        {
            "$group": {
                "_id": {"service": "$service", "resource": "$resource"},
                "durations": {"$push": "$duration"},
                "span_count": {"$sum": 1},
                "error_count": {"$sum": "$error"},
                "total_dur": {"$sum": "$duration"},
            }
        },
    ]

    async for group in mongo_db["spans"].aggregate(pipeline, allowDiskUse=True):
        service = group["_id"]["service"]
        resource = group["_id"]["resource"]
        durations: list[int] = sorted(group["durations"])
        span_count: int = group["span_count"]
        error_count: int = group["error_count"]
        total_dur_ns: int = group["total_dur"]

        p50 = _percentile(durations, 0.50)
        p95 = _percentile(durations, 0.95)
        p99 = _percentile(durations, 0.99)

        await pg.execute(
            """
            INSERT INTO hourly_rollups
                (hour, service, resource, span_count, error_count,
                 total_dur_ns, p50_ns, p95_ns, p99_ns, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW())
            ON CONFLICT (hour, service, resource) DO UPDATE SET
                span_count   = EXCLUDED.span_count,
                error_count  = EXCLUDED.error_count,
                total_dur_ns = EXCLUDED.total_dur_ns,
                p50_ns       = EXCLUDED.p50_ns,
                p95_ns       = EXCLUDED.p95_ns,
                p99_ns       = EXCLUDED.p99_ns,
                updated_at   = NOW()
            """,
            hour, service, resource,
            span_count, error_count, total_dur_ns, p50, p95, p99,
        )

    print(f"[rollup-worker] Rolled up hour {hour.isoformat()}")


async def refresh_dependencies(mongo_db, pg: asyncpg.Connection):
    """
    Derive parent→child service edges from spans that have parentSpanId.
    Join child span's service with its parent span's service.
    """
    pipeline = [
        {"$match": {"parentSpanId": {"$exists": True}}},
        {"$lookup": {
            "from": "spans",
            "localField": "parentSpanId",
            "foreignField": "spanId",
            "as": "parent",
        }},
        {"$unwind": "$parent"},
        {"$match": {"$expr": {"$ne": ["$service", "$parent.service"]}}},
        {
            "$group": {
                "_id": {
                    "parent_service": "$parent.service",
                    "child_service": "$service",
                },
                "call_count": {"$sum": 1},
                "last_seen_ns": {"$max": "$start"},
            }
        },
    ]

    async for edge in mongo_db["spans"].aggregate(pipeline, allowDiskUse=True):
        parent_svc = edge["_id"]["parent_service"]
        child_svc = edge["_id"]["child_service"]
        call_count = edge["call_count"]
        last_seen_ns = edge["last_seen_ns"]
        last_seen_dt = datetime.fromtimestamp(last_seen_ns / 1_000_000_000, tz=timezone.utc)

        await pg.execute(
            """
            INSERT INTO service_dependencies (parent_service, child_service, call_count, last_seen)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (parent_service, child_service) DO UPDATE SET
                call_count = EXCLUDED.call_count,
                last_seen  = EXCLUDED.last_seen
            """,
            parent_svc, child_svc, call_count, last_seen_dt,
        )

    print("[rollup-worker] Refreshed service dependency map")


async def main():
    mongo = AsyncIOMotorClient(MONGO_URL)
    mongo_db = mongo[MONGO_DB]

    pg = await asyncpg.connect(PG_DSN)
    await _apply_schema(pg)

    print(f"[rollup-worker] Running every {ROLLUP_INTERVAL_S}s")

    while True:
        now = datetime.now(tz=timezone.utc)
        # Roll up the previous complete hour
        prev_hour_ts = int(now.timestamp() // 3600) * 3600 - 3600
        prev_hour = datetime.fromtimestamp(prev_hour_ts, tz=timezone.utc)

        try:
            await rollup_hour(mongo_db, pg, prev_hour)
            await refresh_dependencies(mongo_db, pg)
        except Exception as e:
            print(f"[rollup-worker] ERROR: {e}")

        await asyncio.sleep(ROLLUP_INTERVAL_S)


if __name__ == "__main__":
    asyncio.run(main())
