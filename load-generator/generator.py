"""
Load generator — emits realistic multi-service traces to the ingestion API.

Usage:
    python generator.py --rps 10 --chaos

  --rps N     Target requests per second (default: 5)
  --chaos     Randomly inject errors and latency spikes
  --url URL   Ingestion service URL (default: http://localhost:8000)
"""
import argparse
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

import httpx

# ---------------------------------------------------------------------------
# Service topology — a simplified e-commerce trace fan-out
# ---------------------------------------------------------------------------
SERVICES = [
    "frontend",
    "orders",
    "payments",
    "inventory",
    "notifications",
    "user-service",
]

RESOURCES: dict[str, list[str]] = {
    "frontend":      ["GET /", "GET /cart", "POST /checkout"],
    "orders":        ["POST /orders", "GET /orders/:id", "PUT /orders/:id/status"],
    "payments":      ["POST /charge", "POST /refund", "GET /payment/:id"],
    "inventory":     ["GET /stock/:sku", "POST /reserve", "DELETE /reserve/:id"],
    "notifications": ["POST /email", "POST /sms"],
    "user-service":  ["GET /users/:id", "POST /sessions"],
}

SPAN_TYPE: dict[str, str] = {
    "frontend":      "web",
    "orders":        "web",
    "payments":      "web",
    "inventory":     "db",
    "notifications": "queue",
    "user-service":  "web",
}

# Base latency per service in ms
BASE_LATENCY_MS: dict[str, tuple[int, int]] = {
    "frontend":      (10, 50),
    "orders":        (20, 100),
    "payments":      (50, 200),
    "inventory":     (5, 30),
    "notifications": (30, 80),
    "user-service":  (10, 40),
}

# Which services a request fans out to
CALL_GRAPH: dict[str, list[str]] = {
    "frontend":   ["orders", "user-service"],
    "orders":     ["payments", "inventory"],
    "payments":   ["user-service"],
    "inventory":  [],
    "notifications": [],
    "user-service":  [],
}


@dataclass
class SpanBuilder:
    chaos: bool
    spans: list[dict] = field(default_factory=list)

    def _duration_ns(self, service: str, spike: bool = False) -> int:
        lo, hi = BASE_LATENCY_MS[service]
        ms = random.uniform(lo, hi)
        if spike:
            ms *= random.uniform(5, 20)
        return int(ms * 1_000_000)

    def _error(self) -> int:
        if not self.chaos:
            return 0
        return 1 if random.random() < 0.08 else 0

    def add(
        self,
        service: str,
        resource: str,
        trace_id: str,
        start_ns: int,
        parent_span_id: Optional[str] = None,
    ) -> tuple[str, int]:
        """Returns (span_id, end_ns)."""
        span_id = uuid.uuid4().hex[:16]
        spike = self.chaos and random.random() < 0.05
        duration_ns = self._duration_ns(service, spike=spike)
        error = self._error()

        span: dict = {
            "traceId": trace_id,
            "spanId": span_id,
            "service": service,
            "resource": resource,
            "type": SPAN_TYPE[service],
            "start": start_ns,
            "duration": duration_ns,
            "error": error,
            "meta": {"env": "load-gen"},
        }
        if parent_span_id:
            span["parentSpanId"] = parent_span_id

        self.spans.append(span)
        return span_id, start_ns + duration_ns

    def build_trace(self, entry_service: str) -> list[dict]:
        self.spans = []
        trace_id = uuid.uuid4().hex
        now_ns = int(time.time() * 1_000_000_000)

        resources = RESOURCES[entry_service]
        root_resource = random.choice(resources)
        root_id, root_end = self.add(entry_service, root_resource, trace_id, now_ns)

        def fan_out(parent_service: str, parent_id: str, start_ns: int):
            for child_service in CALL_GRAPH.get(parent_service, []):
                child_resource = random.choice(RESOURCES[child_service])
                child_id, child_end = self.add(
                    child_service, child_resource, trace_id, start_ns, parent_span_id=parent_id
                )
                fan_out(child_service, child_id, child_end)

        fan_out(entry_service, root_id, now_ns + 1_000_000)
        return self.spans


def send_batch(client: httpx.Client, url: str, spans: list[dict]):
    try:
        r = client.post(f"{url}/spans", json=spans, timeout=5)
        r.raise_for_status()
    except Exception as e:
        print(f"  [warn] send failed: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rps", type=float, default=5, help="Target requests per second")
    parser.add_argument("--chaos", action="store_true", help="Inject errors and latency spikes")
    parser.add_argument("--url", default="http://localhost:8000", help="Ingestion service base URL")
    args = parser.parse_args()

    interval = 1.0 / args.rps
    builder = SpanBuilder(chaos=args.chaos)
    entry_services = list(CALL_GRAPH.keys())[:3]  # frontend, orders, payments

    print(f"[load-gen] Sending {args.rps} RPS to {args.url} | chaos={args.chaos}")

    with httpx.Client() as client:
        while True:
            t0 = time.monotonic()
            service = random.choice(entry_services)
            spans = builder.build_trace(service)
            send_batch(client, args.url, spans)
            print(f"  trace={spans[0]['traceId'][:8]} spans={len(spans)} root={service}")
            elapsed = time.monotonic() - t0
            sleep_for = max(0.0, interval - elapsed)
            time.sleep(sleep_for)


if __name__ == "__main__":
    main()
