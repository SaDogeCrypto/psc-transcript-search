-- Migration: Add persistent docket tracking
-- Created: 2026-01-05

-- Persistent docket/topic tracking
CREATE TABLE IF NOT EXISTS dockets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state_id INTEGER REFERENCES states(id),
    docket_number VARCHAR(50) NOT NULL,        -- Raw: "44160", "A.24-01-001"
    normalized_id VARCHAR(60) NOT NULL UNIQUE, -- "GA-44160", "CA-A.24-01-001"

    -- Metadata (extracted/enriched over time)
    docket_type VARCHAR(50),                   -- rate_case, irp, rulemaking, complaint
    company VARCHAR(255),
    title VARCHAR(500),
    description TEXT,

    -- Rolling summary (updated each time docket mentioned)
    current_summary TEXT,
    status VARCHAR(50) DEFAULT 'open',         -- open, closed, pending_decision
    decision_expected DATE,

    -- Tracking
    first_seen_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_mentioned_at DATETIME,
    mention_count INTEGER DEFAULT 1,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Junction: which hearings mention which dockets
CREATE TABLE IF NOT EXISTS hearing_dockets (
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    docket_id INTEGER REFERENCES dockets(id) ON DELETE CASCADE,

    -- Context for this specific mention
    mention_summary TEXT,                      -- What was said about this docket
    timestamps_json TEXT,                      -- JSON: [{start, end, quote}]

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (hearing_id, docket_id)
);

-- User watchlists (for future alerting)
CREATE TABLE IF NOT EXISTS user_watchlist (
    user_id INTEGER,
    docket_id INTEGER REFERENCES dockets(id) ON DELETE CASCADE,
    notify_on_mention BOOLEAN DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, docket_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_dockets_state ON dockets(state_id);
CREATE INDEX IF NOT EXISTS idx_dockets_normalized ON dockets(normalized_id);
CREATE INDEX IF NOT EXISTS idx_dockets_company ON dockets(company);
CREATE INDEX IF NOT EXISTS idx_dockets_status ON dockets(status);
CREATE INDEX IF NOT EXISTS idx_hearing_dockets_docket ON hearing_dockets(docket_id);
