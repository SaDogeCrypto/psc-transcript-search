"""
Florida PSC database models.

SQLAlchemy models for Florida-specific tables:
- fl_dockets: Florida docket metadata from ClerkOffice API
- fl_documents: Documents from Thunderstone search
- fl_hearings: Hearing transcripts
- fl_transcript_segments: Speaker-attributed segments
- fl_entities: Extracted entities from transcripts
- fl_analyses: LLM analysis results
- fl_utilities: Canonical utility companies
- fl_topics: Regulatory topics
- fl_hearing_dockets: Hearing-to-docket links
- fl_hearing_utilities: Hearing-to-utility links
- fl_hearing_topics: Hearing-to-topic links
"""

from florida.models.base import Base, SessionLocal, get_db, init_db
from florida.models.docket import FLDocket
from florida.models.document import FLDocument
from florida.models.hearing import FLHearing, FLTranscriptSegment
from florida.models.entity import FLEntity
from florida.models.analysis import FLAnalysis
from florida.models.watchlist import FLWatchlist
from florida.models.linking import (
    FLUtility,
    FLTopic,
    FLHearingDocket,
    FLHearingUtility,
    FLHearingTopic,
    FLEntityCorrection,
)

__all__ = [
    'Base',
    'SessionLocal',
    'get_db',
    'init_db',
    'FLDocket',
    'FLDocument',
    'FLHearing',
    'FLTranscriptSegment',
    'FLEntity',
    'FLAnalysis',
    'FLWatchlist',
    'FLUtility',
    'FLTopic',
    'FLHearingDocket',
    'FLHearingUtility',
    'FLHearingTopic',
    'FLEntityCorrection',
]
