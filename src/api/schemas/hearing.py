"""
Hearing schemas for API requests/responses.
"""

from datetime import date, time, datetime
from typing import Optional, List, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TranscriptSegmentResponse(BaseModel):
    """Transcript segment."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    segment_index: int
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    text: str
    speaker_label: Optional[str] = None
    speaker_name: Optional[str] = None
    speaker_role: Optional[str] = None
    timestamp_display: Optional[str] = None


class AnalysisResponse(BaseModel):
    """Hearing analysis results."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    summary: Optional[str] = None
    one_sentence_summary: Optional[str] = None
    hearing_type: Optional[str] = None
    utility_name: Optional[str] = None
    sector: Optional[str] = None

    # Structured data
    participants: Optional[List[Any]] = None
    issues: Optional[List[Any]] = None
    topics: Optional[List[Any]] = None
    commitments: Optional[List[Any]] = None
    vulnerabilities: Optional[List[str]] = None
    commissioner_concerns: Optional[List[Any]] = None
    risk_factors: Optional[List[str]] = None
    action_items: Optional[List[str]] = None
    quotes: Optional[List[Any]] = None

    # Sentiment
    commissioner_mood: Optional[str] = None
    public_comments: Optional[str] = None
    public_sentiment: Optional[str] = None

    # Predictions
    likely_outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None

    # Metadata
    model: Optional[str] = None
    cost_usd: Optional[float] = None


class HearingResponse(BaseModel):
    """Hearing summary for list views."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_id: Optional[UUID] = None
    docket_number: Optional[str] = None
    title: Optional[str] = None
    hearing_type: Optional[str] = None
    hearing_date: Optional[date] = None
    duration_seconds: Optional[int] = None
    transcript_status: Optional[str] = None
    video_url: Optional[str] = None

    # Analysis summary (if available)
    one_sentence_summary: Optional[str] = None
    utility_name: Optional[str] = None
    sector: Optional[str] = None


class HearingDetail(BaseModel):
    """Full hearing details with transcript and analysis."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    state_code: str
    docket_id: Optional[UUID] = None
    docket_number: Optional[str] = None
    title: Optional[str] = None
    hearing_type: Optional[str] = None
    hearing_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    location: Optional[str] = None

    # Media
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration_minutes: Optional[int] = None

    # Transcript
    full_text: Optional[str] = None
    word_count: Optional[int] = None
    transcript_status: Optional[str] = None

    # Processing info
    whisper_model: Optional[str] = None
    processing_cost_usd: Optional[float] = None
    processed_at: Optional[datetime] = None

    # Related data
    segments: Optional[List[TranscriptSegmentResponse]] = None
    analysis: Optional[AnalysisResponse] = None

    # Florida-specific (optional)
    youtube_video_id: Optional[str] = None
    youtube_url: Optional[str] = None


class HearingListResponse(BaseModel):
    """Paginated hearing list response."""
    items: List[HearingResponse]
    total: int
    limit: int
    offset: int
