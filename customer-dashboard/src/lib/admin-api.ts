/**
 * API client for the PSC Transcript Search backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface AdminStats {
  total_states: number;
  total_sources: number;
  total_hearings: number;
  total_segments: number;
  total_hours: number;
  hearings_by_status: Record<string, number>;
  hearings_by_state: Record<string, number>;
  total_transcription_cost: number;
  total_analysis_cost: number;
  total_cost: number;
  hearings_last_24h: number;
  hearings_last_7d: number;
  sources_healthy: number;
  sources_error: number;
  pipeline_jobs_pending: number;
  pipeline_jobs_running: number;
  pipeline_jobs_error: number;
  cost_today: number;
  cost_this_week: number;
  cost_this_month: number;
}

export interface Source {
  id: number;
  state_id: number;
  state_code: string;
  state_name: string;
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
  check_frequency_hours: number;
  last_checked_at: string | null;
  last_hearing_at: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
}

export interface State {
  id: number;
  code: string;
  name: string;
  commission_name: string | null;
  hearing_count: number;
}

export interface SourceCreateData {
  state_id: number;
  name: string;
  source_type: string;
  url: string;
  check_frequency_hours?: number;
  enabled?: boolean;
}

export interface PipelineJob {
  id: number;
  hearing_id: number;
  stage: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  error_message: string | null;
  retry_count: number;
  cost_usd: number | null;
}

export interface Hearing {
  id: number;
  state_code: string;
  state_name: string;
  title: string;
  hearing_date: string | null;
  hearing_type: string | null;
  utility_name: string | null;
  duration_seconds: number | null;
  status: string;
  source_url: string | null;
  created_at: string;
  pipeline_status: string;
  pipeline_jobs: PipelineJob[];
}

export interface PipelineRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  sources_checked: number;
  new_hearings: number;
  hearings_processed: number;
  errors: number;
  transcription_cost_usd: number;
  analysis_cost_usd: number;
  total_cost_usd: number;
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }

  return res.json();
}

// Admin Stats
export async function getAdminStats(): Promise<AdminStats> {
  return fetchAPI<AdminStats>('/admin/stats');
}

// States
export async function getStates(): Promise<State[]> {
  return fetchAPI<State[]>('/admin/states');
}

// Sources
export async function getSources(state?: string, status?: string): Promise<Source[]> {
  const params = new URLSearchParams();
  if (state) params.set('state', state);
  if (status) params.set('status', status);
  const query = params.toString() ? `?${params.toString()}` : '';
  return fetchAPI<Source[]>(`/admin/sources${query}`);
}

export async function createSource(data: SourceCreateData): Promise<Source> {
  return fetchAPI<Source>('/admin/sources', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function deleteSource(sourceId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/sources/${sourceId}`, { method: 'DELETE' });
}

export async function triggerSourceCheck(sourceId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/sources/${sourceId}/check`, { method: 'POST' });
}

export async function toggleSource(sourceId: number): Promise<{ message: string; enabled: boolean }> {
  return fetchAPI(`/admin/sources/${sourceId}/toggle`, { method: 'PATCH' });
}

// Hearings
export async function getHearings(params?: {
  states?: string;
  status?: string;
  pipeline_status?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}): Promise<Hearing[]> {
  const searchParams = new URLSearchParams();
  if (params?.states) searchParams.set('states', params.states);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.pipeline_status) searchParams.set('pipeline_status', params.pipeline_status);
  if (params?.date_from) searchParams.set('date_from', params.date_from);
  if (params?.date_to) searchParams.set('date_to', params.date_to);
  if (params?.page) searchParams.set('page', params.page.toString());
  if (params?.page_size) searchParams.set('page_size', params.page_size.toString());
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchAPI<Hearing[]>(`/admin/hearings${query}`);
}

export async function retryHearing(hearingId: number, stage?: string): Promise<{ message: string }> {
  const params = stage ? `?stage=${stage}` : '';
  return fetchAPI(`/admin/hearings/${hearingId}/retry${params}`, { method: 'POST' });
}

export async function cancelHearing(hearingId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/hearings/${hearingId}/cancel`, { method: 'POST' });
}

// Pipeline Runs
export async function getPipelineRuns(limit: number = 30): Promise<PipelineRun[]> {
  return fetchAPI<PipelineRun[]>(`/admin/runs?limit=${limit}`);
}

// Scraper Control
export interface ScraperError {
  timestamp: string;
  source: string;
  error: string;
}

export interface ScraperResults {
  sources_scraped: number;
  items_found: number;
  new_hearings: number;
  existing_hearings: number;
  errors: number;
}

export interface ScraperProgress {
  status: 'idle' | 'running' | 'stopping' | 'completed' | 'error';
  started_at: string | null;
  finished_at: string | null;
  current_scraper_type: string | null;
  current_source_name: string | null;
  current_source_index: number;
  total_sources: number;
  sources_completed: number;
  items_found: number;
  new_hearings: number;
  existing_hearings: number;
  errors: ScraperError[];
  error_count: number;
  scraper_results: Record<string, ScraperResults>;
}

export async function getScraperStatus(): Promise<ScraperProgress> {
  return fetchAPI<ScraperProgress>('/admin/scraper/status');
}

export async function startScraper(params?: {
  scraper_types?: string;
  state?: string;
  dry_run?: boolean;
}): Promise<{ message: string; status: string }> {
  const searchParams = new URLSearchParams();
  if (params?.scraper_types) searchParams.set('scraper_types', params.scraper_types);
  if (params?.state) searchParams.set('state', params.state);
  if (params?.dry_run) searchParams.set('dry_run', 'true');
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchAPI(`/admin/scraper/start${query}`, { method: 'POST' });
}

export async function stopScraper(): Promise<{ message: string; status: string }> {
  return fetchAPI('/admin/scraper/stop', { method: 'POST' });
}

// =============================================================================
// PIPELINE ORCHESTRATOR
// =============================================================================

export interface PipelineStatus {
  status: string;
  started_at: string | null;
  current_hearing_id: number | null;
  current_hearing_title: string | null;
  current_stage: string | null;
  hearings_processed: number;
  errors_count: number;
  total_cost_usd: number;
  stage_counts: Record<string, number>;
  processed_today: number;
  cost_today: number;
  errors_today: number;
}

export interface PipelineStartRequest {
  states?: string[];
  only_stage?: string;
  max_cost?: number;
  max_hearings?: number;
}

export interface PipelineActivityItem {
  id: number;
  hearing_id: number;
  hearing_title: string;
  state_code: string | null;
  stage: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  cost_usd: number | null;
  error_message: string | null;
}

export interface PipelineErrorItem {
  hearing_id: number;
  hearing_title: string;
  state_code: string | null;
  status: string;
  last_stage: string | null;
  error_message: string | null;
  retry_count: number;
  updated_at: string | null;
}

export interface Schedule {
  id: number;
  name: string;
  schedule_type: string;
  schedule_value: string;
  schedule_display: string | null;
  target: string;
  enabled: boolean;
  config_json: Record<string, unknown>;
  last_run_at: string | null;
  next_run_at: string | null;
  last_run_status: string | null;
  last_run_error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ScheduleCreateRequest {
  name: string;
  schedule_type: string;
  schedule_value: string;
  target: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

export interface ScheduleUpdateRequest {
  name?: string;
  schedule_type?: string;
  schedule_value?: string;
  target?: string;
  enabled?: boolean;
  config?: Record<string, unknown>;
}

// Pipeline Status & Control
export async function getPipelineStatus(): Promise<PipelineStatus> {
  return fetchAPI<PipelineStatus>('/admin/pipeline/status');
}

export async function startPipeline(request?: PipelineStartRequest): Promise<{ message: string; config: Record<string, unknown> }> {
  return fetchAPI('/admin/pipeline/start', {
    method: 'POST',
    body: JSON.stringify(request || {}),
  });
}

export async function stopPipeline(): Promise<{ message: string }> {
  return fetchAPI('/admin/pipeline/stop', { method: 'POST' });
}

export async function pausePipeline(): Promise<{ message: string }> {
  return fetchAPI('/admin/pipeline/pause', { method: 'POST' });
}

export async function resumePipeline(): Promise<{ message: string }> {
  return fetchAPI('/admin/pipeline/resume', { method: 'POST' });
}

// Pipeline Activity & Errors
export async function getPipelineActivity(limit?: number, stage?: string): Promise<{ items: PipelineActivityItem[]; total_count: number }> {
  const params = new URLSearchParams();
  if (limit) params.set('limit', limit.toString());
  if (stage) params.set('stage', stage);
  const query = params.toString() ? `?${params.toString()}` : '';
  return fetchAPI(`/admin/pipeline/activity${query}`);
}

export async function getPipelineErrors(limit?: number): Promise<{ items: PipelineErrorItem[]; total_count: number }> {
  const params = limit ? `?limit=${limit}` : '';
  return fetchAPI(`/admin/pipeline/errors${params}`);
}

export async function retryPipelineHearing(hearingId: number, fromStage?: string): Promise<{ message: string }> {
  const params = fromStage ? `?from_stage=${fromStage}` : '';
  return fetchAPI(`/admin/pipeline/hearings/${hearingId}/retry${params}`, { method: 'POST' });
}

export async function skipPipelineHearing(hearingId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/pipeline/hearings/${hearingId}/skip`, { method: 'POST' });
}

export async function retryAllPipelineErrors(): Promise<{ message: string }> {
  return fetchAPI('/admin/pipeline/retry-all', { method: 'POST' });
}

// Schedules
export async function getSchedules(): Promise<Schedule[]> {
  return fetchAPI<Schedule[]>('/admin/pipeline/schedules');
}

export async function createSchedule(data: ScheduleCreateRequest): Promise<Schedule> {
  return fetchAPI<Schedule>('/admin/pipeline/schedules', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateSchedule(scheduleId: number, data: ScheduleUpdateRequest): Promise<Schedule> {
  return fetchAPI<Schedule>(`/admin/pipeline/schedules/${scheduleId}`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
}

export async function deleteSchedule(scheduleId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/pipeline/schedules/${scheduleId}`, { method: 'DELETE' });
}

export async function toggleSchedule(scheduleId: number): Promise<{ enabled: boolean; next_run_at: string | null }> {
  return fetchAPI(`/admin/pipeline/schedules/${scheduleId}/toggle`, { method: 'POST' });
}

export async function runScheduleNow(scheduleId: number): Promise<{ message: string }> {
  return fetchAPI(`/admin/pipeline/schedules/${scheduleId}/run-now`, { method: 'POST' });
}

// =============================================================================
// DOCKET DISCOVERY & MATCHING
// =============================================================================

export interface DocketSource {
  id: number;
  state_code: string;
  state_name: string;
  commission_name: string | null;
  search_url: string | null;
  scraper_type: string | null;
  enabled: boolean;
  last_scraped_at: string | null;
  last_scrape_count: number | null;
  last_error: string | null;
}

export interface KnownDocket {
  id: number;
  state_code: string;
  docket_number: string;
  normalized_id: string;
  year: number | null;
  sector: string | null;
  title: string | null;
  utility_name: string | null;
  status: string | null;
  case_type: string | null;
  source_url: string | null;
}

export interface DataQualityStats {
  docket_confidence: {
    verified: number;
    likely: number;
    possible: number;
    unverified: number;
  };
  known_dockets: number;
  docket_sources: {
    total: number;
    enabled: number;
  };
}

export interface ExtendedPipelineStatus {
  pipeline_status: string;
  discovery: {
    docket_sources: number;
    docket_sources_pending: number;
    hearing_sources: number;
    known_dockets: number;
  };
  processing: {
    download_pending: number;
    transcribe_pending: number;
    analyze_pending: number;
    match_pending: number;
    complete: number;
  };
  data_quality: {
    verified: number;
    likely: number;
    possible: number;
    unverified: number;
  };
  today: {
    processed: number;
    cost: number;
    errors: number;
  };
}

export interface DocketDiscoveryRequest {
  states?: string[];
  year?: number;
  limit_per_state?: number;
}

export interface DocketDiscoveryResponse {
  total_scraped: number;
  total_new: number;
  total_updated: number;
  by_state: Record<string, { scraped: number; new: number; updated: number }>;
  errors: { state: string; error: string }[];
}

export interface RunStageRequest {
  stage: string;
  hearing_ids: number[];
}

export interface RunStageResponse {
  message: string;
  stage: string;
  queued_count: number;
  skipped_count: number;
  queued_ids: number[];
  skipped_ids: number[];
}

// Docket Sources
export async function getDocketSources(): Promise<DocketSource[]> {
  return fetchAPI<DocketSource[]>('/admin/pipeline/docket-sources');
}

export async function toggleDocketSource(sourceId: number): Promise<{ enabled: boolean }> {
  return fetchAPI(`/admin/pipeline/docket-sources/${sourceId}/toggle`, { method: 'POST' });
}

// Known Dockets
export async function getKnownDockets(params?: {
  state?: string;
  sector?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<KnownDocket[]> {
  const searchParams = new URLSearchParams();
  if (params?.state) searchParams.set('state', params.state);
  if (params?.sector) searchParams.set('sector', params.sector);
  if (params?.search) searchParams.set('search', params.search);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());
  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchAPI<KnownDocket[]>(`/admin/pipeline/known-dockets${query}`);
}

// Data Quality
export async function getDataQuality(): Promise<DataQualityStats> {
  return fetchAPI<DataQualityStats>('/admin/pipeline/data-quality');
}

// Extended Status (includes docket discovery info)
export async function getExtendedPipelineStatus(): Promise<ExtendedPipelineStatus> {
  return fetchAPI<ExtendedPipelineStatus>('/admin/pipeline/extended-status');
}

// Docket Discovery
export async function startDocketDiscovery(request?: DocketDiscoveryRequest): Promise<DocketDiscoveryResponse> {
  return fetchAPI<DocketDiscoveryResponse>('/admin/pipeline/docket-discovery/start', {
    method: 'POST',
    body: JSON.stringify(request || {}),
  });
}

// Match Stage
export async function startMatchStage(request?: { states?: string[]; max_hearings?: number }): Promise<{ message: string; hearings_queued: number }> {
  return fetchAPI('/admin/pipeline/match/start', {
    method: 'POST',
    body: JSON.stringify(request || {}),
  });
}

// Run Stage on Specific Hearings
export async function runStageOnHearings(request: RunStageRequest): Promise<RunStageResponse> {
  return fetchAPI<RunStageResponse>('/admin/pipeline/run-stage', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}
