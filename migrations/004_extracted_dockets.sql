-- Migration: Smart Extraction Pipeline
-- Creates extracted_dockets table for candidate docket extractions with validation

-- Table for extraction candidates (before confirmation)
CREATE TABLE IF NOT EXISTS extracted_dockets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hearing_id INTEGER NOT NULL,

    -- What was extracted
    raw_text VARCHAR(100) NOT NULL,
    normalized_id VARCHAR(60),
    context_before TEXT,
    context_after TEXT,
    trigger_phrase VARCHAR(100),
    transcript_position INTEGER,

    -- Format validation
    format_valid BOOLEAN DEFAULT FALSE,
    format_score INTEGER DEFAULT 0,
    format_issues TEXT,  -- JSON array of issues

    -- Known docket matching
    match_type VARCHAR(20) DEFAULT 'none',  -- exact, fuzzy, none
    matched_known_docket_id INTEGER,
    fuzzy_score INTEGER DEFAULT 0,
    fuzzy_candidates TEXT,  -- JSON array of near-matches

    -- Context analysis
    context_score INTEGER DEFAULT 0,
    context_clues TEXT,  -- JSON array of clues found

    -- Final scoring
    confidence_score INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'pending',  -- pending, accepted, needs_review, rejected
    review_reason TEXT,

    -- Correction suggestion
    suggested_docket_id INTEGER,
    suggested_correction VARCHAR(60),
    correction_confidence INTEGER DEFAULT 0,
    correction_evidence TEXT,  -- JSON array of evidence

    -- Review tracking
    reviewed_by VARCHAR(100),
    reviewed_at TIMESTAMP,
    review_decision VARCHAR(20),  -- confirmed, corrected, rejected
    review_notes TEXT,
    final_docket_id INTEGER,  -- After review, the confirmed docket

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (hearing_id) REFERENCES hearings(id) ON DELETE CASCADE,
    FOREIGN KEY (matched_known_docket_id) REFERENCES known_dockets(id),
    FOREIGN KEY (suggested_docket_id) REFERENCES known_dockets(id),
    FOREIGN KEY (final_docket_id) REFERENCES known_dockets(id)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_extracted_hearing ON extracted_dockets(hearing_id);
CREATE INDEX IF NOT EXISTS idx_extracted_status ON extracted_dockets(status);
CREATE INDEX IF NOT EXISTS idx_extracted_confidence ON extracted_dockets(confidence_score);
CREATE INDEX IF NOT EXISTS idx_extracted_needs_review ON extracted_dockets(status) WHERE status = 'needs_review';
CREATE INDEX IF NOT EXISTS idx_extracted_normalized ON extracted_dockets(normalized_id);

-- Update known_dockets to track extraction matches
ALTER TABLE known_dockets ADD COLUMN extraction_match_count INTEGER DEFAULT 0;
