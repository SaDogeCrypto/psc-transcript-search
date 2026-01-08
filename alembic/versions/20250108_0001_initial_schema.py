"""Initial schema - core tables and Florida extensions.

Revision ID: 0001
Revises:
Create Date: 2025-01-08

Creates:
- Core tables: dockets, documents, hearings, transcript_segments, analyses, entities
- Florida extension tables: fl_docket_details, fl_document_details, fl_hearing_details
- Required indexes
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # ==========================================================================
    # CORE TABLES
    # ==========================================================================

    # Dockets table
    op.create_table(
        'dockets',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('state_code', sa.String(2), nullable=False, index=True),
        sa.Column('docket_number', sa.String(50), nullable=False),
        sa.Column('title', sa.Text),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(50), index=True),
        sa.Column('docket_type', sa.String(100), index=True),
        sa.Column('filed_date', sa.Date, index=True),
        sa.Column('closed_date', sa.Date),
        sa.Column('source_system', sa.String(50)),
        sa.Column('external_id', sa.String(255)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_dockets_state_number', 'dockets', ['state_code', 'docket_number'], unique=True)

    # Documents table
    op.create_table(
        'documents',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('state_code', sa.String(2), nullable=False, index=True),
        sa.Column('docket_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dockets.id', ondelete='SET NULL'), index=True),
        sa.Column('title', sa.Text, nullable=False),
        sa.Column('document_type', sa.String(100), index=True),
        sa.Column('filed_date', sa.Date, index=True),
        sa.Column('filing_party', sa.String(500)),
        sa.Column('file_url', sa.Text),
        sa.Column('file_size_bytes', sa.Integer),
        sa.Column('file_type', sa.String(50)),
        sa.Column('content_text', sa.Text),
        sa.Column('page_count', sa.Integer),
        sa.Column('source_system', sa.String(50)),
        sa.Column('external_id', sa.String(255), index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Hearings table
    op.create_table(
        'hearings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('state_code', sa.String(2), nullable=False, index=True),
        sa.Column('docket_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dockets.id', ondelete='SET NULL'), index=True),
        sa.Column('docket_number', sa.String(50), index=True),
        sa.Column('title', sa.Text),
        sa.Column('hearing_type', sa.String(100), index=True),
        sa.Column('hearing_date', sa.Date, index=True),
        sa.Column('scheduled_time', sa.Time),
        sa.Column('location', sa.Text),
        sa.Column('video_url', sa.Text),
        sa.Column('audio_url', sa.Text),
        sa.Column('duration_seconds', sa.Integer),
        sa.Column('full_text', sa.Text),
        sa.Column('word_count', sa.Integer),
        sa.Column('transcript_status', sa.String(50), index=True, server_default='pending'),
        sa.Column('whisper_model', sa.String(50)),
        sa.Column('processing_cost_usd', sa.Numeric(10, 4)),
        sa.Column('processed_at', sa.DateTime(timezone=True)),
        sa.Column('source_system', sa.String(50)),
        sa.Column('external_id', sa.String(255), index=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Transcript segments table
    op.create_table(
        'transcript_segments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('hearing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('hearings.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('segment_index', sa.Integer, nullable=False),
        sa.Column('start_time', sa.Float),
        sa.Column('end_time', sa.Float),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('speaker_label', sa.String(50)),
        sa.Column('speaker_name', sa.String(255), index=True),
        sa.Column('speaker_role', sa.String(100)),
        sa.Column('confidence', sa.Float),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_segments_hearing_index', 'transcript_segments', ['hearing_id', 'segment_index'])

    # Analyses table
    op.create_table(
        'analyses',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('hearing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('hearings.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('summary', sa.Text),
        sa.Column('one_sentence_summary', sa.Text),
        sa.Column('hearing_type', sa.String(100)),
        sa.Column('utility_name', sa.String(255), index=True),
        sa.Column('sector', sa.String(50), index=True),
        sa.Column('participants_json', postgresql.JSONB),
        sa.Column('issues_json', postgresql.JSONB),
        sa.Column('commitments_json', postgresql.JSONB),
        sa.Column('vulnerabilities_json', postgresql.JSONB),
        sa.Column('commissioner_concerns_json', postgresql.JSONB),
        sa.Column('risk_factors_json', postgresql.JSONB),
        sa.Column('action_items_json', postgresql.JSONB),
        sa.Column('quotes_json', postgresql.JSONB),
        sa.Column('topics_extracted', postgresql.JSONB),
        sa.Column('utilities_extracted', postgresql.JSONB),
        sa.Column('dockets_extracted', postgresql.JSONB),
        sa.Column('commissioner_mood', sa.String(50)),
        sa.Column('public_comments', sa.Text),
        sa.Column('public_sentiment', sa.String(50)),
        sa.Column('likely_outcome', sa.Text),
        sa.Column('outcome_confidence', sa.Float),
        sa.Column('confidence_score', sa.Float),
        sa.Column('model', sa.String(100)),
        sa.Column('cost_usd', sa.Numeric(10, 4)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Entities table
    op.create_table(
        'entities',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('state_code', sa.String(2), nullable=False, index=True),
        sa.Column('hearing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('hearings.id', ondelete='SET NULL'), index=True),
        sa.Column('analysis_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('analyses.id', ondelete='SET NULL'), index=True),
        sa.Column('entity_type', sa.String(50), nullable=False, index=True),
        sa.Column('value', sa.Text, nullable=False),
        sa.Column('normalized_value', sa.Text, index=True),
        sa.Column('context', sa.Text),
        sa.Column('confidence', sa.Float),
        sa.Column('status', sa.String(20), server_default='pending', index=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True)),
        sa.Column('reviewed_by', sa.String(255)),
        sa.Column('review_notes', sa.Text),
        sa.Column('merged_into_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('entities.id', ondelete='SET NULL')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ==========================================================================
    # FLORIDA EXTENSION TABLES
    # ==========================================================================

    # Florida docket details
    op.create_table(
        'fl_docket_details',
        sa.Column('docket_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('dockets.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('year', sa.Integer, index=True),
        sa.Column('sequence_number', sa.Integer),
        sa.Column('sector_code', sa.String(10), index=True),
        sa.Column('applicant_name', sa.String(500)),
        sa.Column('is_rate_case', sa.Boolean, server_default='false'),
        sa.Column('requested_revenue_increase', sa.Numeric(15, 2)),
        sa.Column('approved_revenue_increase', sa.Numeric(15, 2)),
        sa.Column('requested_roe', sa.Numeric(5, 3)),
        sa.Column('approved_roe', sa.Numeric(5, 3)),
        sa.Column('commissioner_assignments', postgresql.JSONB),
        sa.Column('related_dockets', postgresql.ARRAY(sa.String)),
        sa.Column('clerk_office_id', sa.String(100), index=True),
        sa.Column('clerk_office_data', postgresql.JSONB),
        sa.Column('last_synced_at', sa.DateTime(timezone=True)),
    )

    # Florida document details
    op.create_table(
        'fl_document_details',
        sa.Column('document_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('documents.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('thunderstone_id', sa.String(100), index=True),
        sa.Column('profile', sa.String(50), index=True),
        sa.Column('thunderstone_score', sa.Float),
        sa.Column('filing_party', sa.String(500)),
        sa.Column('document_category', sa.String(100)),
    )

    # Florida hearing details
    op.create_table(
        'fl_hearing_details',
        sa.Column('hearing_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('hearings.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('youtube_video_id', sa.String(50), index=True),
        sa.Column('youtube_channel_id', sa.String(50)),
        sa.Column('youtube_thumbnail_url', sa.String(500)),
        sa.Column('rss_guid', sa.String(255), index=True),
        sa.Column('rss_published_at', sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    # Drop Florida extension tables
    op.drop_table('fl_hearing_details')
    op.drop_table('fl_document_details')
    op.drop_table('fl_docket_details')

    # Drop core tables
    op.drop_table('entities')
    op.drop_table('analyses')
    op.drop_table('transcript_segments')
    op.drop_table('hearings')
    op.drop_table('documents')
    op.drop_table('dockets')
