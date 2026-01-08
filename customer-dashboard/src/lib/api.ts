/**
 * API client for PSC Hearing Intelligence backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Types
export interface State {
  code: string
  name: string
  commission_name: string | null
  hearing_count: number
  docket_format?: string | null
}

export interface HearingListItem {
  id: string  // UUID
  state_code: string
  title: string | null
  hearing_date: string | null
  hearing_type: string | null
  docket_number: string | null
  duration_seconds: number | null
  transcript_status: string | null
  video_url: string | null
  // Analysis fields (if available)
  one_sentence_summary?: string | null
  utility_name?: string | null
  sector?: string | null
}

export interface HearingDetail extends HearingListItem {
  docket_id: string | null
  scheduled_time: string | null
  location: string | null
  audio_url: string | null
  duration_minutes: number | null
  full_text: string | null
  word_count: number | null
  whisper_model: string | null
  processing_cost_usd: number | null
  processed_at: string | null
  segments: Segment[] | null
  analysis: Analysis | null
  youtube_video_id?: string | null
  youtube_url?: string | null
}

export interface Analysis {
  id: string
  summary: string | null
  one_sentence_summary: string | null
  hearing_type: string | null
  utility_name: string | null
  sector: string | null
  participants: Participant[] | null
  issues: Issue[] | null
  topics: Topic[] | null
  commitments: Commitment[] | null
  vulnerabilities: string[] | null
  commissioner_concerns: CommissionerConcern[] | null
  risk_factors: string[] | null
  action_items: string[] | null
  quotes: Quote[] | null
  commissioner_mood: string | null
  public_comments: string | null
  public_sentiment: string | null
  likely_outcome: string | null
  outcome_confidence: number | null
  model: string | null
  cost_usd: number | null
}

export interface Participant {
  name: string
  role: string
  affiliation?: string
}

export interface Issue {
  issue: string
  description: string
  stance_by_party?: Record<string, string>
}

export interface Topic {
  name: string
  relevance: string
  sentiment: string
  context: string
}

export interface Commitment {
  commitment: string
  by_whom?: string
  context: string
  binding?: boolean
}

export interface CommissionerConcern {
  commissioner: string
  concern: string
  severity?: string
}

export interface Quote {
  quote: string
  speaker: string
  timestamp?: number
  significance: string
}

export interface Segment {
  id: string
  segment_index: number
  start_time: number | null
  end_time: number | null
  text: string
  speaker_label: string | null
  speaker_name: string | null
  speaker_role: string | null
  timestamp_display: string | null
}

export interface SearchResult {
  hearing_id: string
  hearing_title: string
  state_code: string
  hearing_date: string | null
  hearing_type: string | null
  text: string
  snippet: string | null
  docket_number: string | null
}

export interface SearchResponse {
  results: SearchResult[]
  total: number
  limit: number
  offset: number
}

export interface Stats {
  total_states: number
  total_hearings: number
  total_segments: number
  total_hours: number
  hearings_by_status: Record<string, number>
  hearings_by_state: Record<string, number>
  total_transcription_cost: number
  total_analysis_cost: number
  total_cost: number
  hearings_last_24h: number
  hearings_last_7d: number
}

export interface DocketListItem {
  id: string
  docket_number: string
  state_code: string
  title: string | null
  status: string | null
  docket_type: string | null
  filed_date: string | null
  closed_date: string | null
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

// API Functions
async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }

  return res.json()
}

// States
export async function getStates(): Promise<State[]> {
  return fetchAPI<State[]>('/api/states')
}

export async function getState(stateCode: string): Promise<State> {
  return fetchAPI<State>(`/api/states/${stateCode}`)
}

// Hearings
export async function getHearings(params?: {
  state_code?: string
  status?: string
  docket_number?: string
  hearing_type?: string
  utility?: string
  sector?: string
  has_transcript?: boolean
  has_analysis?: boolean
  limit?: number
  offset?: number
}): Promise<PaginatedResponse<HearingListItem>> {
  const searchParams = new URLSearchParams()
  if (params?.state_code) searchParams.set('state_code', params.state_code)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.docket_number) searchParams.set('docket_number', params.docket_number)
  if (params?.hearing_type) searchParams.set('hearing_type', params.hearing_type)
  if (params?.utility) searchParams.set('utility', params.utility)
  if (params?.sector) searchParams.set('sector', params.sector)
  if (params?.has_transcript !== undefined) searchParams.set('has_transcript', params.has_transcript.toString())
  if (params?.has_analysis !== undefined) searchParams.set('has_analysis', params.has_analysis.toString())
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI<PaginatedResponse<HearingListItem>>(`/api/hearings${query}`)
}

export async function getHearing(hearingId: string): Promise<HearingDetail> {
  return fetchAPI<HearingDetail>(`/api/hearings/${hearingId}?include_segments=true`)
}

export async function getHearingSegments(
  hearingId: string,
  params?: {
    speaker?: string
    search?: string
    limit?: number
    offset?: number
  }
): Promise<PaginatedResponse<Segment>> {
  const searchParams = new URLSearchParams()
  if (params?.speaker) searchParams.set('speaker', params.speaker)
  if (params?.search) searchParams.set('search', params.search)
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI<PaginatedResponse<Segment>>(`/api/hearings/${hearingId}/segments${query}`)
}

export async function getHearingStatuses(): Promise<Array<{ status: string; count: number }>> {
  return fetchAPI('/api/hearings/statuses')
}

// Dockets
export async function getDockets(params?: {
  state_code?: string
  status?: string
  docket_type?: string
  limit?: number
  offset?: number
}): Promise<PaginatedResponse<DocketListItem>> {
  const searchParams = new URLSearchParams()
  if (params?.state_code) searchParams.set('state_code', params.state_code)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.docket_type) searchParams.set('docket_type', params.docket_type)
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI<PaginatedResponse<DocketListItem>>(`/api/dockets${query}`)
}

export async function getDocket(docketId: string): Promise<DocketListItem & { documents: any[]; hearings: any[] }> {
  return fetchAPI(`/api/dockets/${docketId}`)
}

export async function getDocketByNumber(docketNumber: string, stateCode?: string): Promise<DocketListItem> {
  const query = stateCode ? `?state_code=${stateCode}` : ''
  return fetchAPI(`/api/dockets/by-number/${encodeURIComponent(docketNumber)}${query}`)
}

// Search
export async function search(params: {
  query: string
  state_code?: string
  docket_number?: string
  date_from?: string
  date_to?: string
  hearing_type?: string
  limit?: number
  offset?: number
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams()
  searchParams.set('query', params.query)
  if (params.state_code) searchParams.set('state_code', params.state_code)
  if (params.docket_number) searchParams.set('docket_number', params.docket_number)
  if (params.date_from) searchParams.set('date_from', params.date_from)
  if (params.date_to) searchParams.set('date_to', params.date_to)
  if (params.hearing_type) searchParams.set('hearing_type', params.hearing_type)
  if (params.limit) searchParams.set('limit', params.limit.toString())
  if (params.offset) searchParams.set('offset', params.offset.toString())

  return fetchAPI<SearchResponse>(`/api/search?${searchParams.toString()}`)
}

export async function getSearchFacets(stateCode?: string): Promise<{
  hearing_types: Array<{ value: string; count: number }>
  utilities: Array<{ value: string; count: number }>
  sectors: Array<{ value: string; count: number }>
}> {
  const query = stateCode ? `?state_code=${stateCode}` : ''
  return fetchAPI(`/api/search/facets${query}`)
}

// Stats
export async function getStats(): Promise<Stats> {
  return fetchAPI<Stats>('/api/stats')
}

export async function getUtilities(): Promise<Array<{ utility_name: string; count: number }>> {
  return fetchAPI('/api/stats/utilities')
}

export async function getHearingTypes(): Promise<Array<{ hearing_type: string; count: number }>> {
  return fetchAPI('/api/stats/hearing-types')
}

// Health check
export async function healthCheck(): Promise<{ status: string }> {
  return fetchAPI('/health')
}
