"""Initial Florida PSC schema

Revision ID: 001_initial
Revises:
Create Date: 2026-01-07

Creates Florida-specific tables:
- fl_dockets: Docket metadata from ClerkOffice API
- fl_documents: Documents from Thunderstone search
- fl_hearings: Hearing transcripts
- fl_transcript_segments: Speaker-attributed segments
- fl_entities: Extracted entities from transcripts

Pass 2 tables (commented out, will be added later):
- fl_parties: Utilities, intervenors, agencies
- fl_docket_parties: Party involvement in dockets
- fl_commissioners: Current and historical commissioners
- fl_people: Witnesses, attorneys
- fl_document_types: Document type taxonomy
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # =========================================================================
    # FL_DOCKETS - Core docket tracking from ClerkOffice API
    # =========================================================================
    op.create_table(
        'fl_dockets',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('docket_number', sa.String(20), unique=True, nullable=False),

        # Parsed components
        sa.Column('year', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('sector_code', sa.String(2)),

        # ClerkOffice API fields
        sa.Column('title', sa.Text()),
        sa.Column('utility_name', sa.String(255)),
        sa.Column('status', sa.String(50)),  # Open, Closed, etc.
        sa.Column('case_type', sa.String(100)),  # Rate Case, Fuel Clause, etc.
        sa.Column('industry_type', sa.String(50)),  # Electric, Gas, Water, Telecom

        # Filing metadata
        sa.Column('filed_date', sa.Date()),
        sa.Column('closed_date', sa.Date()),

        # Florida-specific fields
        sa.Column('psc_docket_url', sa.String(500)),
        sa.Column('commissioner_assignments', postgresql.JSONB()),  # Assigned commissioners
        sa.Column('related_dockets', postgresql.ARRAY(sa.Text())),  # Cross-referenced dockets

        # Rate case outcome fields (Pass 2 - nullable for now)
        sa.Column('requested_revenue_increase', sa.Numeric(15, 2)),
        sa.Column('approved_revenue_increase', sa.Numeric(15, 2)),
        sa.Column('requested_roe', sa.Numeric(5, 2)),  # Return on equity requested
        sa.Column('approved_roe', sa.Numeric(5, 2)),  # Return on equity approved
        sa.Column('final_order_number', sa.String(50)),
        sa.Column('vote_result', sa.String(20)),  # '5-0', '3-2', etc.

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Indexes for fl_dockets
    op.create_index('idx_fl_dockets_year', 'fl_dockets', ['year'])
    op.create_index('idx_fl_dockets_sector', 'fl_dockets', ['sector_code'])
    op.create_index('idx_fl_dockets_utility', 'fl_dockets', ['utility_name'])
    op.create_index('idx_fl_dockets_status', 'fl_dockets', ['status'])
    op.create_index('idx_fl_dockets_case_type', 'fl_dockets', ['case_type'])
    op.create_index('idx_fl_dockets_filed_date', 'fl_dockets', ['filed_date'])

    # =========================================================================
    # FL_DOCUMENTS - Documents from Thunderstone search
    # =========================================================================
    op.create_table(
        'fl_documents',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('thunderstone_id', sa.String(100)),  # Internal Thunderstone ID

        # Document metadata
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('document_type', sa.String(100)),  # Filing, Order, Testimony, etc.
        sa.Column('profile', sa.String(50)),  # Thunderstone profile source

        # Associations
        sa.Column('docket_number', sa.String(20), sa.ForeignKey('fl_dockets.docket_number')),

        # Content
        sa.Column('file_url', sa.String(500)),
        sa.Column('file_type', sa.String(20)),  # PDF, DOC, etc.
        sa.Column('file_size_bytes', sa.Integer()),

        # Dates
        sa.Column('filed_date', sa.Date()),
        sa.Column('effective_date', sa.Date()),

        # Full-text search
        sa.Column('content_text', sa.Text()),  # Extracted text for search
        # tsvector column added below with raw SQL

        # Florida-specific
        sa.Column('filer_name', sa.String(255)),
        sa.Column('document_number', sa.String(50)),  # PSC document tracking number

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('scraped_at', sa.DateTime()),
    )

    # Add tsvector column for full-text search
    op.execute("""
        ALTER TABLE fl_documents
        ADD COLUMN content_tsvector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', COALESCE(content_text, ''))) STORED
    """)

    # Indexes for fl_documents
    op.create_index('idx_fl_documents_docket', 'fl_documents', ['docket_number'])
    op.create_index('idx_fl_documents_type', 'fl_documents', ['document_type'])
    op.create_index('idx_fl_documents_filed', 'fl_documents', ['filed_date'])
    op.create_index('idx_fl_documents_profile', 'fl_documents', ['profile'])
    op.execute('CREATE INDEX idx_fl_documents_fts ON fl_documents USING GIN(content_tsvector)')

    # =========================================================================
    # FL_HEARINGS - Hearing transcripts
    # =========================================================================
    op.create_table(
        'fl_hearings',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('docket_number', sa.String(20), sa.ForeignKey('fl_dockets.docket_number')),

        # Hearing details
        sa.Column('hearing_date', sa.Date(), nullable=False),
        sa.Column('hearing_type', sa.String(100)),  # Evidentiary, Prehearing, etc.
        sa.Column('location', sa.String(255)),
        sa.Column('title', sa.Text()),

        # Transcript
        sa.Column('transcript_url', sa.String(500)),
        sa.Column('transcript_status', sa.String(50)),  # pending, downloaded, transcribed, analyzed

        # Audio/Video source
        sa.Column('source_type', sa.String(50)),  # youtube, audio_file, etc.
        sa.Column('source_url', sa.String(500)),
        sa.Column('external_id', sa.String(100)),  # YouTube video ID, etc.
        sa.Column('duration_seconds', sa.Integer()),

        # Full transcript text
        sa.Column('full_text', sa.Text()),
        sa.Column('word_count', sa.Integer()),

        # Processing metadata
        sa.Column('whisper_model', sa.String(50)),
        sa.Column('transcription_confidence', sa.Float()),
        sa.Column('processing_cost_usd', sa.Numeric(10, 4)),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('processed_at', sa.DateTime()),
    )

    # Indexes for fl_hearings
    op.create_index('idx_fl_hearings_docket', 'fl_hearings', ['docket_number'])
    op.create_index('idx_fl_hearings_date', 'fl_hearings', ['hearing_date'])
    op.create_index('idx_fl_hearings_status', 'fl_hearings', ['transcript_status'])
    op.create_index('idx_fl_hearings_source', 'fl_hearings', ['source_type'])

    # =========================================================================
    # FL_TRANSCRIPT_SEGMENTS - Speaker-attributed segments
    # =========================================================================
    op.create_table(
        'fl_transcript_segments',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hearing_id', sa.Integer(), sa.ForeignKey('fl_hearings.id', ondelete='CASCADE')),

        # Segment data
        sa.Column('segment_index', sa.Integer()),
        sa.Column('start_time', sa.Float()),
        sa.Column('end_time', sa.Float()),

        # Speaker attribution
        sa.Column('speaker_label', sa.String(100)),  # SPEAKER_01, Commissioner Smith, etc.
        sa.Column('speaker_name', sa.String(255)),  # Resolved speaker name
        sa.Column('speaker_role', sa.String(100)),  # Commissioner, Witness, Attorney, etc.

        # Content
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('confidence', sa.Float()),

        # tsvector column added below
    )

    # Add tsvector column for full-text search
    op.execute("""
        ALTER TABLE fl_transcript_segments
        ADD COLUMN text_tsvector tsvector
        GENERATED ALWAYS AS (to_tsvector('english', COALESCE(text, ''))) STORED
    """)

    # Indexes for fl_transcript_segments
    op.create_index('idx_fl_segments_hearing', 'fl_transcript_segments', ['hearing_id'])
    op.create_index('idx_fl_segments_speaker', 'fl_transcript_segments', ['speaker_name'])
    op.create_index('idx_fl_segments_role', 'fl_transcript_segments', ['speaker_role'])
    op.execute('CREATE INDEX idx_fl_segments_fts ON fl_transcript_segments USING GIN(text_tsvector)')

    # =========================================================================
    # FL_ENTITIES - Extracted entities from transcripts
    # =========================================================================
    op.create_table(
        'fl_entities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hearing_id', sa.Integer(), sa.ForeignKey('fl_hearings.id', ondelete='CASCADE')),
        sa.Column('segment_id', sa.Integer(), sa.ForeignKey('fl_transcript_segments.id', ondelete='SET NULL')),

        # Entity data
        sa.Column('entity_type', sa.String(50)),  # utility, person, rate, statute, docket, etc.
        sa.Column('entity_value', sa.Text(), nullable=False),
        sa.Column('normalized_value', sa.Text()),  # Standardized form
        sa.Column('confidence', sa.Float()),

        # Florida-specific entity metadata
        # utility_territory, rate_schedule, tariff_number, statute_citation
        sa.Column('metadata', postgresql.JSONB()),

        # Review status
        sa.Column('status', sa.String(20), server_default='pending'),  # pending, verified, rejected
        sa.Column('reviewed_at', sa.DateTime()),
        sa.Column('reviewed_by', sa.String(100)),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    # Indexes for fl_entities
    op.create_index('idx_fl_entities_hearing', 'fl_entities', ['hearing_id'])
    op.create_index('idx_fl_entities_segment', 'fl_entities', ['segment_id'])
    op.create_index('idx_fl_entities_type', 'fl_entities', ['entity_type'])
    op.create_index('idx_fl_entities_value', 'fl_entities', ['normalized_value'])
    op.create_index('idx_fl_entities_status', 'fl_entities', ['status'])

    # =========================================================================
    # FL_ANALYSES - LLM analysis results for hearings
    # =========================================================================
    op.create_table(
        'fl_analyses',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('hearing_id', sa.Integer(), sa.ForeignKey('fl_hearings.id', ondelete='CASCADE'), unique=True),

        # Executive summary
        sa.Column('summary', sa.Text()),
        sa.Column('one_sentence_summary', sa.Text()),

        # Classification
        sa.Column('hearing_type', sa.String(100)),
        sa.Column('utility_name', sa.String(200)),
        sa.Column('sector', sa.String(50)),

        # Extracted entities (JSON)
        sa.Column('participants_json', postgresql.JSONB()),
        sa.Column('issues_json', postgresql.JSONB()),
        sa.Column('commitments_json', postgresql.JSONB()),
        sa.Column('vulnerabilities_json', postgresql.JSONB()),
        sa.Column('commissioner_concerns_json', postgresql.JSONB()),
        sa.Column('commissioner_mood', sa.String(50)),

        # Public input
        sa.Column('public_comments', sa.Text()),
        sa.Column('public_sentiment', sa.String(50)),

        # Outcome prediction
        sa.Column('likely_outcome', sa.Text()),
        sa.Column('outcome_confidence', sa.Float()),
        sa.Column('risk_factors_json', postgresql.JSONB()),
        sa.Column('action_items_json', postgresql.JSONB()),
        sa.Column('quotes_json', postgresql.JSONB()),

        # Topics and utilities extracted
        sa.Column('topics_extracted', postgresql.JSONB()),
        sa.Column('utilities_extracted', postgresql.JSONB()),
        sa.Column('dockets_extracted', postgresql.JSONB()),

        # Metadata
        sa.Column('model', sa.String(50)),
        sa.Column('cost_usd', sa.Numeric(10, 4)),
        sa.Column('confidence_score', sa.Float()),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
    )

    op.create_index('idx_fl_analyses_hearing', 'fl_analyses', ['hearing_id'])

    # =========================================================================
    # HELPER FUNCTIONS
    # =========================================================================

    # Full-text search function for Florida documents
    op.execute("""
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
    """)

    # Full-text search function for Florida transcript segments
    op.execute("""
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
    """)

    # Unified search across documents and transcripts
    op.execute("""
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
    """)


def downgrade() -> None:
    # Drop functions
    op.execute('DROP FUNCTION IF EXISTS fl_unified_search(TEXT, TEXT, INTEGER)')
    op.execute('DROP FUNCTION IF EXISTS fl_search_transcripts(TEXT, TEXT, TEXT, INTEGER)')
    op.execute('DROP FUNCTION IF EXISTS fl_search_documents(TEXT, TEXT, TEXT, INTEGER)')

    # Drop tables in reverse order
    op.drop_table('fl_analyses')
    op.drop_table('fl_entities')
    op.drop_table('fl_transcript_segments')
    op.drop_table('fl_hearings')
    op.drop_table('fl_documents')
    op.drop_table('fl_dockets')
