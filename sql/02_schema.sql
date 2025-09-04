-- Connect to DB before running: \c tracker
-- Use dedicated schema 'app' (recommended)
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION tracker;
ALTER ROLE tracker SET search_path = app, public;

-- Tables
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active TIMESTAMPTZ DEFAULT NOW(),
    settings JSONB DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS items (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    url TEXT NOT NULL,
    asin TEXT,
    domain TEXT,
    title TEXT,
    currency TEXT DEFAULT 'EUR',
    last_price DOUBLE PRECISION,
    min_price DOUBLE PRECISION,
    max_price DOUBLE PRECISION,
    target_price DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    last_checked TIMESTAMPTZ,
    check_count INTEGER DEFAULT 0,
    notification_sent_at TIMESTAMPTZ,
    category TEXT,
    priority INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS price_history (
    id BIGSERIAL PRIMARY KEY,
    item_id BIGINT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    price DOUBLE PRECISION NOT NULL,
    currency TEXT DEFAULT 'EUR',
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    source TEXT DEFAULT 'keepa',
    availability TEXT
);

CREATE TABLE IF NOT EXISTS user_stats (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    items_tracked INTEGER DEFAULT 0,
    total_savings DOUBLE PRECISION DEFAULT 0.0,
    notifications_sent INTEGER DEFAULT 0,
    last_activity TIMESTAMPTZ DEFAULT NOW(),
    total_checks INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS system_metrics (
    id BIGSERIAL PRIMARY KEY,
    metric_name TEXT NOT NULL,
    metric_value DOUBLE PRECISION NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    metadata TEXT
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_items_user_id ON items(user_id);
CREATE INDEX IF NOT EXISTS idx_items_asin ON items(asin);
CREATE INDEX IF NOT EXISTS idx_items_active ON items(is_active);
CREATE INDEX IF NOT EXISTS idx_items_last_checked ON items(last_checked);
CREATE INDEX IF NOT EXISTS idx_price_history_item_id ON price_history(item_id);
CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active);
CREATE INDEX IF NOT EXISTS idx_system_metrics_name_time ON system_metrics(metric_name, timestamp);
