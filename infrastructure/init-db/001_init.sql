-- DeadMile AI — Database Initialization
-- PostgreSQL 16 + PostGIS + TimescaleDB

-- Extensions
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- loads table (PostGIS enabled)
-- =============================================================================
CREATE TABLE IF NOT EXISTS loads (
    id SERIAL PRIMARY KEY,
    load_id VARCHAR(20) UNIQUE NOT NULL,
    origin_city VARCHAR(100),
    origin_state VARCHAR(2),
    origin_zip VARCHAR(10),
    origin_point GEOGRAPHY(POINT, 4326),
    dest_city VARCHAR(100),
    dest_state VARCHAR(2),
    dest_zip VARCHAR(10),
    dest_point GEOGRAPHY(POINT, 4326),
    pickup_start TIMESTAMP,
    pickup_end TIMESTAMP,
    delivery_start TIMESTAMP,
    delivery_end TIMESTAMP,
    equipment VARCHAR(20),
    commodity VARCHAR(100),
    weight_lbs INTEGER,
    miles INTEGER,
    rate DECIMAL(10, 2),
    rate_per_mile DECIMAL(5, 2),
    requirements VARCHAR(50),
    source VARCHAR(10),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_loads_load_id ON loads (load_id);
CREATE INDEX IF NOT EXISTS idx_loads_equipment ON loads (equipment);
CREATE INDEX IF NOT EXISTS idx_loads_origin_point ON loads USING GIST (origin_point);
CREATE INDEX IF NOT EXISTS idx_loads_dest_point ON loads USING GIST (dest_point);
CREATE INDEX IF NOT EXISTS idx_loads_pickup_start ON loads (pickup_start);
CREATE INDEX IF NOT EXISTS idx_loads_origin_state ON loads (origin_state);
CREATE INDEX IF NOT EXISTS idx_loads_dest_state ON loads (dest_state);

-- =============================================================================
-- market_scores table
-- =============================================================================
CREATE TABLE IF NOT EXISTS market_scores (
    id SERIAL PRIMARY KEY,
    city VARCHAR(100) NOT NULL,
    state VARCHAR(2) NOT NULL,
    point GEOGRAPHY(POINT, 4326),
    outbound_load_count INTEGER DEFAULT 0,
    avg_outbound_rate DECIMAL(5, 2),
    avg_inbound_rate DECIMAL(5, 2),
    lane_balance_ratio DECIMAL(5, 2),
    market_score DECIMAL(8, 2),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (city, state)
);

CREATE INDEX IF NOT EXISTS idx_market_scores_point ON market_scores USING GIST (point);
CREATE INDEX IF NOT EXISTS idx_market_scores_score ON market_scores (market_score DESC);
CREATE INDEX IF NOT EXISTS idx_market_scores_state ON market_scores (state);

-- =============================================================================
-- rate_history table (TimescaleDB hypertable)
-- =============================================================================
CREATE TABLE IF NOT EXISTS rate_history (
    time TIMESTAMP NOT NULL,
    origin_city VARCHAR(100),
    origin_state VARCHAR(2),
    dest_city VARCHAR(100),
    dest_state VARCHAR(2),
    equipment VARCHAR(20),
    avg_rate_per_mile DECIMAL(5, 2),
    load_count INTEGER
);

SELECT create_hypertable('rate_history', 'time', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_rate_history_lane
    ON rate_history (origin_state, dest_state, equipment, time DESC);

-- =============================================================================
-- driver_sessions table
-- =============================================================================
CREATE TABLE IF NOT EXISTS driver_sessions (
    id SERIAL PRIMARY KEY,
    driver_id VARCHAR(50) NOT NULL,
    location_point GEOGRAPHY(POINT, 4326),
    equipment VARCHAR(20),
    max_deadhead_miles INTEGER DEFAULT 250,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_driver_sessions_driver_id ON driver_sessions (driver_id);
CREATE INDEX IF NOT EXISTS idx_driver_sessions_location ON driver_sessions USING GIST (location_point);

-- =============================================================================
-- profitability_cache table (backed by Redis in production, persisted for audit)
-- =============================================================================
CREATE TABLE IF NOT EXISTS profitability_cache (
    id SERIAL PRIMARY KEY,
    load_id VARCHAR(20) NOT NULL,
    driver_lat DECIMAL(9, 6),
    driver_lng DECIMAL(9, 6),
    net_profit DECIMAL(10, 2),
    breakdown JSONB,
    computed_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (load_id, driver_lat, driver_lng)
);

CREATE INDEX IF NOT EXISTS idx_profitability_cache_load_id ON profitability_cache (load_id);

-- =============================================================================
-- load_ingestion_log table
-- =============================================================================
CREATE TABLE IF NOT EXISTS load_ingestion_log (
    id SERIAL PRIMARY KEY,
    source_file VARCHAR(255),
    source_format VARCHAR(20),
    loads_parsed INTEGER DEFAULT 0,
    loads_failed INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',
    error_message TEXT,
    ingested_at TIMESTAMP DEFAULT NOW()
);

-- Grant permissions
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO deadmile;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO deadmile;
