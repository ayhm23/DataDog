CREATE TABLE IF NOT EXISTS hourly_rollups (
    id            BIGSERIAL PRIMARY KEY,
    hour          TIMESTAMPTZ NOT NULL,
    service       TEXT        NOT NULL,
    resource      TEXT        NOT NULL,
    span_count    BIGINT      NOT NULL DEFAULT 0,
    error_count   BIGINT      NOT NULL DEFAULT 0,
    total_dur_ns  BIGINT      NOT NULL DEFAULT 0,
    p50_ns        BIGINT      NOT NULL DEFAULT 0,
    p95_ns        BIGINT      NOT NULL DEFAULT 0,
    p99_ns        BIGINT      NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (hour, service, resource)
);

CREATE INDEX IF NOT EXISTS idx_rollups_service_hour
    ON hourly_rollups (service, hour DESC);

CREATE TABLE IF NOT EXISTS service_dependencies (
    id              BIGSERIAL PRIMARY KEY,
    parent_service  TEXT        NOT NULL,
    child_service   TEXT        NOT NULL,
    call_count      BIGINT      NOT NULL DEFAULT 0,
    last_seen       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (parent_service, child_service)
);
