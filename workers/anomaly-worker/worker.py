import asyncio
import json
import os
import time

import redis.asyncio as aredis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_KEY = "spans:raw"
GROUP = "anomaly-cg"
CONSUMER = "anomaly-worker-1"
ALERTS_CHANNEL = "alerts"
BATCH_SIZE = 100
BLOCK_MS = 2000

ERROR_RATE_THRESHOLD = float(os.getenv("ERROR_RATE_THRESHOLD", "0.05"))
P95_THRESHOLD_MS = float(os.getenv("P95_THRESHOLD_MS", "1000"))
ALERT_COOLDOWN_S = int(os.getenv("ALERT_COOLDOWN_S", "60"))


async def main():
    r = aredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
    except aredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[anomaly-worker] Listening on stream '{STREAM_KEY}' group '{GROUP}'")
    print(f"[anomaly-worker] Thresholds — error_rate>{ERROR_RATE_THRESHOLD:.0%} p95>{P95_THRESHOLD_MS:.0f}ms cooldown={ALERT_COOLDOWN_S}s")

    while True:
        entries = await r.xreadgroup(
            GROUP, CONSUMER, {STREAM_KEY: ">"}, count=BATCH_SIZE, block=BLOCK_MS
        )
        if not entries:
            continue

        _, messages = entries[0]
        ids = [msg_id for msg_id, _ in messages]
        seen: set[tuple[str, str]] = {
            (fields["service"], fields["resource"]) for _, fields in messages
        }

        for service, resource in seen:
            snap = await r.hgetall(f"snapshot:{service}:{resource}")
            if snap:
                await _check_and_alert(r, service, resource, snap)

        await r.xack(STREAM_KEY, GROUP, *ids)


async def _check_and_alert(r: aredis.Redis, service: str, resource: str, snap: dict):
    error_rate = float(snap.get("error_rate", 0))
    p95_ms = float(snap.get("p95_ms", 0))
    ts = int(time.time() * 1000)

    candidates = []

    if error_rate > ERROR_RATE_THRESHOLD:
        severity = "critical" if error_rate > 0.20 else "high"
        candidates.append({
            "type": "anomaly_alert",
            "timestamp": ts,
            "service": service,
            "resource": resource,
            "severity": severity,
            "description": (
                f"Error rate {error_rate:.1%} exceeds threshold {ERROR_RATE_THRESHOLD:.1%}"
            ),
            "value": error_rate,
            "baseline": ERROR_RATE_THRESHOLD,
            "_cooldown_type": "error_rate",
        })

    if p95_ms > P95_THRESHOLD_MS:
        severity = "critical" if p95_ms > P95_THRESHOLD_MS * 3 else "high"
        candidates.append({
            "type": "anomaly_alert",
            "timestamp": ts,
            "service": service,
            "resource": resource,
            "severity": severity,
            "description": (
                f"p95 latency {p95_ms:.0f}ms exceeds threshold {P95_THRESHOLD_MS:.0f}ms"
            ),
            "value": p95_ms,
            "baseline": P95_THRESHOLD_MS,
            "_cooldown_type": "p95_latency",
        })

    for alert in candidates:
        cooldown_type = alert.pop("_cooldown_type")
        cooldown_key = f"alert_cooldown:{service}:{resource}:{cooldown_type}"
        if await r.exists(cooldown_key):
            continue
        await r.publish(ALERTS_CHANNEL, json.dumps(alert))
        await r.set(cooldown_key, 1, ex=ALERT_COOLDOWN_S)
        print(f"[anomaly-worker] ALERT {alert['severity'].upper()} — {alert['description']} ({service}/{resource})")


if __name__ == "__main__":
    asyncio.run(main())
