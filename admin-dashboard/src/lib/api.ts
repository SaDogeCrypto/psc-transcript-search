/**
 * API client for PSC Hearing Intelligence Admin Backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface AdminStats {
  total_states: number;
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
}

export interface State {
  code: string;
  name: string;
  commission_name: string | null;
  hearing_count: number;
  docket_format?: string | null;
}

export interface Scraper {
  name: string;
  state_code: string;
  description?: string;
}

export interface ScraperStatus {
  state_code: string;
  scraper: string;
  status: 'idle' | 'running' | 'completed' | 'error';
  last_run?: string;
  items_found?: number;
  errors?: string[];
}

export interface Hearing {
  id: string;
  state_code: string;
  title: string | null;
  hearing_date: string | null;
  hearing_type: string | null;
  docket_number: string | null;
  duration_seconds: number | null;
  transcript_status: string | null;
  video_url: string | null;
  one_sentence_summary?: string | null;
  utility_name?: string | null;
  sector?: string | null;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface PipelineRunRequest {
  stage: string;
  state_code?: string;
  hearing_ids?: string[];
  limit?: number;
}

export interface PipelineStatus {
  status: string;
  stage: string;
  total: number;
  successful?: number;
  failed?: number;
  skipped?: number;
  total_cost_usd?: number;
  errors?: Array<{ error: string }>;
  started_at?: string;
  completed_at?: string;
}

export interface PendingHearing {
  id: string;
  title: string | null;
  docket_number: string | null;
  hearing_date: string | null;
  transcript_status: string | null;
}

export interface ScraperRunResult {
  state_code: string;
  scraper: string;
  status: string;
  items_found?: number;
  hearings_created?: number;
  errors?: string[];
}

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': process.env.NEXT_PUBLIC_ADMIN_API_KEY || 'admin-dev-key',
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

// Scrapers
export async function getScrapers(): Promise<Record<string, string[]>> {
  return fetchAPI<Record<string, string[]>>('/admin/scrapers');
}

export async function getScraperStates(): Promise<string[]> {
  return fetchAPI<string[]>('/admin/scrapers/states');
}

export async function getScraperStatus(stateCode: string, scraper: string): Promise<ScraperStatus> {
  return fetchAPI<ScraperStatus>(`/admin/scrapers/status/${stateCode}/${scraper}`);
}

export async function runScraper(stateCode: string, scraper: string, daysBack?: number): Promise<ScraperRunResult> {
  const params = new URLSearchParams();
  params.set('state_code', stateCode);
  params.set('scraper', scraper);
  if (daysBack) params.set('days_back', daysBack.toString());

  return fetchAPI<ScraperRunResult>(`/admin/scrapers/run?${params.toString()}`, {
    method: 'POST',
  });
}

export async function runScraperAsync(stateCode: string, scraper: string, daysBack?: number): Promise<{ message: string; status: string }> {
  const params = new URLSearchParams();
  params.set('state_code', stateCode);
  params.set('scraper', scraper);
  if (daysBack) params.set('days_back', daysBack.toString());

  return fetchAPI(`/admin/scrapers/run-async?${params.toString()}`, {
    method: 'POST',
  });
}

export async function getScraperStats(): Promise<{
  scrapers_by_state: Record<string, string[]>;
  total_scrapers: number;
}> {
  return fetchAPI('/admin/scrapers/stats');
}

// Hearings
export async function getHearings(params?: {
  state_code?: string;
  status?: string;
  docket_number?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<Hearing>> {
  const searchParams = new URLSearchParams();
  if (params?.state_code) searchParams.set('state_code', params.state_code);
  if (params?.status) searchParams.set('status', params.status);
  if (params?.docket_number) searchParams.set('docket_number', params.docket_number);
  if (params?.limit) searchParams.set('limit', params.limit.toString());
  if (params?.offset) searchParams.set('offset', params.offset.toString());

  const query = searchParams.toString() ? `?${searchParams.toString()}` : '';
  return fetchAPI<PaginatedResponse<Hearing>>(`/api/hearings${query}`);
}

// Pipeline
export async function runPipeline(request: PipelineRunRequest): Promise<PipelineStatus> {
  return fetchAPI<PipelineStatus>('/admin/pipeline/run', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function runPipelineSync(request: PipelineRunRequest): Promise<PipelineStatus> {
  return fetchAPI<PipelineStatus>('/admin/pipeline/run-sync', {
    method: 'POST',
    body: JSON.stringify(request),
  });
}

export async function runPipelineSingle(hearingId: string, stage: string): Promise<{
  hearing_id: string;
  success: boolean;
  skipped: boolean;
  error?: string;
  cost_usd?: number;
}> {
  return fetchAPI(`/admin/pipeline/run-single/${hearingId}?stage=${stage}`, {
    method: 'POST',
  });
}

export async function getPendingHearings(stage: string, stateCode?: string, limit?: number): Promise<{
  stage: string;
  state_code: string | null;
  count: number;
  hearings: PendingHearing[];
}> {
  const params = new URLSearchParams();
  params.set('stage', stage);
  if (stateCode) params.set('state_code', stateCode);
  if (limit) params.set('limit', limit.toString());

  return fetchAPI(`/admin/pipeline/pending?${params.toString()}`);
}

export async function getPipelineStatus(runId: string): Promise<PipelineStatus> {
  return fetchAPI<PipelineStatus>(`/admin/pipeline/status/${runId}`);
}

export async function getPipelineStats(stateCode?: string): Promise<{
  status_counts: Record<string, number>;
  total_hearings: number;
  total_processing_cost_usd: number;
}> {
  const query = stateCode ? `?state_code=${stateCode}` : '';
  return fetchAPI(`/admin/pipeline/stats${query}`);
}

// Health check
export async function healthCheck(): Promise<{ status: string }> {
  return fetchAPI('/health');
}

export async function getDetailedHealth(): Promise<{
  database: string;
  whisper_provider: string;
  registered_states: string[];
}> {
  return fetchAPI('/health/detailed');
}
