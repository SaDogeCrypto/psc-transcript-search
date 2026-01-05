/**
 * API client for CanaryScope backend
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

// Types
export interface State {
  id: number
  code: string
  name: string
  commission_name: string | null
  hearing_count: number
}

export interface HearingListItem {
  id: number
  state_code: string
  state_name: string
  title: string
  hearing_date: string | null
  hearing_type: string | null
  utility_name: string | null
  duration_seconds: number | null
  status: string
  source_url: string | null
  created_at: string
  pipeline_status: string
}

export interface HearingDetail extends HearingListItem {
  description: string | null
  docket_numbers: string[] | null
  video_url: string | null
  source_name: string | null
  summary: string | null
  one_sentence_summary: string | null
  participants: Participant[] | null
  issues: Issue[] | null
  commitments: Commitment[] | null
  commissioner_concerns: CommissionerConcern[] | null
  commissioner_mood: string | null
  likely_outcome: string | null
  outcome_confidence: number | null
  risk_factors: RiskFactor[] | null
  quotes: Quote[] | null
  segment_count: number | null
  word_count: number | null
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

export interface Commitment {
  commitment: string
  context: string
  binding?: boolean
}

export interface CommissionerConcern {
  commissioner: string
  concern: string
  severity?: string
}

export interface RiskFactor {
  factor: string
  likelihood: string
  impact: string
}

export interface Quote {
  quote: string
  speaker: string
  timestamp?: number
  significance: string
}

export interface Segment {
  id: number
  segment_index: number
  start_time: number
  end_time: number
  text: string
  speaker: string | null
  speaker_role: string | null
}

export interface TranscriptResponse {
  hearing_id: number
  total_segments: number
  segments: Segment[]
  page: number
  page_size: number
}

export interface SearchResult {
  segment_id: number
  hearing_id: number
  hearing_title: string
  state_code: string
  state_name: string
  hearing_date: string | null
  text: string
  start_time: number
  end_time: number
  speaker: string | null
  speaker_role: string | null
  source_url: string | null
  video_url: string | null
  timestamp_url: string | null
  snippet: string | null
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  total_count: number
  page: number
  page_size: number
}

export interface Stats {
  total_states: number
  total_sources: number
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
  states?: string
  utilities?: string
  hearing_types?: string
  date_from?: string
  date_to?: string
  status?: string
  search_query?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}): Promise<HearingListItem[]> {
  const searchParams = new URLSearchParams()
  if (params?.states) searchParams.set('states', params.states)
  if (params?.utilities) searchParams.set('utilities', params.utilities)
  if (params?.hearing_types) searchParams.set('hearing_types', params.hearing_types)
  if (params?.date_from) searchParams.set('date_from', params.date_from)
  if (params?.date_to) searchParams.set('date_to', params.date_to)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.search_query) searchParams.set('search_query', params.search_query)
  if (params?.page) searchParams.set('page', params.page.toString())
  if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
  if (params?.sort_by) searchParams.set('sort_by', params.sort_by)
  if (params?.sort_order) searchParams.set('sort_order', params.sort_order)

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI<HearingListItem[]>(`/api/hearings${query}`)
}

export async function getHearing(hearingId: number): Promise<HearingDetail> {
  return fetchAPI<HearingDetail>(`/api/hearings/${hearingId}`)
}

export async function getTranscript(
  hearingId: number,
  page: number = 1,
  pageSize: number = 50
): Promise<TranscriptResponse> {
  return fetchAPI<TranscriptResponse>(
    `/api/hearings/${hearingId}/transcript?page=${page}&page_size=${pageSize}`
  )
}

// Search
export async function search(params: {
  q: string
  states?: string
  date_from?: string
  date_to?: string
  page?: number
  page_size?: number
}): Promise<SearchResponse> {
  const searchParams = new URLSearchParams()
  searchParams.set('q', params.q)
  if (params.states) searchParams.set('states', params.states)
  if (params.date_from) searchParams.set('date_from', params.date_from)
  if (params.date_to) searchParams.set('date_to', params.date_to)
  if (params.page) searchParams.set('page', params.page.toString())
  if (params.page_size) searchParams.set('page_size', params.page_size.toString())

  return fetchAPI<SearchResponse>(`/api/search?${searchParams.toString()}`)
}

// Utilities and Hearing Types
export async function getUtilities(): Promise<Array<{ utility_name: string; count: number }>> {
  return fetchAPI('/api/utilities')
}

export async function getHearingTypes(): Promise<Array<{ hearing_type: string; count: number }>> {
  return fetchAPI('/api/hearing-types')
}

// Stats
export async function getStats(): Promise<Stats> {
  return fetchAPI<Stats>('/api/stats')
}

// Docket Types
export interface LatestMention {
  summary?: string
  hearing_date?: string
  hearing_title?: string
  hearing_id?: number
}

export interface DocketListItem {
  id: number
  normalized_id: string
  docket_number: string
  state_code?: string
  state_name?: string
  docket_type?: string
  company?: string
  status?: string
  mention_count: number
  first_seen_at?: string
  last_mentioned_at?: string
}

export interface WatchlistDocket extends DocketListItem {
  hearing_count: number
  latest_mention?: LatestMention
}

export interface DocketMention {
  normalized_id: string
  title?: string
  docket_type?: string
}

export interface ActivityItem {
  date: string
  state_code: string
  state_name: string
  activity_type: 'new_hearing' | 'transcript_ready' | 'analysis_complete'
  hearing_title: string
  hearing_id: number
  dockets_mentioned: DocketMention[]
}

export interface TimelineItem {
  hearing_id: number
  hearing_title: string
  hearing_date?: string
  video_url?: string
  mention_summary?: string
}

export interface DocketWithTimeline extends DocketListItem {
  title?: string
  description?: string
  current_summary?: string
  decision_expected?: string
  timeline: TimelineItem[]
}

// Watchlist
export async function getWatchlist(userId: number = 1): Promise<{ dockets: WatchlistDocket[]; total_count: number }> {
  return fetchAPI(`/api/watchlist?user_id=${userId}`)
}

export async function addToWatchlist(docketId: number, userId: number = 1): Promise<{ message: string; docket_id: number }> {
  return fetchAPI('/api/watchlist', {
    method: 'POST',
    body: JSON.stringify({ docket_id: docketId, notify_on_mention: true }),
  })
}

export async function removeFromWatchlist(docketId: number, userId: number = 1): Promise<{ message: string; docket_id: number }> {
  return fetchAPI(`/api/watchlist/${docketId}?user_id=${userId}`, {
    method: 'DELETE',
  })
}

// Activity Feed
export async function getActivityFeed(params?: {
  states?: string
  limit?: number
  offset?: number
}): Promise<{ items: ActivityItem[]; total_count: number; limit: number; offset: number }> {
  const searchParams = new URLSearchParams()
  if (params?.states) searchParams.set('states', params.states)
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI(`/api/activity${query}`)
}

// Dockets
export async function getDockets(params?: {
  states?: string
  docket_type?: string
  company?: string
  status?: string
  page?: number
  page_size?: number
  sort_by?: string
  sort_order?: 'asc' | 'desc'
}): Promise<DocketListItem[]> {
  const searchParams = new URLSearchParams()
  if (params?.states) searchParams.set('states', params.states)
  if (params?.docket_type) searchParams.set('docket_type', params.docket_type)
  if (params?.company) searchParams.set('company', params.company)
  if (params?.status) searchParams.set('status', params.status)
  if (params?.page) searchParams.set('page', params.page.toString())
  if (params?.page_size) searchParams.set('page_size', params.page_size.toString())
  if (params?.sort_by) searchParams.set('sort_by', params.sort_by)
  if (params?.sort_order) searchParams.set('sort_order', params.sort_order)

  const query = searchParams.toString() ? `?${searchParams.toString()}` : ''
  return fetchAPI(`/api/dockets${query}`)
}

export async function searchDockets(q: string, states?: string): Promise<{ results: DocketListItem[]; total_count: number }> {
  const searchParams = new URLSearchParams()
  searchParams.set('q', q)
  if (states) searchParams.set('states', states)

  return fetchAPI(`/api/dockets/search?${searchParams.toString()}`)
}

export async function getDocketByNormalizedId(normalizedId: string): Promise<DocketWithTimeline> {
  return fetchAPI(`/api/dockets/by-normalized-id/${normalizedId}`)
}
