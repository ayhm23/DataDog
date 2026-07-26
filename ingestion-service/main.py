import json
import os
from typing import Literal, Optional

import redis.asyncio as aredis
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
STREAM_KEY = "spans:raw"

app = FastAPI(title="Ingestion Service")
_redis: aredis.Redis | None = None


async def get_redis() -> aredis.Redis:
    global _redis
    if _redis is None:
        _redis = aredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


class Span(BaseModel):
    traceId: str
    spanId: str
    parentSpanId: Optional[str] = None
    service: str
    resource: str
    type: Literal["web", "db", "cache", "queue", "custom"] = "custom"
    start: int = Field(..., description="Unix epoch nanoseconds")
    duration: int = Field(..., description="Span duration in nanoseconds")
    error: Literal[0, 1] = 0
    meta: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)


@app.get("/health")
async def health():
    r = await get_redis()
    try:
        await r.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Redis unavailable: {exc}")
    return {"status": "ok"}


@app.post("/spans", status_code=status.HTTP_202_ACCEPTED)
async def ingest_spans(spans: list[Span]):
    if not spans:
        raise HTTPException(status_code=400, detail="Empty span batch")

    r = await get_redis()
    pipe = r.pipeline(transaction=False)
    for span in spans:
        fields = {
            "traceId":      span.traceId,
            "spanId":       span.spanId,
            "service":      span.service,
            "resource":     span.resource,
            "type":         span.type,
            "start":        str(span.start),
            "duration":     str(span.duration),
            "error":        str(span.error),
        }
        if span.parentSpanId is not None:
            fields["parentSpanId"] = span.parentSpanId
        if span.meta:
            fields["meta"] = json.dumps(span.meta)
        if span.metrics:
            fields["metrics"] = json.dumps(span.metrics)
        pipe.xadd(STREAM_KEY, fields)

    await pipe.execute()
    return {"accepted": len(spans)}
