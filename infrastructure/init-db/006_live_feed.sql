-- Live load feed sync audit log

CREATE TABLE IF NOT EXISTS live_sync_log (
    id SERIAL PRIMARY KEY,
    source VARCHAR(64) NOT NULL DEFAULT 'api',
    loads_received INTEGER DEFAULT 0,
    loads_upserted INTEGER DEFAULT 0,
    status VARCHAR(20) NOT NULL DEFAULT 'ok',
    error_message TEXT,
    synced_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_live_sync_at ON live_sync_log (synced_at DESC);
