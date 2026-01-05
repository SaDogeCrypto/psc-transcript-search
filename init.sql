-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Hearings table (one row per YouTube video)
CREATE TABLE hearings (
    id SERIAL PRIMARY KEY,
    youtube_id VARCHAR(20) UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    hearing_date DATE,
    duration_seconds INTEGER,
    docket_numbers TEXT[],
    youtube_url TEXT NOT NULL,
    audio_path TEXT,
    transcript_status VARCHAR(20) DEFAULT 'pending', -- pending, processing, completed, failed
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Transcript segments (one row per ~30 second chunk)
CREATE TABLE segments (
    id SERIAL PRIMARY KEY,
    hearing_id INTEGER REFERENCES hearings(id) ON DELETE CASCADE,
    segment_index INTEGER NOT NULL,
    start_time FLOAT NOT NULL,
    end_time FLOAT NOT NULL,
    text TEXT NOT NULL,
    speaker VARCHAR(100), -- extracted speaker name if identifiable
    speaker_role VARCHAR(50), -- Commissioner, Utility Witness, Staff, Intervenor, etc.
    topics TEXT[], -- extracted topics
    embedding vector(1536), -- for semantic search
    created_at TIMESTAMP DEFAULT NOW(),

    UNIQUE(hearing_id, segment_index)
);

-- Create indexes for search
CREATE INDEX idx_segments_hearing ON segments(hearing_id);
CREATE INDEX idx_segments_text_search ON segments USING gin(to_tsvector('english', text));
CREATE INDEX idx_segments_embedding ON segments USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- Full-text search function
CREATE OR REPLACE FUNCTION search_segments(
    search_query TEXT,
    limit_count INTEGER DEFAULT 20
)
RETURNS TABLE (
    segment_id INTEGER,
    hearing_id INTEGER,
    youtube_id VARCHAR(20),
    hearing_title TEXT,
    start_time FLOAT,
    end_time FLOAT,
    text TEXT,
    speaker VARCHAR(100),
    rank REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.id as segment_id,
        s.hearing_id,
        h.youtube_id,
        h.title as hearing_title,
        s.start_time,
        s.end_time,
        s.text,
        s.speaker,
        ts_rank(to_tsvector('english', s.text), plainto_tsquery('english', search_query)) as rank
    FROM segments s
    JOIN hearings h ON s.hearing_id = h.id
    WHERE to_tsvector('english', s.text) @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT limit_count;
END;
$$ LANGUAGE plpgsql;
