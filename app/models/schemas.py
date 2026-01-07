"""
Pydantic schemas for API request/response validation.
"""
from datetime import datetime, date
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


# ============================================================================
# STATE SCHEMAS
# ============================================================================

class StateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    commission_name: Optional[str] = None
    hearing_count: Optional[int] = None


# ============================================================================
# SOURCE SCHEMAS
# ============================================================================

class SourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state_id: int
    name: str
    source_type: str
    url: str
    enabled: bool
    check_frequency_hours: Optional[int] = 24
    created_at: Optional[datetime] = None


class SourceWithStatus(SourceResponse):
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    last_hearing_at: Optional[datetime] = None
    status: str
    error_message: Optional[str] = None


class SourceCheckRequest(BaseModel):
    source_id: int


class SourceCreateRequest(BaseModel):
    state_id: int
    name: str
    source_type: str  # 'youtube_channel', 'admin_monitor', 'rss_feed', etc.
    url: str
    check_frequency_hours: int = 24
    enabled: bool = True


# ============================================================================
# HEARING SCHEMAS
# ============================================================================

class HearingListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    title: str
    hearing_date: Optional[date] = None
    hearing_type: Optional[str] = None
    utility_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    status: str
    source_url: Optional[str] = None
    created_at: datetime

    # Pipeline summary
    pipeline_status: Optional[str] = None  # 'discovered', 'downloading', 'transcribing', 'analyzing', 'complete', 'error'


class HearingDetail(HearingListItem):
    description: Optional[str] = None
    docket_numbers: Optional[List[str]] = None
    video_url: Optional[str] = None
    source_name: Optional[str] = None

    # Analysis fields
    summary: Optional[str] = None
    one_sentence_summary: Optional[str] = None
    participants: Optional[List[Any]] = None
    issues: Optional[List[Any]] = None
    commitments: Optional[List[Any]] = None
    commissioner_concerns: Optional[List[Any]] = None
    commissioner_mood: Optional[str] = None
    likely_outcome: Optional[str] = None
    outcome_confidence: Optional[float] = None
    risk_factors: Optional[List[Any]] = None
    quotes: Optional[List[Any]] = None

    # Segments summary
    segment_count: Optional[int] = None
    word_count: Optional[int] = None


class HearingWithPipeline(HearingListItem):
    pipeline_jobs: List["PipelineJobResponse"] = []


class HearingRetryRequest(BaseModel):
    hearing_id: int
    stage: Optional[str] = None  # If None, retry all failed stages


# ============================================================================
# PIPELINE SCHEMAS
# ============================================================================

class PipelineJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    hearing_id: int
    stage: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    retry_count: int
    cost_usd: Optional[float] = None


class PipelineRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str
    sources_checked: int
    new_hearings: int
    hearings_processed: int
    errors: int
    transcription_cost_usd: float
    analysis_cost_usd: float
    total_cost_usd: float


class PipelineRunDetail(PipelineRunResponse):
    details_json: Optional[dict] = None


# ============================================================================
# SEARCH SCHEMAS
# ============================================================================

class SearchResult(BaseModel):
    segment_id: int
    hearing_id: int
    hearing_title: str
    state_code: str
    state_name: str
    text: str
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None
    source_url: Optional[str] = None
    video_url: Optional[str] = None
    timestamp_url: Optional[str] = None
    rank: Optional[float] = None
    snippet: Optional[str] = None  # Highlighted match


class SearchResponse(BaseModel):
    query: str
    results: List[SearchResult]
    total_count: int
    page: int = 1
    page_size: int = 20


# ============================================================================
# SEGMENT SCHEMAS
# ============================================================================

class SegmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    segment_index: int
    start_time: float
    end_time: float
    text: str
    speaker: Optional[str] = None
    speaker_role: Optional[str] = None


class TranscriptResponse(BaseModel):
    hearing_id: int
    hearing_title: str
    segments: List[SegmentResponse]
    word_count: Optional[int] = None


# ============================================================================
# STATS SCHEMAS
# ============================================================================

class StatsResponse(BaseModel):
    total_states: int
    total_sources: int
    total_hearings: int
    total_segments: int
    total_hours: float

    hearings_by_status: dict
    hearings_by_state: dict

    # Cost tracking
    total_transcription_cost: float
    total_analysis_cost: float
    total_cost: float

    # Recent activity
    hearings_last_24h: int
    hearings_last_7d: int


class AdminStatsResponse(StatsResponse):
    sources_healthy: int
    sources_error: int
    pipeline_jobs_pending: int
    pipeline_jobs_running: int
    pipeline_jobs_error: int

    # Cost breakdown by period
    cost_today: float
    cost_this_week: float
    cost_this_month: float


# ============================================================================
# FILTER SCHEMAS
# ============================================================================

class HearingFilters(BaseModel):
    states: Optional[List[str]] = None  # State codes
    utilities: Optional[List[str]] = None
    hearing_types: Optional[List[str]] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    status: Optional[str] = None
    search_query: Optional[str] = None
    page: int = 1
    page_size: int = 20
    sort_by: str = "hearing_date"
    sort_order: str = "desc"


# ============================================================================
# DOCKET SCHEMAS
# ============================================================================

class DocketListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    normalized_id: str
    docket_number: str
    state_code: Optional[str] = None
    state_name: Optional[str] = None
    docket_type: Optional[str] = None
    company: Optional[str] = None
    status: Optional[str] = None
    mention_count: int = 1
    first_seen_at: Optional[datetime] = None
    last_mentioned_at: Optional[datetime] = None


class DocketDetail(DocketListItem):
    title: Optional[str] = None
    description: Optional[str] = None
    current_summary: Optional[str] = None
    decision_expected: Optional[date] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    hearings: List["DocketHearingItem"] = []


class DocketHearingItem(BaseModel):
    """Hearing summary when viewing a docket."""
    model_config = ConfigDict(from_attributes=True)

    hearing_id: int
    hearing_title: str
    hearing_date: Optional[date] = None
    mention_summary: Optional[str] = None


class DocketSearchResponse(BaseModel):
    query: str
    results: List[DocketListItem]
    total_count: int
    page: int = 1
    page_size: int = 20


# ============================================================================
# WATCHLIST SCHEMAS
# ============================================================================

class LatestMention(BaseModel):
    summary: Optional[str] = None
    hearing_date: Optional[date] = None
    hearing_title: Optional[str] = None
    hearing_id: Optional[int] = None


class WatchlistDocket(DocketListItem):
    """Docket with watchlist-specific info."""
    hearing_count: int = 0
    latest_mention: Optional[LatestMention] = None


class WatchlistAddRequest(BaseModel):
    docket_id: int
    notify_on_mention: bool = True


class WatchlistResponse(BaseModel):
    dockets: List[WatchlistDocket]
    total_count: int


# ============================================================================
# ACTIVITY FEED SCHEMAS
# ============================================================================

class DocketMention(BaseModel):
    normalized_id: str
    title: Optional[str] = None
    docket_type: Optional[str] = None


class ActivityItem(BaseModel):
    date: date
    state_code: str
    state_name: str
    activity_type: str  # 'new_hearing', 'transcript_ready', 'analysis_complete'
    hearing_title: str
    hearing_id: int
    dockets_mentioned: List[DocketMention] = []


class ActivityFeedResponse(BaseModel):
    items: List[ActivityItem]
    total_count: int
    limit: int
    offset: int


# ============================================================================
# DOCKET TIMELINE SCHEMAS
# ============================================================================

class TimelineItem(BaseModel):
    hearing_id: int
    hearing_title: str
    hearing_date: Optional[date] = None
    video_url: Optional[str] = None
    mention_summary: Optional[str] = None
    timestamps: Optional[List[Any]] = None


class DocketWithTimeline(DocketDetail):
    timeline: List[TimelineItem] = []


# ============================================================================
# PIPELINE ORCHESTRATOR SCHEMAS
# ============================================================================

class PipelineStatusResponse(BaseModel):
    """Current pipeline orchestrator status."""
    status: str  # 'idle', 'running', 'paused', 'stopping'
    started_at: Optional[datetime] = None
    current_hearing_id: Optional[int] = None
    current_hearing_title: Optional[str] = None
    current_stage: Optional[str] = None
    hearings_processed: int = 0
    errors_count: int = 0
    total_cost_usd: float = 0

    # Stage counts for visualization
    stage_counts: dict = {}  # {'discovered': 45, 'transcribing': 1, 'complete': 120, ...}

    # Today's stats
    processed_today: int = 0
    cost_today: float = 0
    errors_today: int = 0


class PipelineStartRequest(BaseModel):
    """Request to start the pipeline."""
    states: Optional[List[str]] = None  # State codes to filter
    max_cost: Optional[float] = 50.0  # Max cost for this run
    only_stage: Optional[str] = None  # 'download', 'transcribe', 'analyze', 'extract'
    max_hearings: Optional[int] = None  # Max hearings to process


class RunStageRequest(BaseModel):
    """Request to run a specific stage on specific hearings."""
    stage: str  # 'download', 'transcribe', 'analyze', 'extract'
    hearing_ids: List[int]  # List of hearing IDs to process


class RunStageResponse(BaseModel):
    """Response from running a stage on hearings."""
    message: str
    stage: str
    queued_count: int
    skipped_count: int
    queued_ids: List[int]
    skipped_ids: List[int]


class PipelineActivityItem(BaseModel):
    """A single pipeline activity entry."""
    id: int
    hearing_id: int
    hearing_title: str
    state_code: Optional[str] = None
    stage: str
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cost_usd: Optional[float] = None
    error_message: Optional[str] = None


class PipelineActivityResponse(BaseModel):
    """Recent pipeline activity."""
    items: List[PipelineActivityItem]
    total_count: int


class PipelineErrorItem(BaseModel):
    """A hearing in error/failed state."""
    hearing_id: int
    hearing_title: str
    state_code: Optional[str] = None
    status: str
    last_stage: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    updated_at: Optional[datetime] = None


class PipelineErrorsResponse(BaseModel):
    """Hearings in error/failed state."""
    items: List[PipelineErrorItem]
    total_count: int


# ============================================================================
# SCHEDULE SCHEMAS
# ============================================================================

class ScheduleResponse(BaseModel):
    """Pipeline/scraper schedule."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    schedule_type: str  # 'interval', 'daily', 'cron'
    schedule_value: str  # '30m', '08:00', '0 */4 * * *'
    schedule_display: Optional[str] = None  # Human-readable: 'Every 30 minutes'
    target: str  # 'scraper', 'pipeline', 'all'
    enabled: bool
    config_json: Optional[dict] = None
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_run_status: Optional[str] = None
    last_run_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ScheduleCreateRequest(BaseModel):
    """Create a new schedule."""
    name: str
    schedule_type: str  # 'interval', 'daily', 'cron'
    schedule_value: str  # '30m', '2h', '08:00', '0 */4 * * *'
    target: str = "pipeline"  # 'scraper', 'pipeline', 'all'
    enabled: bool = True
    config: Optional[dict] = None  # {states: [], max_cost: 50, only_stage: null}


class ScheduleUpdateRequest(BaseModel):
    """Update an existing schedule."""
    name: Optional[str] = None
    schedule_type: Optional[str] = None
    schedule_value: Optional[str] = None
    target: Optional[str] = None
    enabled: Optional[bool] = None
    config: Optional[dict] = None


# ============================================================================
# SUGGESTIONS / QUICK ADD SCHEMAS
# ============================================================================

class TrendingDocket(BaseModel):
    """A trending docket suggestion for quick add."""
    id: int
    docket_id: str  # normalized_id like "FL-20250035"
    utility_name: Optional[str] = None
    mention_count: int
    state: str
    already_watching: bool = False


class UtilitySuggestion(BaseModel):
    """A utility suggestion for following all its dockets."""
    utility_name: str
    states: List[str]
    active_docket_count: int
    already_following: bool = False


class SuggestionsResponse(BaseModel):
    """Response containing suggested dockets and utilities."""
    trending: List[TrendingDocket]
    utilities: List[UtilitySuggestion]


class FollowUtilityRequest(BaseModel):
    """Request to follow all dockets for a utility."""
    utility_name: str


class FollowUtilityResponse(BaseModel):
    """Response after following a utility."""
    added_count: int
    docket_ids: List[str]


# ============================================================================
# DOCKET SOURCE / KNOWN DOCKET SCHEMAS
# ============================================================================

class DocketSourceResponse(BaseModel):
    """Docket source (PSC website) status."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    state_code: str
    state_name: str
    commission_name: Optional[str] = None
    search_url: Optional[str] = None
    scraper_type: Optional[str] = None
    enabled: bool
    last_scraped_at: Optional[datetime] = None
    last_scrape_count: Optional[int] = None
    last_error: Optional[str] = None


class KnownDocketResponse(BaseModel):
    """Known authoritative docket from PSC."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    state_code: str
    docket_number: str
    normalized_id: str
    year: Optional[int] = None
    sector: Optional[str] = None
    title: Optional[str] = None
    utility_name: Optional[str] = None
    status: Optional[str] = None
    case_type: Optional[str] = None
    source_url: Optional[str] = None


class DocketDiscoveryRequest(BaseModel):
    """Request to start docket discovery."""
    states: Optional[List[str]] = None
    year: Optional[int] = None
    limit_per_state: int = 1000


class DocketDiscoveryResponse(BaseModel):
    """Response from docket discovery."""
    total_scraped: int
    total_new: int
    total_updated: int
    by_state: dict
    errors: List[dict]


class MatchDocketsRequest(BaseModel):
    """Request to run docket matching."""
    states: Optional[List[str]] = None
    max_hearings: Optional[int] = None


class DataQualityStats(BaseModel):
    """Docket data quality statistics."""
    verified: int = 0
    likely: int = 0
    possible: int = 0
    unverified: int = 0


class ExtendedPipelineStatus(BaseModel):
    """Extended pipeline status including docket discovery."""
    pipeline_status: str

    discovery: dict  # docket_sources, docket_sources_pending, hearing_sources, known_dockets
    processing: dict  # download_pending, transcribe_pending, analyze_pending, match_pending, complete

    data_quality: DataQualityStats

    today: dict  # processed, cost, errors
