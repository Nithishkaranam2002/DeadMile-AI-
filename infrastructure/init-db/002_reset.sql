-- Reset DeadMile AI database tables (run before 001_init.sql)

DROP TABLE IF EXISTS profitability_cache CASCADE;
DROP TABLE IF EXISTS load_ingestion_log CASCADE;
DROP TABLE IF EXISTS driver_sessions CASCADE;
DROP TABLE IF EXISTS rate_history CASCADE;
DROP TABLE IF EXISTS market_scores CASCADE;
DROP TABLE IF EXISTS loads CASCADE;
