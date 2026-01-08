-- Florida PSC Schema - Initial Tables
-- Creates Florida-specific tables for the per-state architecture
--
-- Tables created:
-- - fl_dockets: Docket metadata from ClerkOffice API
-- - fl_documents: Documents from Thunderstone search
-- - fl_hearings: Hearing transcripts
-- - fl_transcript_segments: Speaker-attributed segments
-- - fl_entities: Extracted entities from transcripts
-- - fl_analyses: LLM analysis results

-- ============================================================================
-- FL_DOCKETS - Core docket tracking from ClerkOffice API
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_dockets (
    id SERIAL PRIMARY KEY,
    docket_number VARCHAR(20) UNIQUE NOT NULL,  -- e.g., "20250001-EI"

    -- Parsed components
    year INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    sector_code VARCHAR(2),  -- EI, EU, GU, WU, etc.

    -- ClerkOffice API fields
    title TEXT,
    utility_name VARCHAR(255),
    status VARCHAR(50),  -- Open, Closed, etc.
    case_type VARCHAR(100),  -- Rate Case, Fuel Clause, etc.
    industry_type VARCHAR(50),  -- Electric, Gas, Water, Telecom

    -- Filing metadata
    filed_date DATE,
    closed_date DATE,

    -- Florida-specific fields
    psc_docket_url VARCHAR(500),
    commissioner_assignments JSONB,  -- Assigned commissioners
    related_dockets TEXT[],  -- Cross-referenced dockets

    -- Rate case outcome fields (Pass 2)
    requested_revenue_increase DECIMAL(15,2),
    approved_revenue_increase DECIMAL(15,2),
    requested_roe DECIMAL(5,2),  -- Return on equity requested
    approved_roe DECIMAL(5,2),  -- Return on equity approved
    final_order_number VARCHAR(50),
    vote_result VARCHAR(20),  -- '5-0', '3-2', etc.

    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fl_dockets
CREATE INDEX IF NOT EXISTS idx_fl_dockets_year ON fl_dockets(year);
CREATE INDEX IF NOT EXISTS idx_fl_dockets_sector ON fl_dockets(sector_code);
CREATE INDEX IF NOT EXISTS idx_fl_dockets_utility ON fl_dockets(utility_name);
CREATE INDEX IF NOT EXISTS idx_fl_dockets_status ON fl_dockets(status);
CREATE INDEX IF NOT EXISTS idx_fl_dockets_case_type ON fl_dockets(case_type);
CREATE INDEX IF NOT EXISTS idx_fl_dockets_filed_date ON fl_dockets(filed_date);

-- ============================================================================
-- FL_DOCUMENTS - Documents from Thunderstone search
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_documents (
    id SERIAL PRIMARY KEY,
    thunderstone_id VARCHAR(100),  -- Internal Thunderstone ID

    -- Document metadata
    title TEXT NOT NULL,
    document_type VARCHAR(100),  -- Filing, Order, Testimony, etc.
    profile VARCHAR(50),  -- Thunderstone profile source

    -- Associations
    docket_number VARCHAR(20) REFERENCES fl_dockets(docket_number),

    -- Content
    file_url VARCHAR(500),
    file_type VARCHAR(20),  -- PDF, DOC, etc.
    file_size_bytes INTEGER,

    -- Dates
    filed_date DATE,
    effective_date DATE,

    -- Full-text search
    content_text TEXT,  -- Extracted text for search
    content_tsvector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', COALESCE(content_text, ''))) STORED,

    -- Florida-specific
    filer_name VARCHAR(255),
    document_number VARCHAR(50),  -- PSC document tracking number

    created_at TIMESTAMP DEFAULT NOW(),
    scraped_at TIMESTAMP
);

-- Indexes for fl_documents
CREATE INDEX IF NOT EXISTS idx_fl_documents_docket ON fl_documents(docket_number);
CREATE INDEX IF NOT EXISTS idx_fl_documents_type ON fl_documents(document_type);
CREATE INDEX IF NOT EXISTS idx_fl_documents_filed ON fl_documents(filed_date);
CREATE INDEX IF NOT EXISTS idx_fl_documents_profile ON fl_documents(profile);
CREATE INDEX IF NOT EXISTS idx_fl_documents_fts ON fl_documents USING GIN(content_tsvector);

-- ============================================================================
-- FL_HEARINGS - Hearing transcripts
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_hearings (
    id SERIAL PRIMARY KEY,
    docket_number VARCHAR(20) REFERENCES fl_dockets(docket_number),

    -- Hearing details
    hearing_date DATE NOT NULL,
    hearing_type VARCHAR(100),  -- Evidentiary, Prehearing, etc.
    location VARCHAR(255),
    title TEXT,

    -- Transcript
    transcript_url VARCHAR(500),
    transcript_status VARCHAR(50),  -- pending, downloaded, transcribed, analyzed

    -- Audio/Video source
    source_type VARCHAR(50),  -- youtube, audio_file, etc.
    source_url VARCHAR(500),
    external_id VARCHAR(100),  -- YouTube video ID, etc.
    duration_seconds INTEGER,

    -- Full transcript text
    full_text TEXT,
    word_count INTEGER,

    -- Processing metadata
    whisper_model VARCHAR(50),
    transcription_confidence FLOAT,
    processing_cost_usd DECIMAL(10, 4),

    created_at TIMESTAMP DEFAULT NOW(),
    processed_at TIMESTAMP
);

-- Indexes for fl_hearings
CREATE INDEX IF NOT EXISTS idx_fl_hearings_docket ON fl_hearings(docket_number);
CREATE INDEX IF NOT EXISTS idx_fl_hearings_date ON fl_hearings(hearing_date);
CREATE INDEX IF NOT EXISTS idx_fl_hearings_status ON fl_hearings(transcript_status);
CREATE INDEX IF NOT EXISTS idx_fl_hearings_source ON fl_hearings(source_type);

-- ============================================================================
-- FL_TRANSCRIPT_SEGMENTS - Speaker-attributed segments
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_transcript_segments (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES fl_hearings(id) ON DELETE CASCADE,

    -- Segment data
    segment_index INTEGER,
    start_time FLOAT,
    end_time FLOAT,

    -- Speaker attribution
    speaker_label VARCHAR(100),  -- SPEAKER_01, Commissioner Smith, etc.
    speaker_name VARCHAR(255),  -- Resolved speaker name
    speaker_role VARCHAR(100),  -- Commissioner, Witness, Attorney, etc.

    -- Content
    text TEXT NOT NULL,
    confidence FLOAT,

    -- Full-text search
    text_tsvector TSVECTOR GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED
);

-- Indexes for fl_transcript_segments
CREATE INDEX IF NOT EXISTS idx_fl_segments_hearing ON fl_transcript_segments(hearing_id);
CREATE INDEX IF NOT EXISTS idx_fl_segments_speaker ON fl_transcript_segments(speaker_name);
CREATE INDEX IF NOT EXISTS idx_fl_segments_role ON fl_transcript_segments(speaker_role);
CREATE INDEX IF NOT EXISTS idx_fl_segments_fts ON fl_transcript_segments USING GIN(text_tsvector);

-- ============================================================================
-- FL_ENTITIES - Extracted entities from transcripts
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_entities (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES fl_hearings(id) ON DELETE CASCADE,
    segment_id INTEGER REFERENCES fl_transcript_segments(id) ON DELETE SET NULL,

    entity_type VARCHAR(50),  -- utility, person, rate, statute, docket, etc.
    entity_value TEXT NOT NULL,
    normalized_value TEXT,  -- Standardized form
    confidence FLOAT,

    -- Florida-specific entity metadata
    entity_metadata JSONB,

    -- Review status
    status VARCHAR(20) DEFAULT 'pending',  -- pending, verified, rejected
    reviewed_at TIMESTAMP,
    reviewed_by VARCHAR(100),

    created_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for fl_entities
CREATE INDEX IF NOT EXISTS idx_fl_entities_hearing ON fl_entities(hearing_id);
CREATE INDEX IF NOT EXISTS idx_fl_entities_segment ON fl_entities(segment_id);
CREATE INDEX IF NOT EXISTS idx_fl_entities_type ON fl_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_fl_entities_value ON fl_entities(normalized_value);
CREATE INDEX IF NOT EXISTS idx_fl_entities_status ON fl_entities(status);

-- ============================================================================
-- FL_ANALYSES - LLM analysis results
-- ============================================================================

CREATE TABLE IF NOT EXISTS fl_analyses (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER UNIQUE REFERENCES fl_hearings(id) ON DELETE CASCADE,

    -- Executive summary
    summary TEXT,
    one_sentence_summary TEXT,

    -- Classification
    hearing_type VARCHAR(100),
    utility_name VARCHAR(200),
    sector VARCHAR(50),

    -- Extracted entities
    participants_json JSONB,
    issues_json JSONB,
    commitments_json JSONB,
    vulnerabilities_json JSONB,
    commissioner_concerns_json JSONB,
    commissioner_mood VARCHAR(50),

    -- Public input
    public_comments TEXT,
    public_sentiment VARCHAR(50),

    -- Outcome prediction
    likely_outcome TEXT,
    outcome_confidence FLOAT,
    risk_factors_json JSONB,
    action_items_json JSONB,
    quotes_json JSONB,

    -- Topics and utilities extracted
    topics_extracted JSONB,
    utilities_extracted JSONB,
    dockets_extracted JSONB,

    -- Metadata
    model VARCHAR(50),
    cost_usd DECIMAL(10, 4),
    confidence_score FLOAT,

    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fl_analyses_hearing ON fl_analyses(hearing_id);

-- ============================================================================
-- SEARCH FUNCTIONS
-- ============================================================================

-- Full-text search for Florida documents
CREATE OR REPLACE FUNCTION fl_search_documents(
    search_query TEXT,
    docket_filter TEXT DEFAULT NULL,
    doc_type_filter TEXT DEFAULT NULL,
    result_limit INTEGER DEFAULT 50
)
RETURNS TABLE (
    document_id INTEGER,
    docket_number VARCHAR,
    title TEXT,
    document_type VARCHAR,
    filed_date DATE,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.docket_number,
        d.title,
        d.document_type,
        d.filed_date,
        ts_rank(d.content_tsvector, plainto_tsquery('english', search_query)) as rank
    FROM fl_documents d
    WHERE d.content_tsvector @@ plainto_tsquery('english', search_query)
      AND (docket_filter IS NULL OR d.docket_number = docket_filter)
      AND (doc_type_filter IS NULL OR d.document_type = doc_type_filter)
    ORDER BY rank DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Full-text search for Florida transcript segments
CREATE OR REPLACE FUNCTION fl_search_transcripts(
    search_query TEXT,
    docket_filter TEXT DEFAULT NULL,
    speaker_filter TEXT DEFAULT NULL,
    result_limit INTEGER DEFAULT 50
)
RETURNS TABLE (
    segment_id INTEGER,
    hearing_id INTEGER,
    docket_number VARCHAR,
    text TEXT,
    speaker_name VARCHAR,
    start_time FLOAT,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id,
        s.hearing_id,
        h.docket_number,
        s.text,
        s.speaker_name,
        s.start_time,
        ts_rank(s.text_tsvector, plainto_tsquery('english', search_query)) as rank
    FROM fl_transcript_segments s
    JOIN fl_hearings h ON s.hearing_id = h.id
    WHERE s.text_tsvector @@ plainto_tsquery('english', search_query)
      AND (docket_filter IS NULL OR h.docket_number = docket_filter)
      AND (speaker_filter IS NULL OR s.speaker_name = speaker_filter)
    ORDER BY rank DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Unified search across documents and transcripts
CREATE OR REPLACE FUNCTION fl_unified_search(
    search_query TEXT,
    docket_filter TEXT DEFAULT NULL,
    result_limit INTEGER DEFAULT 50
)
RETURNS TABLE (
    result_type TEXT,
    result_id INTEGER,
    docket_number VARCHAR,
    title TEXT,
    excerpt TEXT,
    result_date DATE,
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    (
        SELECT
            'document'::TEXT as result_type,
            d.id as result_id,
            d.docket_number,
            d.title,
            substring(d.content_text, 1, 300) as excerpt,
            d.filed_date as result_date,
            ts_rank(d.content_tsvector, plainto_tsquery('english', search_query)) as rank
        FROM fl_documents d
        WHERE d.content_tsvector @@ plainto_tsquery('english', search_query)
          AND (docket_filter IS NULL OR d.docket_number = docket_filter)
    )
    UNION ALL
    (
        SELECT
            'transcript'::TEXT as result_type,
            s.id as result_id,
            h.docket_number,
            h.title,
            substring(s.text, 1, 300) as excerpt,
            h.hearing_date as result_date,
            ts_rank(s.text_tsvector, plainto_tsquery('english', search_query)) as rank
        FROM fl_transcript_segments s
        JOIN fl_hearings h ON s.hearing_id = h.id
        WHERE s.text_tsvector @@ plainto_tsquery('english', search_query)
          AND (docket_filter IS NULL OR h.docket_number = docket_filter)
    )
    ORDER BY rank DESC
    LIMIT result_limit;
END;
$$ LANGUAGE plpgsql;

-- Update timestamp trigger for fl_dockets
CREATE OR REPLACE FUNCTION fl_update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_fl_dockets_updated_at ON fl_dockets;
CREATE TRIGGER update_fl_dockets_updated_at BEFORE UPDATE ON fl_dockets
    FOR EACH ROW EXECUTE FUNCTION fl_update_updated_at();
