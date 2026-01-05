"""
Pydantic models for PSC Transcript Search API.
"""

from pydantic import BaseModel
from datetime import date, datetime


class HearingBase(BaseModel):
    youtube_id: str
    title: str
    description: str | None = None
    hearing_date: date | None = None
    duration_seconds: int | None = None
    docket_numbers: list[str] | None = None
    youtube_url: str
    transcript_status: str = "pending"


class HearingCreate(HearingBase):
    pass


class Hearing(HearingBase):
    id: int
    audio_path: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HearingWithCount(Hearing):
    segment_count: int = 0


class SegmentBase(BaseModel):
    segment_index: int
    start_time: float
    end_time: float
    text: str
    speaker: str | None = None
    speaker_role: str | None = None
    topics: list[str] | None = None


class SegmentCreate(SegmentBase):
    hearing_id: int
    embedding: list[float] | None = None


class Segment(SegmentBase):
    id: int
    hearing_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class SearchResult(BaseModel):
    segment_id: int
    hearing_id: int
    youtube_id: str
    hearing_title: str
    start_time: float
    end_time: float
    text: str
    speaker: str | None = None
    speaker_role: str | None = None
    youtube_url: str
    youtube_timestamp_url: str
    rank: float | None = None
    similarity: float | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]
    total_count: int
    search_type: str = "fulltext"  # "fulltext" or "semantic"


class StatsResponse(BaseModel):
    hearings: int
    segments: int
    total_hours: float
