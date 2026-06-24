-- DeadMile AI — Saved import analyses per carrier

CREATE TABLE IF NOT EXISTS import_history (
    id SERIAL PRIMARY KEY,
    carrier_id VARCHAR(64) NOT NULL DEFAULT 'default',
    driver_city VARCHAR(100),
    driver_state VARCHAR(2),
    equipment VARCHAR(20),
    parsed_count INTEGER DEFAULT 0,
    insight TEXT,
    loads_json JSONB NOT NULL,
    raw_preview TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_import_history_carrier ON import_history (carrier_id, created_at DESC);
