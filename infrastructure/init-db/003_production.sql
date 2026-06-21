-- DeadMile AI — Production schema (carriers, API keys, audit)

CREATE TABLE IF NOT EXISTS carrier_profiles (
    id SERIAL PRIMARY KEY,
    carrier_id VARCHAR(64) UNIQUE NOT NULL DEFAULT 'default',
    company_name VARCHAR(200) NOT NULL DEFAULT 'My Fleet',
    default_equipment VARCHAR(20) DEFAULT 'Dry Van',
    max_deadhead_miles INTEGER DEFAULT 250,
    fuel_price_per_gallon DECIMAL(6, 2) DEFAULT 3.90,
    avg_mpg_loaded DECIMAL(4, 2) DEFAULT 6.0,
    avg_mpg_empty DECIMAL(4, 2) DEFAULT 7.0,
    driver_cpm DECIMAL(6, 4) DEFAULT 0.55,
    insurance_per_mile DECIMAL(6, 4) DEFAULT 0.08,
    maintenance_per_mile DECIMAL(6, 4) DEFAULT 0.15,
    tolls_per_mile DECIMAL(6, 4) DEFAULT 0.04,
    dispatch_fee_percent DECIMAL(5, 4) DEFAULT 0.05,
    factoring_fee_percent DECIMAL(5, 4) DEFAULT 0.03,
    overhead_per_mile DECIMAL(6, 4) DEFAULT 0.05,
    home_city VARCHAR(100),
    home_state VARCHAR(2),
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO carrier_profiles (carrier_id, company_name)
VALUES ('default', 'My Fleet')
ON CONFLICT (carrier_id) DO NOTHING;

CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    label VARCHAR(100) NOT NULL DEFAULT 'default',
    carrier_id VARCHAR(64) NOT NULL DEFAULT 'default',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    last_used_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_keys_carrier ON api_keys (carrier_id);

CREATE TABLE IF NOT EXISTS search_audit (
    id SERIAL PRIMARY KEY,
    carrier_id VARCHAR(64) NOT NULL DEFAULT 'default',
    driver_lat DECIMAL(9, 6),
    driver_lng DECIMAL(9, 6),
    equipment VARCHAR(20),
    max_deadhead_miles INTEGER,
    results_count INTEGER DEFAULT 0,
    top_load_id VARCHAR(20),
    top_net_profit DECIMAL(10, 2),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_search_audit_carrier ON search_audit (carrier_id, created_at DESC);
