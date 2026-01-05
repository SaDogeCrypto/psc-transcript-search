-- PSC Transcript Search - Production Schema
-- Supports multi-state PUC hearing monitoring with pipeline tracking

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

-- ============================================================================
-- REFERENCE TABLES
-- ============================================================================

-- States we monitor
CREATE TABLE states (
    id SERIAL PRIMARY KEY,
    code VARCHAR(2) UNIQUE NOT NULL,  -- GA, CA, TX, etc.
    name VARCHAR(100) NOT NULL,
    commission_name VARCHAR(200),  -- "Georgia Public Service Commission"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert initial states
INSERT INTO states (code, name, commission_name) VALUES
    ('GA', 'Georgia', 'Georgia Public Service Commission'),
    ('CA', 'California', 'California Public Utilities Commission'),
    ('TX', 'Texas', 'Public Utility Commission of Texas');

-- ============================================================================
-- SOURCE MONITORING
-- ============================================================================

-- Sources to monitor (YouTube channels, AdminMonitor pages, etc.)
CREATE TABLE sources (
    id SERIAL PRIMARY KEY,
    state_id INTEGER REFERENCES states(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    source_type VARCHAR(50) NOT NULL,  -- 'youtube_channel', 'adminmonitor', 'state_portal'
    url TEXT NOT NULL,
    config_json JSONB DEFAULT '{}',  -- channel_id, playlist_id, scrape patterns, etc.
    enabled BOOLEAN DEFAULT TRUE,
    check_frequency_hours INTEGER DEFAULT 24,
    last_checked_at TIMESTAMP,
    last_hearing_at TIMESTAMP,  -- When we last found a new hearing
    status VARCHAR(20) DEFAULT 'pending',  -- 'healthy', 'error', 'pending'
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sources_state ON sources(state_id);
CREATE INDEX idx_sources_enabled ON sources(enabled) WHERE enabled = TRUE;

-- ============================================================================
-- HEARINGS
-- ============================================================================

-- Discovered hearings
CREATE TABLE hearings (
    id SERIAL PRIMARY KEY,
    source_id INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    state_id INTEGER REFERENCES states(id) ON DELETE CASCADE,
    external_id VARCHAR(100),  -- YouTube video ID, AdminMonitor URL slug, etc.
    title TEXT NOT NULL,
    description TEXT,
    hearing_date DATE,
    hearing_type VARCHAR(100),  -- 'rate_case', 'certificate', 'rulemaking', 'workshop', etc.
    utility_name VARCHAR(200),
    docket_numbers TEXT[],  -- Array of docket numbers
    source_url TEXT,  -- Original source page URL
    video_url TEXT,   -- Direct video/audio URL
    duration_seconds INTEGER,

    -- Pipeline status
    status VARCHAR(20) DEFAULT 'discovered',  -- discovered, processing, complete, error

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(source_id, external_id)
);

CREATE INDEX idx_hearings_state ON hearings(state_id);
CREATE INDEX idx_hearings_source ON hearings(source_id);
CREATE INDEX idx_hearings_status ON hearings(status);
CREATE INDEX idx_hearings_date ON hearings(hearing_date DESC);
CREATE INDEX idx_hearings_utility ON hearings(utility_name);

-- ============================================================================
-- PIPELINE TRACKING
-- ============================================================================

-- Pipeline jobs (one per hearing per stage)
CREATE TABLE pipeline_jobs (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    stage VARCHAR(20) NOT NULL,  -- 'download', 'transcribe', 'analyze'
    status VARCHAR(20) DEFAULT 'pending',  -- 'pending', 'running', 'complete', 'error', 'cancelled'
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    cost_usd DECIMAL(10, 4),  -- Cost for this stage
    metadata_json JSONB DEFAULT '{}',  -- Additional stage-specific data
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(hearing_id, stage)
);

CREATE INDEX idx_pipeline_jobs_hearing ON pipeline_jobs(hearing_id);
CREATE INDEX idx_pipeline_jobs_status ON pipeline_jobs(status);
CREATE INDEX idx_pipeline_jobs_stage ON pipeline_jobs(stage, status);

-- ============================================================================
-- TRANSCRIPTS
-- ============================================================================

-- Full transcripts
CREATE TABLE transcripts (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER UNIQUE REFERENCES hearings(id) ON DELETE CASCADE,
    full_text TEXT,
    word_count INTEGER,
    model VARCHAR(50),  -- 'whisper-1', 'base', 'medium', etc.
    cost_usd DECIMAL(10, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transcript segments (for search and timestamped display)
CREATE TABLE segments (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    transcript_id INTEGER REFERENCES transcripts(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL,
    speaker VARCHAR(200),
    speaker_role VARCHAR(100),  -- 'commissioner', 'utility_witness', 'intervenor', 'staff', 'public'
    embedding vector(1536),  -- OpenAI text-embedding-3-small
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(hearing_id, segment_index)
);

CREATE INDEX idx_segments_hearing ON segments(hearing_id);
CREATE INDEX idx_segments_transcript ON segments(transcript_id);
CREATE INDEX idx_segments_speaker ON segments(speaker);

-- Full-text search index
CREATE INDEX idx_segments_text_search ON segments USING GIN (to_tsvector('english', text));

-- Vector similarity index (IVFFlat for approximate nearest neighbor)
CREATE INDEX idx_segments_embedding ON segments USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ============================================================================
-- ANALYSIS RESULTS
-- ============================================================================

-- LLM-generated analysis
CREATE TABLE analyses (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER UNIQUE REFERENCES hearings(id) ON DELETE CASCADE,

    -- Executive summary
    summary TEXT,
    one_sentence_summary TEXT,

    -- Classification
    hearing_type VARCHAR(100),
    utility_name VARCHAR(200),

    -- Extracted entities
    participants_json JSONB,  -- [{name, role, affiliation}]
    issues_json JSONB,  -- [{issue, description, stance_by_party}]

    -- Utility analysis
    commitments_json JSONB,  -- [{commitment, context, binding}]
    vulnerabilities_json JSONB,  -- [{vulnerability, severity, context}]

    -- Commissioner analysis
    commissioner_concerns_json JSONB,  -- [{commissioner, concern, severity}]
    commissioner_mood VARCHAR(100),  -- 'supportive', 'skeptical', 'hostile', 'neutral'

    -- Public input
    public_comments TEXT,
    public_sentiment VARCHAR(50),  -- 'supportive', 'opposed', 'mixed', 'none'

    -- Outcome prediction
    likely_outcome TEXT,
    outcome_confidence FLOAT,  -- 0.0 to 1.0
    risk_factors_json JSONB,  -- [{factor, likelihood, impact}]

    -- Action items
    action_items_json JSONB,  -- [{item, deadline, responsible_party}]

    -- Notable quotes
    quotes_json JSONB,  -- [{quote, speaker, timestamp, significance}]

    -- Metadata
    model VARCHAR(50),  -- 'gpt-4o', 'gpt-4o-mini'
    cost_usd DECIMAL(10, 4),
    confidence_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_analyses_hearing ON analyses(hearing_id);

-- ============================================================================
-- PIPELINE RUNS (DAILY MONITORING)
-- ============================================================================

-- Daily run logs
CREATE TABLE pipeline_runs (
    id SERIAL PRIMARY KEY,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',  -- 'running', 'complete', 'error'

    -- Stats
    sources_checked INTEGER DEFAULT 0,
    new_hearings INTEGER DEFAULT 0,
    hearings_processed INTEGER DEFAULT 0,
    errors INTEGER DEFAULT 0,

    -- Costs
    transcription_cost_usd DECIMAL(10, 4) DEFAULT 0,
    analysis_cost_usd DECIMAL(10, 4) DEFAULT 0,
    total_cost_usd DECIMAL(10, 4) DEFAULT 0,

    -- Details
    details_json JSONB DEFAULT '{}',  -- Per-source breakdown, error details

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pipeline_runs_started ON pipeline_runs(started_at DESC);

-- ============================================================================
-- ALERTS (FUTURE)
-- ============================================================================

-- Alert subscriptions (for future implementation)
CREATE TABLE alert_subscriptions (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    alert_type VARCHAR(50) NOT NULL,  -- 'keyword', 'state', 'utility', 'new_hearing'
    config_json JSONB NOT NULL,  -- {keywords: [...], states: [...], utilities: [...]}
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_alert_subscriptions_email ON alert_subscriptions(email);
CREATE INDEX idx_alert_subscriptions_type ON alert_subscriptions(alert_type);

-- ============================================================================
-- HELPER FUNCTIONS
-- ============================================================================

-- Full-text search function
CREATE OR REPLACE FUNCTION search_segments(
    search_query TEXT,
    result_limit INTEGER DEFAULT 50
)
RETURNS TABLE (
    segment_id INTEGER,
    hearing_id INTEGER,
    text TEXT,
    start_time FLOAT,
    end_time FLOAT,
    speaker VARCHAR,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id,
        s.hearing_id,
        s.text,
        s.start_time,
        s.end_time,
        s.speaker,
        ts_rank(to_tsvector('english', s.text), plainto_tsquery('english', search_query)) as rank
    FROM segments s
    WHERE to_tsvector('english', s.text) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Get hearing pipeline status
CREATE OR REPLACE FUNCTION get_hearing_pipeline_status(p_hearing_id INTEGER)
RETURNS TABLE (
    stage VARCHAR,
    status VARCHAR,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        pj.stage,
        pj.status,
        pj.started_at,
        pj.completed_at,
        pj.error_message
    FROM pipeline_jobs pj
    WHERE pj.hearing_id = p_hearing_id
    ORDER BY
        CASE pj.stage
            WHEN 'download' THEN 1
            WHEN 'transcribe' THEN 2
            WHEN 'analyze' THEN 3
        END;
END;
$$ LANGUAGE plpgsql;

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply update triggers
CREATE TRIGGER update_sources_updated_at BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_hearings_updated_at BEFORE UPDATE ON hearings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER update_pipeline_jobs_updated_at BEFORE UPDATE ON pipeline_jobs
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================================================
-- INITIAL SOURCES (16 YouTube + 2 AdminMonitor)
-- ============================================================================

-- Georgia PSC YouTube
INSERT INTO sources (state_id, name, source_type, url, config_json) VALUES
    (1, 'Georgia PSC YouTube', 'youtube_channel', 'https://www.youtube.com/@GeorgiaPSC',
     '{"channel_id": "UCxxxxxxxxxx", "keywords": ["hearing", "docket"]}');

-- California CPUC AdminMonitor
INSERT INTO sources (state_id, name, source_type, url, config_json) VALUES
    (2, 'CPUC Hearings', 'adminmonitor', 'https://www.adminmonitor.com/ca/cpuc/hearing/',
     '{"archive_url": "https://www.adminmonitor.com/ca/cpuc/hearing/"}'),
    (2, 'CPUC Voting Meetings', 'adminmonitor', 'https://www.adminmonitor.com/ca/cpuc/voting_meeting/',
     '{"archive_url": "https://www.adminmonitor.com/ca/cpuc/voting_meeting/"}'),
    (2, 'CPUC Workshops', 'adminmonitor', 'https://www.adminmonitor.com/ca/cpuc/workshop/',
     '{"archive_url": "https://www.adminmonitor.com/ca/cpuc/workshop/"}');

-- Texas PUCT AdminMonitor
INSERT INTO sources (state_id, name, source_type, url, config_json) VALUES
    (3, 'PUCT Open Meetings', 'adminmonitor', 'https://www.adminmonitor.com/tx/puct/open_meeting/',
     '{"archive_url": "https://www.adminmonitor.com/tx/puct/open_meeting/"}'),
    (3, 'PUCT Hearings', 'adminmonitor', 'https://www.adminmonitor.com/tx/puct/hearing_on_the_merits/',
     '{"archive_url": "https://www.adminmonitor.com/tx/puct/hearing_on_the_merits/"}');
