-- Migration: Add entity validation columns for confidence scoring
-- These columns support the unified smart entity validation pipeline

-- Add confidence_score and match_type to hearing_topics
ALTER TABLE hearing_topics ADD COLUMN IF NOT EXISTS confidence_score INTEGER;
ALTER TABLE hearing_topics ADD COLUMN IF NOT EXISTS match_type VARCHAR(20);
ALTER TABLE hearing_topics ADD COLUMN IF NOT EXISTS review_reason TEXT;

-- Add confidence_score and match_type to hearing_utilities
ALTER TABLE hearing_utilities ADD COLUMN IF NOT EXISTS confidence_score INTEGER;
ALTER TABLE hearing_utilities ADD COLUMN IF NOT EXISTS match_type VARCHAR(20);
ALTER TABLE hearing_utilities ADD COLUMN IF NOT EXISTS review_reason TEXT;

-- Add confidence_score and match_type to hearing_dockets
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS confidence_score INTEGER;
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS match_type VARCHAR(20);
ALTER TABLE hearing_dockets ADD COLUMN IF NOT EXISTS review_reason TEXT;

-- Create indexes for efficient review queries
CREATE INDEX IF NOT EXISTS idx_hearing_topics_review
    ON hearing_topics(needs_review, confidence_score)
    WHERE needs_review = true;

CREATE INDEX IF NOT EXISTS idx_hearing_utilities_review
    ON hearing_utilities(needs_review, confidence_score)
    WHERE needs_review = true;

CREATE INDEX IF NOT EXISTS idx_hearing_dockets_review
    ON hearing_dockets(needs_review, confidence_score)
    WHERE needs_review = true;
