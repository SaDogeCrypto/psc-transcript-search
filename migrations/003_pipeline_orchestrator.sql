-- Migration: Pipeline Orchestrator
-- Created: 2026-01-05
-- Adds scheduling and orchestrator state tracking for the pipeline

-- Add processing tracking fields to hearings
ALTER TABLE hearings ADD COLUMN processing_started_at DATETIME;
ALTER TABLE hearings ADD COLUMN processing_cost_usd DECIMAL(10,4) DEFAULT 0;

-- Pipeline schedules for automated runs
CREATE TABLE IF NOT EXISTS pipeline_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(100) NOT NULL UNIQUE,
    schedule_type VARCHAR(20) NOT NULL,       -- 'interval', 'daily', 'cron'
    schedule_value VARCHAR(100) NOT NULL,     -- '30m', '08:00', '0 */4 * * *'
    target VARCHAR(50) NOT NULL,              -- 'scraper', 'pipeline', 'all'
    enabled BOOLEAN DEFAULT 1,

    -- Configuration
    config_json TEXT DEFAULT '{}',            -- {states: [], max_cost: 50, only_stage: null}

    -- Tracking
    last_run_at DATETIME,
    next_run_at DATETIME,
    last_run_status VARCHAR(20),              -- 'success', 'error'
    last_run_error TEXT,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Pipeline orchestrator state (singleton row for live status)
CREATE TABLE IF NOT EXISTS pipeline_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),    -- Singleton enforcement
    status VARCHAR(20) DEFAULT 'idle',        -- 'idle', 'running', 'paused', 'stopping'
    started_at DATETIME,

    -- Current work
    current_hearing_id INTEGER REFERENCES hearings(id),
    current_stage VARCHAR(30),

    -- Session stats
    hearings_processed INTEGER DEFAULT 0,
    errors_count INTEGER DEFAULT 0,
    total_cost_usd DECIMAL(10,4) DEFAULT 0,
    last_error TEXT,

    -- Configuration for current run
    config_json TEXT DEFAULT '{}',            -- {states: [], max_cost: 50, only_stage: null}

    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Initialize singleton row
INSERT OR IGNORE INTO pipeline_state (id, status) VALUES (1, 'idle');

-- Indexes for efficient orchestrator queries
CREATE INDEX IF NOT EXISTS idx_hearings_status ON hearings(status);
CREATE INDEX IF NOT EXISTS idx_hearings_status_date ON hearings(status, hearing_date);
CREATE INDEX IF NOT EXISTS idx_hearings_processing ON hearings(status, processing_started_at);
CREATE INDEX IF NOT EXISTS idx_schedules_enabled ON pipeline_schedules(enabled, next_run_at);
