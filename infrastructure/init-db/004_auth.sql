-- DeadMile AI — User accounts for driver signup counter

CREATE TABLE IF NOT EXISTS user_accounts (
    user_id VARCHAR(64) PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    name VARCHAR(200),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_accounts_created ON user_accounts (created_at DESC);
