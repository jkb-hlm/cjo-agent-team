-- CJO Agent Data Cache — PostgreSQL Schema
-- Run against the work-agents PostgreSQL instance
-- Creates a separate schema to avoid conflicts with n8n tables

CREATE SCHEMA IF NOT EXISTS cjo;

-- Daily etracker snapshots
CREATE TABLE IF NOT EXISTS cjo.kpi_daily_etracker (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    report_id       TEXT NOT NULL,        -- e.g. EADeviceType, EAGeo, EAPage
    attribute_name  TEXT,                  -- e.g. device_type, geo_country, page_url
    attribute_value TEXT,                  -- e.g. Mobile, Germany, /collections/cycling
    unique_visits   INTEGER,
    unique_visitors INTEGER,
    page_impressions INTEGER,
    bounces_per_visit NUMERIC(5,2),
    staytime_per_visit NUMERIC(8,2),
    pi_per_visit    NUMERIC(5,2),
    conversion_count INTEGER,
    conversion_value NUMERIC(12,2),
    conversion_rate NUMERIC(8,5),
    raw_json        JSONB,                -- full row for future flexibility
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, report_id, attribute_name, attribute_value)
);

-- Daily GA4 Web snapshots
CREATE TABLE IF NOT EXISTS cjo.kpi_daily_ga4_web (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    dimension_name  TEXT,                  -- e.g. deviceCategory, sessionDefaultChannelGroup
    dimension_value TEXT,                  -- e.g. mobile, Paid Social
    sessions        INTEGER,
    total_users     INTEGER,
    new_users       INTEGER,
    bounce_rate     NUMERIC(5,4),
    avg_session_duration NUMERIC(8,2),
    pages_per_session NUMERIC(5,2),
    session_conversion_rate NUMERIC(8,5),
    ecommerce_purchases INTEGER,
    purchase_revenue NUMERIC(12,2),
    raw_json        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, dimension_name, dimension_value)
);

-- Daily GA4 App snapshots
CREATE TABLE IF NOT EXISTS cjo.kpi_daily_ga4_app (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    dimension_name  TEXT,
    dimension_value TEXT,
    sessions        INTEGER,
    total_users     INTEGER,
    new_users       INTEGER,
    bounce_rate     NUMERIC(5,4),
    avg_session_duration NUMERIC(8,2),
    pages_per_session NUMERIC(5,2),
    session_conversion_rate NUMERIC(8,5),
    ecommerce_purchases INTEGER,
    purchase_revenue NUMERIC(12,2),
    raw_json        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, dimension_name, dimension_value)
);

-- Agent learnings (persistent memory across sessions)
CREATE TABLE IF NOT EXISTS cjo.learnings (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL DEFAULT CURRENT_DATE,
    agent           TEXT NOT NULL,         -- kai, tessa, mara
    type            TEXT NOT NULL,         -- pattern, test_result, hypothesis, tracking_gap
    insight         TEXT NOT NULL,
    source_test_id  TEXT,                  -- AB Tasty test ID if applicable
    page_type       TEXT,                  -- PDP, PLP, Home, Cart, etc.
    still_valid     BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- AB Tasty test status snapshots (for Tessa monitoring)
CREATE TABLE IF NOT EXISTS cjo.test_monitor (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    test_id         TEXT NOT NULL,
    test_name       TEXT,
    status          TEXT,                  -- running, paused, stopped
    page_type       TEXT,
    visitors_control INTEGER,
    visitors_variant INTEGER,
    cr_control      NUMERIC(8,5),
    cr_variant      NUMERIC(8,5),
    chance_to_win   NUMERIC(5,2),
    aov_control     NUMERIC(10,2),
    aov_variant     NUMERIC(10,2),
    guardrail_ok    BOOLEAN,
    srm_ok          BOOLEAN,
    raw_json        JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (date, test_id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_etracker_date ON cjo.kpi_daily_etracker(date);
CREATE INDEX IF NOT EXISTS idx_etracker_report ON cjo.kpi_daily_etracker(report_id, date);
CREATE INDEX IF NOT EXISTS idx_ga4_web_date ON cjo.kpi_daily_ga4_web(date);
CREATE INDEX IF NOT EXISTS idx_ga4_app_date ON cjo.kpi_daily_ga4_app(date);
CREATE INDEX IF NOT EXISTS idx_learnings_agent ON cjo.learnings(agent, still_valid);
CREATE INDEX IF NOT EXISTS idx_test_monitor_date ON cjo.test_monitor(date, test_id);
