import asyncio
import json
import os
import time

import redis.asyncio as aredis
from motor.motor_asyncio import AsyncIOMotorClient

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "tracing")
STREAM_KEY = "spans:raw"
GROUP = "mongo-cg"
CONSUMER = "mongo-writer-1"
BATCH_SIZE = 200
BLOCK_MS = 2000


def _parse_span(msg_id: str, fields: dict) -> dict:
    doc = {
        "_stream_id": msg_id,
        "traceId": fields["traceId"],
        "spanId": fields["spanId"],
        "service": fields["service"],
        "resource": fields["resource"],
        "type": fields.get("type", "custom"),
        "start": int(fields["start"]),
        "duration": int(fields["duration"]),
        "error": int(fields.get("error", 0)),
        "ingested_at": int(time.time() * 1000),
    }
    if "parentSpanId" in fields:
        doc["parentSpanId"] = fields["parentSpanId"]
    if "meta" in fields:
        doc["meta"] = json.loads(fields["meta"])
    if "metrics" in fields:
        doc["metrics"] = json.loads(fields["metrics"])
    return doc


async def main():
    r = aredis.from_url(REDIS_URL, decode_responses=True)
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo[MONGO_DB]
    spans_col = db["spans"]

    await spans_col.create_index([("traceId", 1)])
    await spans_col.create_index([("spanId", 1)], unique=True)
    await spans_col.create_index([("service", 1), ("start", -1)])

    try:
        await r.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
    except aredis.ResponseError as e:
        if "BUSYGROUP" not in str(e):
            raise

    print(f"[mongo-writer] Listening on stream '{STREAM_KEY}' group '{GROUP}'")

    while True:
        entries = await r.xreadgroup(
            GROUP, CONSUMER, {STREAM_KEY: ">"}, count=BATCH_SIZE, block=BLOCK_MS
        )
        if not entries:
            continue

        _, messages = entries[0]
        ids = []
        docs = []

        for msg_id, fields in messages:
            ids.append(msg_id)
            docs.append(_parse_span(msg_id, fields))

        try:
            result = await spans_col.insert_many(docs, ordered=False)
            inserted = len(result.inserted_ids)
        except Exception as e:
            # ordered=False means partial writes succeed; duplicates are skipped
            inserted = getattr(e, "details", {}).get("nInserted", 0)

        await r.xack(STREAM_KEY, GROUP, *ids)
        print(f"[mongo-writer] Inserted {inserted}/{len(docs)} spans")


if __name__ == "__main__":
    asyncio.run(main())
