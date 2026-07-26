import asyncio
import math
import os
import time

import redis.asyncio as aredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_KEY = "spans:raw"
GROUP = "counter-cg"
CONSUMER = "counter-worker-1"
BATCH_SIZE = 100
BLOCK_MS = 2000


async def main():
    r = aredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
    except aredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[counter-worker] Listening on stream '{STREAM_KEY}' group '{GROUP}'")

    while True:
        entries = await r.xreadgroup(
            GROUP, CONSUMER, {STREAM_KEY: ">"}, count=BATCH_SIZE, block=BLOCK_MS
        )
        if not entries:
            continue

        _, messages = entries[0]
        ids = []
        bucket = int(time.time() // 60)
        seen: set[tuple[str, str]] = set()

        pipe = r.pipeline(transaction=False)
        for msg_id, fields in messages:
            ids.append(msg_id)
            service = fields["service"]
            resource = fields["resource"]
            duration_ns = int(fields["duration"])
            error = int(fields.get("error", 0))
            prefix = f"counters:{service}:{resource}"

            pipe.incr(f"{prefix}:count:{bucket}")
            pipe.expire(f"{prefix}:count:{bucket}", 120)
            if error:
                pipe.incr(f"{prefix}:errors:{bucket}")
                pipe.expire(f"{prefix}:errors:{bucket}", 120)
            pipe.zadd(f"{prefix}:dur:{bucket}", {msg_id: duration_ns})
            pipe.expire(f"{prefix}:dur:{bucket}", 120)
            seen.add((service, resource))

        await pipe.execute()

        for service, resource in seen:
            await _update_snapshot(r, service, resource, bucket)

        await r.xack(STREAM_KEY, GROUP, *ids)
        print(f"[counter-worker] Processed {len(ids)} spans, updated {len(seen)} snapshots")


async def _update_snapshot(r: aredis.Redis, service: str, resource: str, bucket: int):
    prefix = f"counters:{service}:{resource}"
    count = int(await r.get(f"{prefix}:count:{bucket}") or 0)
    errors = int(await r.get(f"{prefix}:errors:{bucket}") or 0)

    p95_ns = 0
    total = await r.zcard(f"{prefix}:dur:{bucket}")
    if total > 0:
        idx = min(math.floor(0.95 * total), total - 1)
        result = await r.zrange(f"{prefix}:dur:{bucket}", idx, idx, withscores=True)
        if result:
            p95_ns = int(result[0][1])

    snap = {
        "service": service,
        "resource": resource,
        "rps": str(round(count / 60.0, 4)),
        "error_rate": str(round(errors / count, 6) if count > 0 else 0.0),
        "p95_ns": str(p95_ns),
        "p95_ms": str(round(p95_ns / 1_000_000, 2)),
        "count": str(count),
        "error_count": str(errors),
        "updated_at": str(int(time.time() * 1000)),
    }
    snap_key = f"snapshot:{service}:{resource}"
    await r.hset(snap_key, mapping=snap)
    await r.expire(snap_key, 300)


if __name__ == "__main__":
    asyncio.run(main())
