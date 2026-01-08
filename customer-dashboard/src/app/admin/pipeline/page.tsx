'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  Play,
  Square,
  RefreshCw,
  Search,
  CheckCircle2,
  CheckCircle,
  XCircle,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Loader2,
  X,
  RotateCcw,
  SkipForward,
  Clock,
  Activity,
  Eye,
  ExternalLink,
  ArrowUpDown,
  Database,
  Shield,
  Link,
  FileSearch,
  ClipboardCheck,
} from 'lucide-react';
import { PageLayout } from '../components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface PipelineStatus {
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

interface State {
  code: string;
  name: string;
  hearing_count: number;
}

interface StageHearing {
  id: number;
  title: string;
  state_code: string;
  hearing_date: string | null;
  created_at: string | null;
  duration_seconds: number | null;
}

type SortField = 'hearing_date' | 'created_at' | 'title' | 'state_code' | 'duration_seconds';
type SortDirection = 'asc' | 'desc';

interface Source {
  id: number;
  name: string;
  source_type: string;
  url: string;
  state_code: string;
  state_name: string;
  status: string;
  enabled: boolean;
}

interface PipelineError {
  hearing_id: number;
  hearing_title: string;
  state_code: string;
  status: string;
  last_stage: string | null;
  error_message: string | null;
  retry_count: number;
  updated_at: string;
}

interface ActivityItem {
  id: number;
  hearing_id: number;
  hearing_title: string;
  state_code: string;
  stage: string;
  status: string;
  started_at: string;
  completed_at: string;
  cost_usd: number | null;
  error_message: string | null;
}

interface ScraperProgress {
  status: string;
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
  errors: string[];
}

interface HearingDetails {
  id: number;
  title: string;
  state_code: string | null;
  state_name: string | null;
  hearing_date: string | null;
  status: string;
  video_url: string | null;
  created_at: string;
  updated_at: string;
  processing_cost_usd: number;
  jobs: {
    id: number;
    stage: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    cost_usd: number | null;
    error_message: string | null;
    retry_count: number;
  }[];
  transcript: {
    id: number;
    word_count: number;
    cost_usd: number | null;
    preview: string | null;
  } | null;
  analysis: {
    id: number;
    summary: string | null;
    one_sentence_summary: string | null;
    hearing_type: string | null;
    utility_name: string | null;
    issues: unknown[] | null;
    commissioner_mood: string | null;
    likely_outcome: string | null;
    cost_usd: number | null;
  } | null;
  dockets: {
    id: number;
    docket_number: string;
    normalized_id: string;
    company: string | null;
    title: string | null;
    status: string | null;
  }[];
}

interface DocketSource {
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

// Docket Discovery stage types
interface DocketScraperInfo {
  state_code: string;
  state_name: string;
  has_batch: boolean;
  has_individual: boolean;
  last_scraped: string | null;
  docket_count: number;
  enabled: boolean;
}

interface DocketDiscoveryStats {
  known_dockets_count: number;
  sources_enabled: number;
  sources_due: number;
  last_discovery_run: string | null;
  batch_states: number;
  individual_states: number;
}

interface DocketVerifyResult {
  found: boolean;
  docket_number: string;
  state_code: string;
  title: string | null;
  company: string | null;
  filing_date: string | null;
  status: string | null;
  utility_type: string | null;
  docket_type: string | null;
  source_url: string | null;
  error: string | null;
  saved: boolean;
}

interface DataQuality {
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

// Review types
interface ReviewSuggestion {
  id: number;
  normalized_id?: string;
  name?: string;
  title?: string;
  utility_name?: string;
  score: number;
}

interface EntityReviewItem {
  id: number;
  entity_type: string;
  entity_id: number;
  name: string;
  role?: string;
  category?: string;
  context?: string;
  confidence: string;
  confidence_score?: number;
  match_type?: string;
  review_reason?: string;
  known_docket_id?: number;
  known_utility?: string;
  known_title?: string;
  utility_match?: boolean;
  suggestions?: ReviewSuggestion[];
}

interface HearingReviewItem {
  hearing_id: number;
  hearing_title: string;
  hearing_date?: string;
  state_code?: string;
  topics: EntityReviewItem[];
  utilities: EntityReviewItem[];
  dockets: EntityReviewItem[];
  total_entities: number;
  needs_review_count: number;
  lowest_confidence?: number;
  utility_docket_matches: number;
}

interface ReviewStats {
  total: number;
  dockets: number;
  topics: number;
  utilities: number;
  hearings: number;
}

// Stage configuration
// Flow: docket_discovery -> discover -> download -> transcribe -> analyze -> review -> extract -> complete
// Note: Analyze extracts topics/utilities via LLM, SmartExtract finds dockets via regex.
//       Review is a manual step to verify entities before final extraction.
const STAGES = [
  { key: 'docket_discovery', label: 'Dockets', pendingStatus: 'known_dockets', action: 'discover_dockets', description: 'Scrape PSC websites for authoritative docket data', isSpecial: true },
  { key: 'discover', label: 'Discover', pendingStatus: 'discovered', action: 'scan', description: 'Scan YouTube channels and other sources for new PSC hearing videos' },
  { key: 'download', label: 'Download', pendingStatus: 'discovered', action: 'download', description: 'Download audio from video sources using yt-dlp' },
  { key: 'transcribe', label: 'Transcribe', pendingStatus: 'downloaded', action: 'transcribe', description: 'Convert audio to text using Groq Whisper ($0.04/hour)' },
  { key: 'analyze', label: 'Analyze', pendingStatus: 'transcribed', action: 'analyze', description: 'Extract topics & utilities via LLM, find dockets via regex pattern matching' },
  { key: 'review', label: 'Review', pendingStatus: 'review', action: 'review', description: 'Verify extracted entities before proceeding to final extraction', isManual: true },
  { key: 'extract', label: 'Extract', pendingStatus: 'ready_for_extract', action: 'extract', description: 'Generate vector embeddings for semantic search (optional)' },
];

export default function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Run options
  const [selectedStates, setSelectedStates] = useState<Set<string>>(new Set());
  const [costLimit, setCostLimit] = useState<string>('50');

  // Expanded stage panel
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [stageHearings, setStageHearings] = useState<StageHearing[]>([]);
  const [stageHearingsLoading, setStageHearingsLoading] = useState(false);
  const [selectedHearings, setSelectedHearings] = useState<Set<number>>(new Set());
  const [stageStateFilter, setStageStateFilter] = useState<string>('');

  // Sorting for stage hearings
  const [sortField, setSortField] = useState<SortField>('hearing_date');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Sources for Discover stage
  const [sources, setSources] = useState<Source[]>([]);
  const [sourcesLoading, setSourcesLoading] = useState(false);
  const [selectedSources, setSelectedSources] = useState<Set<number>>(new Set());

  // Activity and Errors
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [errors, setErrors] = useState<PipelineError[]>([]);
  const [showActivity, setShowActivity] = useState(false);
  const [showErrors, setShowErrors] = useState(false);

  // Scraper progress
  const [scraperProgress, setScraperProgress] = useState<ScraperProgress | null>(null);

  // Hearing detail modal
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailHearing, setDetailHearing] = useState<HearingDetails | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Docket discovery (legacy)
  const [docketSources, setDocketSources] = useState<DocketSource[]>([]);
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null);
  const [showDocketSources, setShowDocketSources] = useState(false);
  const [discoveryRunning, setDiscoveryRunning] = useState(false);

  // Docket Discovery stage (new)
  const [docketScrapers, setDocketScrapers] = useState<DocketScraperInfo[]>([]);
  const [docketDiscoveryStats, setDocketDiscoveryStats] = useState<DocketDiscoveryStats | null>(null);
  const [selectedDocketStates, setSelectedDocketStates] = useState<Set<string>>(new Set());
  const [individualDocketState, setIndividualDocketState] = useState<string>('');
  const [individualDocketNumber, setIndividualDocketNumber] = useState<string>('');
  const [verifyingDocket, setVerifyingDocket] = useState(false);
  const [lastVerifyResult, setLastVerifyResult] = useState<DocketVerifyResult | null>(null);

  // Review section
  const [reviewStats, setReviewStats] = useState<ReviewStats | null>(null);
  const [reviewItems, setReviewItems] = useState<HearingReviewItem[]>([]);
  const [showReview, setShowReview] = useState(true);
  const [reviewLoading, setReviewLoading] = useState(false);
  const [bulkProcessing, setBulkProcessing] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    try {
      const [statusRes, statesRes, activityRes, errorsRes] = await Promise.all([
        fetch(`${API_URL}/admin/pipeline/status`),
        fetch(`${API_URL}/admin/states`),
        fetch(`${API_URL}/admin/pipeline/activity?limit=20`),
        fetch(`${API_URL}/admin/pipeline/errors?limit=20`),
      ]);

      if (!statusRes.ok) throw new Error('Failed to load pipeline status');
      if (!statesRes.ok) throw new Error('Failed to load states');

      const statusData = await statusRes.json();
      const statesData = await statesRes.json();

      setStatus(statusData);
      setStates(statesData.filter((s: State) => s.hearing_count > 0));

      if (activityRes.ok) {
        const activityData = await activityRes.json();
        setActivity(activityData.items || []);
      }

      if (errorsRes.ok) {
        const errorsData = await errorsRes.json();
        setErrors(errorsData.items || []);
      }

      // Fetch scraper status separately (may not be available in all deployments)
      try {
        const scraperRes = await fetch(`${API_URL}/admin/scraper/status`);
        if (scraperRes.ok) {
          const scraperData = await scraperRes.json();
          setScraperProgress(scraperData);
        } else {
          setScraperProgress(null);
        }
      } catch {
        // Scraper not available - ignore
        setScraperProgress(null);
      }

      // Fetch docket sources and data quality
      try {
        const [sourcesRes, qualityRes, docketStatsRes] = await Promise.all([
          fetch(`${API_URL}/admin/pipeline/docket-sources`),
          fetch(`${API_URL}/admin/pipeline/data-quality`),
          fetch(`${API_URL}/admin/pipeline/docket-discovery/stats`),
        ]);
        if (sourcesRes.ok) {
          const sourcesData = await sourcesRes.json();
          setDocketSources(sourcesData);
        }
        if (qualityRes.ok) {
          const qualityData = await qualityRes.json();
          setDataQuality(qualityData);
        }
        if (docketStatsRes.ok) {
          const docketStatsData = await docketStatsRes.json();
          setDocketDiscoveryStats(docketStatsData);
        }
      } catch {
        // Docket data not available - ignore
      }

      // Load review data
      try {
        const [statsRes, hearingsRes] = await Promise.all([
          fetch(`${API_URL}/admin/review/stats`),
          fetch(`${API_URL}/admin/review/hearings?limit=10`),
        ]);
        if (statsRes.ok) {
          setReviewStats(await statsRes.json());
        }
        if (hearingsRes.ok) {
          setReviewItems(await hearingsRes.json());
        }
      } catch {
        // Review data not available - ignore
      }

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadReviewData = useCallback(async () => {
    setReviewLoading(true);
    try {
      const [statsRes, hearingsRes] = await Promise.all([
        fetch(`${API_URL}/admin/review/stats`),
        fetch(`${API_URL}/admin/review/hearings?limit=20`),
      ]);
      if (statsRes.ok) {
        setReviewStats(await statsRes.json());
      }
      if (hearingsRes.ok) {
        setReviewItems(await hearingsRes.json());
      }
    } catch (err) {
      console.error('Failed to load review data:', err);
    } finally {
      setReviewLoading(false);
    }
  }, []);

  const handleBulkApprove = async (hearingId: number, action: string, threshold?: number) => {
    setBulkProcessing(hearingId);
    try {
      const res = await fetch(`${API_URL}/admin/review/hearings/${hearingId}/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          confidence_threshold: threshold || 80,
        }),
      });
      if (!res.ok) throw new Error('Bulk action failed');
      // Reload the review data
      await loadReviewData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk action failed');
    } finally {
      setBulkProcessing(null);
    }
  };

  const handleEntityAction = async (entityType: string, entityId: number, action: 'approve' | 'reject', hearingId: number, docketId?: number) => {
    try {
      // Map entity type to API endpoint
      // Dockets use composite key: hearing_docket/{hearing_id}/{docket_id}
      let url: string;
      if (entityType === 'docket') {
        url = `${API_URL}/admin/review/hearing_docket/${hearingId}/${docketId || entityId}`;
      } else {
        const endpoint = entityType === 'topic' ? 'topic' : 'utility';
        url = `${API_URL}/admin/review/${endpoint}/${entityId}`;
      }

      const res = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          notes: action === 'approve' ? 'Approved via pipeline review' : 'Rejected via pipeline review',
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || `Failed to ${action} ${entityType}`);
      }

      // Reload the review data to reflect changes
      await loadReviewData();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} ${entityType}`);
    }
  };

  const handleLinkDocket = async (hearingId: number, docketId: number, knownDocketId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/review/hearing_docket/${hearingId}/${docketId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action: 'link',
          correct_entity_id: knownDocketId,
          notes: 'Linked via pipeline review',
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to link docket');
      }

      // Reload the review data to reflect changes
      await loadReviewData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to link docket');
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  const runStage = async (stage: string) => {
    // Check if pipeline is running before attempting
    if (status?.status === 'running') {
      setError('Pipeline is currently running. Please wait for it to complete or stop it first.');
      return;
    }

    setActionLoading(stage);
    try {
      const body: Record<string, unknown> = {
        only_stage: stage,
      };
      if (selectedStates.size > 0) {
        body.states = Array.from(selectedStates);
      }
      if (costLimit) {
        body.max_cost = parseFloat(costLimit);
      }

      const res = await fetch(`${API_URL}/admin/pipeline/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start stage');
      }

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run stage');
    } finally {
      setActionLoading(null);
    }
  };

  const runScan = async () => {
    setActionLoading('scan');
    try {
      const params = new URLSearchParams();
      if (selectedStates.size > 0) {
        params.set('state', Array.from(selectedStates)[0]); // Scraper takes single state
      }

      const res = await fetch(`${API_URL}/admin/scraper/start?${params}`, {
        method: 'POST',
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start scan');
      }

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run scan');
    } finally {
      setActionLoading(null);
    }
  };

  const runFullPipeline = async () => {
    setActionLoading('full');
    try {
      const body: Record<string, unknown> = {};
      if (selectedStates.size > 0) {
        body.states = Array.from(selectedStates);
      }
      if (costLimit) {
        body.max_cost = parseFloat(costLimit);
      }

      const res = await fetch(`${API_URL}/admin/pipeline/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start pipeline');
      }

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const stopPipeline = async () => {
    setActionLoading('stop');
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/stop`, {
        method: 'POST',
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to stop pipeline');
      }

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const toggleState = (code: string) => {
    const newSelected = new Set(selectedStates);
    if (newSelected.has(code)) {
      newSelected.delete(code);
    } else {
      newSelected.add(code);
    }
    setSelectedStates(newSelected);
  };

  const selectAllStates = () => {
    if (selectedStates.size === states.length) {
      setSelectedStates(new Set());
    } else {
      setSelectedStates(new Set(states.map(s => s.code)));
    }
  };

  const loadStageHearings = async (pendingStatus: string, stateFilter?: string) => {
    setStageHearingsLoading(true);
    try {
      // Map dashboard status names to Florida API status names
      const statusMap: Record<string, string> = {
        'downloaded': 'pending',      // Transcribe stage: downloaded → pending (need transcription)
        'complete': 'analyzed',       // Complete stage: complete → analyzed
      };
      const apiStatus = statusMap[pendingStatus] || pendingStatus;

      const params = new URLSearchParams({
        status: apiStatus,
        page_size: '500',
      });
      if (stateFilter) {
        params.set('states', stateFilter);
      }
      const res = await fetch(`${API_URL}/admin/hearings?${params}`);
      if (!res.ok) throw new Error('Failed to load hearings');
      const data = await res.json();
      setStageHearings(data.items || []);
    } catch (err) {
      console.error('Failed to load stage hearings:', err);
      setStageHearings([]);
    } finally {
      setStageHearingsLoading(false);
    }
  };

  const loadSources = async () => {
    setSourcesLoading(true);
    try {
      const res = await fetch(`${API_URL}/admin/sources`);
      if (!res.ok) throw new Error('Failed to load sources');
      const data = await res.json();
      setSources(data.filter((s: Source) => s.enabled));
    } catch (err) {
      console.error('Failed to load sources:', err);
      setSources([]);
    } finally {
      setSourcesLoading(false);
    }
  };

  const openHearingDetail = async (hearingId: number) => {
    setDetailLoading(true);
    setDetailModalOpen(true);
    setDetailHearing(null);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/details`);
      if (!res.ok) throw new Error('Failed to load hearing details');
      const data = await res.json();
      setDetailHearing(data);
    } catch (err) {
      console.error('Failed to load hearing details:', err);
      setError(err instanceof Error ? err.message : 'Failed to load hearing details');
      setDetailModalOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const closeHearingDetail = () => {
    setDetailModalOpen(false);
    setDetailHearing(null);
  };

  // Docket Discovery stage handlers
  const loadDocketScrapers = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/scrapers`);
      if (res.ok) {
        const data = await res.json();
        setDocketScrapers(data);
      }
    } catch (err) {
      console.error('Failed to load docket scrapers:', err);
    }
  };

  const loadDocketDiscoveryStats = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/stats`);
      if (res.ok) {
        const data = await res.json();
        setDocketDiscoveryStats(data);
      }
    } catch (err) {
      console.error('Failed to load docket discovery stats:', err);
    }
  };

  const toggleDocketStateSelection = (stateCode: string) => {
    const newSelected = new Set(selectedDocketStates);
    if (newSelected.has(stateCode)) {
      newSelected.delete(stateCode);
    } else {
      newSelected.add(stateCode);
    }
    setSelectedDocketStates(newSelected);
  };

  const selectAllDocketStates = (batchOnly: boolean = false) => {
    const eligibleStates = docketScrapers.filter(s => batchOnly ? s.has_batch : true);
    if (selectedDocketStates.size === eligibleStates.length) {
      setSelectedDocketStates(new Set());
    } else {
      setSelectedDocketStates(new Set(eligibleStates.map(s => s.state_code)));
    }
  };

  const runBatchDocketDiscovery = async () => {
    if (selectedDocketStates.size === 0) return;
    setDiscoveryRunning(true);
    try {
      const states = Array.from(selectedDocketStates).join(',');
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/start?states=${states}`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start discovery');
      }
      // Refresh stats after starting
      setTimeout(() => {
        loadDocketDiscoveryStats();
        setDiscoveryRunning(false);
      }, 2000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start discovery');
      setDiscoveryRunning(false);
    }
  };

  const verifyIndividualDocket = async () => {
    if (!individualDocketState || !individualDocketNumber.trim()) return;
    setVerifyingDocket(true);
    setLastVerifyResult(null);
    try {
      const res = await fetch(
        `${API_URL}/admin/pipeline/docket-discovery/verify-single?state_code=${individualDocketState}&docket_number=${encodeURIComponent(individualDocketNumber.trim())}&save=true`,
        { method: 'POST' }
      );
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Verification failed');
      }
      setLastVerifyResult(data);
      if (data.found && data.saved) {
        // Refresh stats
        loadDocketDiscoveryStats();
        setIndividualDocketNumber('');
      }
    } catch (err) {
      setLastVerifyResult({
        found: false,
        docket_number: individualDocketNumber,
        state_code: individualDocketState,
        title: null,
        company: null,
        filing_date: null,
        status: null,
        utility_type: null,
        docket_type: null,
        source_url: null,
        error: err instanceof Error ? err.message : 'Verification failed',
        saved: false,
      });
    } finally {
      setVerifyingDocket(false);
    }
  };

  const toggleStageExpand = (stageKey: string, pendingStatus: string) => {
    if (expandedStage === stageKey) {
      setExpandedStage(null);
      setStageHearings([]);
      setSelectedHearings(new Set());
      setSources([]);
      setSelectedSources(new Set());
      setStageStateFilter('');
      setSelectedDocketStates(new Set());
      setLastVerifyResult(null);
    } else {
      setExpandedStage(stageKey);
      setSelectedHearings(new Set());
      setSelectedSources(new Set());
      setStageStateFilter('');
      setSelectedDocketStates(new Set());
      setLastVerifyResult(null);
      if (stageKey === 'docket_discovery') {
        loadDocketScrapers();
        loadDocketDiscoveryStats();
      } else if (stageKey === 'discover') {
        loadSources();
      } else if (stageKey === 'review') {
        loadReviewData();
      } else {
        loadStageHearings(pendingStatus);
      }
    }
  };

  const handleStageStateFilterChange = (stateCode: string) => {
    setStageStateFilter(stateCode);
    setSelectedHearings(new Set());
    if (expandedStage === 'complete') {
      loadStageHearings('analyzed', stateCode);  // Florida API uses 'analyzed'
    } else if (expandedStage === 'skipped') {
      loadStageHearings('skipped', stateCode);
    } else {
      const stage = STAGES.find(s => s.key === expandedStage);
      if (stage) {
        loadStageHearings(stage.pendingStatus, stateCode);
      }
    }
  };

  const restoreHearing = async (hearingId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/retry`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to restore hearing');
      }
      // Remove from local state immediately
      setStageHearings(prev => prev.filter(h => h.id !== hearingId));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restore hearing');
    }
  };

  const toggleSourceSelection = (id: number) => {
    const newSelected = new Set(selectedSources);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedSources(newSelected);
  };

  const selectAllSources = () => {
    if (selectedSources.size === sources.length) {
      setSelectedSources(new Set());
    } else {
      setSelectedSources(new Set(sources.map(s => s.id)));
    }
  };

  const runSelectedSources = async () => {
    if (selectedSources.size === 0) return;

    setActionLoading('scan');
    try {
      // Get unique states from selected sources
      const selectedSourcesList = sources.filter(s => selectedSources.has(s.id));
      const uniqueStates = Array.from(new Set(selectedSourcesList.map(s => s.state_code)));

      // If only one state, pass it as filter. Otherwise scan all.
      const params = new URLSearchParams();
      if (uniqueStates.length === 1) {
        params.set('state', uniqueStates[0]);
      }

      const res = await fetch(`${API_URL}/admin/scraper/start?${params}`, {
        method: 'POST',
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start scan');
      }

      // Refresh data and close panel
      await loadData();
      setExpandedStage(null);
      setSources([]);
      setSelectedSources(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run scan');
    } finally {
      setActionLoading(null);
    }
  };

  const toggleHearingSelection = (id: number) => {
    const newSelected = new Set(selectedHearings);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedHearings(newSelected);
  };

  const selectAllHearings = () => {
    if (selectedHearings.size === stageHearings.length) {
      setSelectedHearings(new Set());
    } else {
      setSelectedHearings(new Set(stageHearings.map(h => h.id)));
    }
  };

  const runSelectedHearings = async (action: string) => {
    if (selectedHearings.size === 0) return;

    // Check if pipeline is running before attempting
    if (status?.status === 'running') {
      setError('Pipeline is currently running. Please wait for it to complete or stop it first.');
      return;
    }

    setActionLoading(action);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/run-stage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          stage: action,
          hearing_ids: Array.from(selectedHearings),
        }),
      });

      if (!res.ok) {
        const data = await res.json();
        // Provide a more user-friendly message for common errors
        if (res.status === 400 && data.detail?.includes('running')) {
          throw new Error('Pipeline is currently running. Please wait for it to complete or stop it first.');
        }
        throw new Error(data.detail || 'Failed to run stage');
      }

      // Refresh data and close panel
      await loadData();
      setExpandedStage(null);
      setStageHearings([]);
      setSelectedHearings(new Set());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run stage');
    } finally {
      setActionLoading(null);
    }
  };

  const retryHearing = async (hearingId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/retry`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to retry hearing');
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry hearing');
    }
  };

  const skipHearing = async (hearingId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/skip`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to skip hearing');
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip hearing');
    }
  };

  const dismissHearing = async (hearingId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/skip`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to dismiss hearing');
      }
      // Remove from local state immediately
      setStageHearings(prev => prev.filter(h => h.id !== hearingId));
      setSelectedHearings(prev => {
        const next = new Set(prev);
        next.delete(hearingId);
        return next;
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss hearing');
    }
  };

  const dismissSelectedHearings = async () => {
    if (selectedHearings.size === 0) return;

    setActionLoading('dismiss');
    try {
      // Dismiss all selected hearings
      const promises = Array.from(selectedHearings).map(id =>
        fetch(`${API_URL}/admin/pipeline/hearings/${id}/skip`, { method: 'POST' })
      );
      await Promise.all(promises);

      // Clear selection and refresh
      setStageHearings(prev => prev.filter(h => !selectedHearings.has(h.id)));
      setSelectedHearings(new Set());
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to dismiss hearings');
    } finally {
      setActionLoading(null);
    }
  };

  const retryAllErrors = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/retry-all`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to retry all');
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry all errors');
    }
  };

  // Docket Discovery Functions
  const startDocketDiscovery = async () => {
    setDiscoveryRunning(true);
    try {
      const enabledStates = docketSources.filter(s => s.enabled).map(s => s.state_code);
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ states: enabledStates.length > 0 ? enabledStates : undefined }),
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start discovery');
      }
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start docket discovery');
    } finally {
      setDiscoveryRunning(false);
    }
  };

  const toggleDocketSource = async (sourceId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/docket-sources/${sourceId}/toggle`, {
        method: 'POST',
      });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to toggle source');
      }
      // Refresh docket sources
      const sourcesRes = await fetch(`${API_URL}/admin/pipeline/docket-sources`);
      if (sourcesRes.ok) {
        const sourcesData = await sourcesRes.json();
        setDocketSources(sourcesData);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle docket source');
    }
  };

  const getStageCount = (pendingStatus: string) => {
    // Docket Discovery stage uses known_dockets count
    if (pendingStatus === 'known_dockets') {
      return docketDiscoveryStats?.known_dockets_count || 0;
    }
    // Review stage uses reviewStats.hearings count
    if (pendingStatus === 'review') {
      return reviewStats?.hearings || 0;
    }
    // Map Florida API's simpler status keys to expected stage keys
    // Florida returns: pending (need transcription), transcribed (need analysis), analyzed (complete)
    if (pendingStatus === 'downloaded') {
      return status?.stage_counts?.['pending'] || status?.stage_counts?.['downloaded'] || 0;
    }
    return status?.stage_counts?.[pendingStatus] || 0;
  };

  const getCompleteCount = () => {
    // Florida API uses 'analyzed' for complete hearings
    return status?.stage_counts?.['complete'] || status?.stage_counts?.['analyzed'] || 0;
  };

  const getSkippedCount = () => {
    return status?.stage_counts?.['skipped'] || 0;
  };

  // Sort hearings based on current sort settings
  const sortedStageHearings = [...stageHearings].sort((a, b) => {
    let comparison = 0;

    switch (sortField) {
      case 'hearing_date':
        const dateA = a.hearing_date ? new Date(a.hearing_date).getTime() : 0;
        const dateB = b.hearing_date ? new Date(b.hearing_date).getTime() : 0;
        comparison = dateA - dateB;
        break;
      case 'created_at':
        const createdA = a.created_at ? new Date(a.created_at).getTime() : 0;
        const createdB = b.created_at ? new Date(b.created_at).getTime() : 0;
        comparison = createdA - createdB;
        break;
      case 'title':
        comparison = (a.title || '').localeCompare(b.title || '');
        break;
      case 'state_code':
        comparison = (a.state_code || '').localeCompare(b.state_code || '');
        break;
      case 'duration_seconds':
        comparison = (a.duration_seconds || 0) - (b.duration_seconds || 0);
        break;
    }

    return sortDirection === 'desc' ? -comparison : comparison;
  });

  const handleSortChange = (field: SortField) => {
    if (field === sortField) {
      // Toggle direction if same field
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      // New field, default to descending for dates, ascending for text
      setSortField(field);
      setSortDirection(field === 'hearing_date' || field === 'created_at' || field === 'duration_seconds' ? 'desc' : 'asc');
    }
  };

  const formatDuration = (seconds: number | null): string => {
    if (!seconds) return '-';
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    if (hrs > 0) return `${hrs}h ${mins}m`;
    return `${mins}m`;
  };

  const isRunning = status?.status === 'running';
  const isPaused = status?.status === 'paused';
  const isScraperRunning = scraperProgress?.status === 'running';
  const scraperJustFinished = scraperProgress?.status === 'completed' && scraperProgress?.finished_at;

  if (loading) {
    return (
      <PageLayout activeTab="pipeline">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="pipeline">
      {/* Header */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0 }}>Pipeline</h2>
            <span
              className={`badge ${isRunning ? 'badge-success' : isPaused ? 'badge-warning' : 'badge-secondary'}`}
              style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}
            >
              {isRunning && <Loader2 size={12} className="animate-spin" />}
              {status?.status || 'idle'}
            </span>
          </div>
          <button onClick={loadData} className="btn btn-secondary" style={{ padding: '0.5rem' }}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={20} />
          <div>{error}</div>
          <button onClick={() => setError(null)} style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer' }}>&times;</button>
        </div>
      )}

      {/* Active Processing Banner */}
      {isRunning && (
        <div
          className="card"
          style={{
            marginBottom: '1rem',
            padding: '1rem 1.25rem',
            background: 'linear-gradient(90deg, var(--primary-50) 0%, var(--primary-100) 100%)',
            border: '1px solid var(--primary-200)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <Loader2 size={24} className="animate-spin" style={{ color: 'var(--primary)' }} />
            <div style={{ flex: 1 }}>
              <div style={{ fontWeight: 600, color: 'var(--gray-800)' }}>
                Processing: {status?.current_stage || 'starting'}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                {status?.current_hearing_title || 'Preparing...'}
              </div>
            </div>
            <button
              onClick={stopPipeline}
              disabled={actionLoading === 'stop'}
              className="btn btn-danger"
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.85rem' }}
            >
              {actionLoading === 'stop' ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} />}
              Stop
            </button>
          </div>
          <div
            style={{
              marginTop: '0.75rem',
              height: '4px',
              background: 'var(--primary-200)',
              borderRadius: '2px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: '30%',
                background: 'var(--primary)',
                borderRadius: '2px',
                animation: 'progress-indeterminate 1.5s ease-in-out infinite',
              }}
            />
          </div>
        </div>
      )}

      {/* Data Quality & Docket Discovery Section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
        {/* Data Quality Card */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Shield size={20} style={{ color: 'var(--primary)' }} />
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Data Quality</h3>
            </div>
          </div>
          {dataQuality ? (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
              <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--success-50)', borderRadius: '6px', border: '1px solid var(--success-200)' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success-700)' }}>
                  {dataQuality.docket_confidence.verified}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--success-600)' }}>Verified</div>
              </div>
              <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--primary-50)', borderRadius: '6px', border: '1px solid var(--primary-200)' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--primary-700)' }}>
                  {dataQuality.docket_confidence.likely}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--primary-600)' }}>Likely</div>
              </div>
              <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--warning-50)', borderRadius: '6px', border: '1px solid var(--warning-200)' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--warning-700)' }}>
                  {dataQuality.docket_confidence.possible}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--warning-600)' }}>Possible</div>
              </div>
              <div style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--gray-50)', borderRadius: '6px', border: '1px solid var(--gray-200)' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-700)' }}>
                  {dataQuality.docket_confidence.unverified}
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--gray-600)' }}>Unverified</div>
              </div>
            </div>
          ) : (
            <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--gray-500)' }}>
              Loading quality data...
            </div>
          )}
          {dataQuality && (
            <div style={{ marginTop: '1rem', display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--gray-600)' }}>
              <span><Database size={14} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />{dataQuality.known_dockets.toLocaleString()} known dockets</span>
              <span>{dataQuality.docket_sources.enabled} / {dataQuality.docket_sources.total} sources enabled</span>
            </div>
          )}
        </div>

        {/* Docket Discovery Card */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileSearch size={20} style={{ color: 'var(--primary)' }} />
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Docket Discovery</h3>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                onClick={() => setShowDocketSources(!showDocketSources)}
                className="btn btn-secondary"
                style={{ padding: '0.35rem 0.6rem', fontSize: '0.8rem' }}
              >
                {showDocketSources ? 'Hide' : 'Sources'}
              </button>
              <button
                onClick={startDocketDiscovery}
                disabled={discoveryRunning}
                className="btn btn-primary"
                style={{ padding: '0.35rem 0.6rem', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                title="Scrape docket data from PSC websites"
              >
                {discoveryRunning ? <Loader2 size={14} className="animate-spin" /> : <Play size={14} />}
                {discoveryRunning ? 'Scanning...' : 'Scan PSCs'}
              </button>
            </div>
          </div>
          <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
            Scrape authoritative docket data from PSC websites. Dockets are matched automatically during Analyze.
          </div>
          {docketSources.length > 0 && (
            <div style={{ marginTop: '0.75rem', fontSize: '0.8rem', color: 'var(--gray-500)' }}>
              {docketSources.filter(s => s.enabled).length} states enabled for discovery
            </div>
          )}
        </div>
      </div>

      {/* Docket Sources Panel (Expandable) */}
      {showDocketSources && docketSources.length > 0 && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
            <h4 style={{ margin: 0, fontSize: '0.95rem', fontWeight: 600 }}>PSC Docket Sources</h4>
            <button
              onClick={() => setShowDocketSources(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
            >
              <X size={16} color="var(--gray-500)" />
            </button>
          </div>
          <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
              <thead>
                <tr style={{ background: 'var(--gray-50)', position: 'sticky', top: 0 }}>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid var(--gray-200)' }}>State</th>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'left', borderBottom: '1px solid var(--gray-200)' }}>Commission</th>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'center', borderBottom: '1px solid var(--gray-200)' }}>Scraper</th>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'center', borderBottom: '1px solid var(--gray-200)' }}>Last Scraped</th>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'center', borderBottom: '1px solid var(--gray-200)' }}>Count</th>
                  <th style={{ padding: '0.5rem 0.75rem', textAlign: 'center', borderBottom: '1px solid var(--gray-200)' }}>Enabled</th>
                </tr>
              </thead>
              <tbody>
                {docketSources.map((source) => (
                  <tr key={source.id} style={{ borderBottom: '1px solid var(--gray-100)' }}>
                    <td style={{ padding: '0.5rem 0.75rem' }}>
                      <span className="badge badge-primary" style={{ marginRight: '0.5rem' }}>{source.state_code}</span>
                      {source.state_name}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', color: 'var(--gray-600)', fontSize: '0.8rem' }}>
                      {source.commission_name || '-'}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                      {source.scraper_type ? (
                        <span className="badge badge-info">{source.scraper_type}</span>
                      ) : (
                        <span style={{ color: 'var(--gray-400)' }}>-</span>
                      )}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center', fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                      {source.last_scraped_at ? new Date(source.last_scraped_at).toLocaleDateString() : '-'}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center', fontSize: '0.8rem' }}>
                      {source.last_scrape_count ?? '-'}
                    </td>
                    <td style={{ padding: '0.5rem 0.75rem', textAlign: 'center' }}>
                      <button
                        onClick={() => toggleDocketSource(source.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: source.scraper_type ? 'pointer' : 'not-allowed',
                          padding: '0.25rem',
                          opacity: source.scraper_type ? 1 : 0.5,
                        }}
                        disabled={!source.scraper_type}
                        title={source.scraper_type ? (source.enabled ? 'Disable' : 'Enable') : 'No scraper available'}
                      >
                        {source.enabled ? (
                          <CheckCircle2 size={18} style={{ color: 'var(--success)' }} />
                        ) : (
                          <div style={{ width: 18, height: 18, borderRadius: '50%', border: '2px solid var(--gray-300)' }} />
                        )}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {docketSources.some(s => s.last_error) && (
            <div style={{ marginTop: '0.75rem', padding: '0.5rem 0.75rem', background: 'var(--danger-50)', borderRadius: '4px', fontSize: '0.8rem', color: 'var(--danger-700)' }}>
              <AlertTriangle size={14} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
              Some sources have errors. Check logs for details.
            </div>
          )}
        </div>
      )}

      {/* Workflow Stages */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'stretch', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.5rem' }}>
          {STAGES.map((stage, idx) => {
            const count = getStageCount(stage.pendingStatus);
            const isActive = status?.current_stage === stage.key;
            const isDiscover = stage.key === 'discover';
            const isReview = stage.key === 'review';
            const isExpanded = expandedStage === stage.key;
            const canExpand = isDiscover ? states.length > 0 : count > 0;

            return (
              <div key={stage.key} style={{ display: 'flex', alignItems: 'center' }}>
                <div
                  onClick={() => canExpand && toggleStageExpand(stage.key, stage.pendingStatus)}
                  title={stage.description}
                  style={{
                    padding: '1rem',
                    borderRadius: '8px',
                    background: isExpanded ? 'var(--primary-100)' : isReview && count > 0 ? 'var(--warning-50)' : isActive ? 'var(--primary)' : 'var(--gray-50)',
                    color: isActive && !isExpanded ? 'white' : 'var(--gray-700)',
                    border: isExpanded ? '2px solid var(--primary)' : isReview && count > 0 ? '2px solid var(--warning)' : isActive ? 'none' : '1px solid var(--gray-200)',
                    minWidth: '130px',
                    textAlign: 'center',
                    cursor: canExpand ? 'pointer' : 'default',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem', fontWeight: 600, marginBottom: '0.25rem' }}>
                    {stage.label}
                    {canExpand && (
                      <ChevronDown
                        size={14}
                        style={{
                          transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                          transition: 'transform 0.15s ease',
                        }}
                      />
                    )}
                  </div>
                  <div style={{ fontSize: '2rem', fontWeight: 700, lineHeight: 1.2, color: isReview && count > 0 ? 'var(--warning)' : undefined }}>
                    {isDiscover ? states.length : count}
                  </div>
                  <div style={{ fontSize: '0.75rem', opacity: 0.8, marginBottom: '0.75rem' }}>
                    {isDiscover ? 'sources' : isReview ? 'hearings' : 'pending'}
                  </div>
                  {/* Review is manual - no Run All button */}
                  {isReview ? (
                    <div style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}>
                      <ClipboardCheck size={18} style={{ color: count > 0 ? 'var(--warning)' : 'var(--gray-400)' }} />
                    </div>
                  ) : (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        isDiscover ? runScan() : runStage(stage.action);
                      }}
                      disabled={actionLoading !== null || isRunning}
                      className="btn btn-primary"
                      style={{
                        padding: '0.4rem 0.75rem',
                        fontSize: '0.8rem',
                        width: '100%',
                        background: isActive && !isExpanded ? 'rgba(255,255,255,0.2)' : undefined,
                      }}
                    >
                      {actionLoading === stage.action || actionLoading === 'scan' && isDiscover ? (
                        <Loader2 size={14} className="animate-spin" />
                      ) : isDiscover ? (
                        <><Search size={14} /> Scan</>
                      ) : (
                        <><Play size={14} /> Run All</>
                      )}
                    </button>
                  )}
                </div>
                {idx < STAGES.length && (
                  <ChevronRight size={24} style={{ color: 'var(--gray-300)', margin: '0 0.25rem', flexShrink: 0 }} />
                )}
              </div>
            );
          })}

          {/* Complete */}
          <div
            onClick={() => {
              if (getCompleteCount() > 0) {
                if (expandedStage === 'complete') {
                  setExpandedStage(null);
                  setStageHearings([]);
                } else {
                  setExpandedStage('complete');
                  loadStageHearings('analyzed');  // Florida API uses 'analyzed' for complete
                }
              }
            }}
            title="Fully processed hearings with transcript, analysis, and verified dockets"
            style={{
              padding: '1rem',
              borderRadius: '8px',
              background: expandedStage === 'complete' ? 'var(--success)' : 'var(--success-bg)',
              border: expandedStage === 'complete' ? '2px solid var(--success)' : '1px solid var(--success)',
              minWidth: '130px',
              textAlign: 'center',
              cursor: getCompleteCount() > 0 ? 'pointer' : 'default',
              transition: 'all 0.15s ease',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem', fontWeight: 600, marginBottom: '0.25rem', color: expandedStage === 'complete' ? 'white' : 'var(--success)' }}>
              Complete
              {getCompleteCount() > 0 && (
                <ChevronDown
                  size={14}
                  style={{
                    transform: expandedStage === 'complete' ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.15s ease',
                  }}
                />
              )}
            </div>
            <div style={{ fontSize: '2rem', fontWeight: 700, lineHeight: 1.2, color: expandedStage === 'complete' ? 'white' : 'var(--success)' }}>
              {getCompleteCount()}
            </div>
            <div style={{ fontSize: '0.75rem', color: expandedStage === 'complete' ? 'rgba(255,255,255,0.9)' : 'var(--success)', marginBottom: '0.75rem' }}>
              processed
            </div>
            <div style={{ padding: '0.4rem', fontSize: '0.8rem' }}>
              <CheckCircle2 size={20} style={{ color: expandedStage === 'complete' ? 'white' : 'var(--success)' }} />
            </div>
          </div>

          {/* Skipped */}
          {getSkippedCount() > 0 && (
            <div
              onClick={() => {
                if (expandedStage === 'skipped') {
                  setExpandedStage(null);
                  setStageHearings([]);
                } else {
                  setExpandedStage('skipped');
                  loadStageHearings('skipped');
                }
              }}
              title="Hearings excluded from processing (too short, not relevant, or manually skipped)"
              style={{
                padding: '1rem',
                borderRadius: '8px',
                background: expandedStage === 'skipped' ? 'var(--gray-500)' : 'var(--gray-100)',
                border: expandedStage === 'skipped' ? '2px solid var(--gray-500)' : '1px solid var(--gray-300)',
                minWidth: '100px',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
                marginLeft: '0.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.25rem', fontWeight: 600, marginBottom: '0.25rem', color: expandedStage === 'skipped' ? 'white' : 'var(--gray-600)' }}>
                Skipped
                <ChevronDown
                  size={14}
                  style={{
                    transform: expandedStage === 'skipped' ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.15s ease',
                  }}
                />
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700, lineHeight: 1.2, color: expandedStage === 'skipped' ? 'white' : 'var(--gray-600)' }}>
                {getSkippedCount()}
              </div>
              <div style={{ fontSize: '0.75rem', color: expandedStage === 'skipped' ? 'rgba(255,255,255,0.9)' : 'var(--gray-500)', marginBottom: '0.5rem' }}>
                dismissed
              </div>
              <div style={{ padding: '0.25rem', fontSize: '0.8rem' }}>
                <SkipForward size={16} style={{ color: expandedStage === 'skipped' ? 'white' : 'var(--gray-500)' }} />
              </div>
            </div>
          )}
        </div>

        {/* Expanded Stage Panel - Docket Discovery */}
        {expandedStage === 'docket_discovery' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--gray-50)',
            borderRadius: '8px',
            border: '1px solid var(--gray-200)',
          }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 600 }}>
                  <Database size={16} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
                  Docket Discovery
                </span>
                {docketDiscoveryStats && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                    {docketDiscoveryStats.known_dockets_count} dockets • {docketDiscoveryStats.individual_states} states supported
                  </span>
                )}
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setSelectedDocketStates(new Set());
                  setLastVerifyResult(null);
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {/* Batch Discovery Section */}
            <div style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <span style={{ fontWeight: 500, fontSize: '0.875rem' }}>Batch Discovery (State Sources)</span>
                {docketScrapers.filter(s => s.has_batch).length > 0 && (
                  <button
                    onClick={() => selectAllDocketStates(true)}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                  >
                    {selectedDocketStates.size === docketScrapers.filter(s => s.has_batch).length ? 'Deselect All' : 'Select Batch States'}
                  </button>
                )}
              </div>

              <div style={{
                maxHeight: '200px',
                overflowY: 'auto',
                border: '1px solid var(--gray-200)',
                borderRadius: '6px',
                background: 'white',
              }}>
                {docketScrapers.length === 0 ? (
                  <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.875rem' }}>
                    <Loader2 size={16} className="animate-spin" style={{ display: 'inline', marginRight: '0.5rem' }} />
                    Loading state scrapers...
                  </div>
                ) : (
                  docketScrapers.map((scraper) => (
                    <label
                      key={scraper.state_code}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.75rem',
                        padding: '0.5rem 0.75rem',
                        borderBottom: '1px solid var(--gray-100)',
                        cursor: 'pointer',
                        background: selectedDocketStates.has(scraper.state_code) ? 'var(--primary-50)' : 'transparent',
                        opacity: scraper.has_batch ? 1 : 0.6,
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedDocketStates.has(scraper.state_code)}
                        onChange={() => toggleDocketStateSelection(scraper.state_code)}
                        disabled={!scraper.has_batch}
                        style={{ width: '16px', height: '16px' }}
                      />
                      <span className="badge badge-primary" style={{ flexShrink: 0, minWidth: '2rem', textAlign: 'center' }}>
                        {scraper.state_code}
                      </span>
                      <span style={{ flex: 1, fontSize: '0.875rem' }}>
                        {scraper.state_name}
                      </span>
                      <span style={{ display: 'flex', gap: '0.25rem', flexShrink: 0 }}>
                        {scraper.has_batch && (
                          <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>Batch</span>
                        )}
                        {scraper.has_individual && (
                          <span className="badge badge-info" style={{ fontSize: '0.65rem' }}>Single</span>
                        )}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', minWidth: '4rem', textAlign: 'right' }}>
                        {scraper.docket_count} dockets
                      </span>
                    </label>
                  ))
                )}
              </div>

              {selectedDocketStates.size > 0 && (
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <button
                    onClick={runBatchDocketDiscovery}
                    disabled={discoveryRunning}
                    className="btn btn-primary"
                    style={{ padding: '0.5rem 1rem' }}
                  >
                    {discoveryRunning ? (
                      <><Loader2 size={14} className="animate-spin" style={{ marginRight: '0.5rem' }} /> Discovering...</>
                    ) : (
                      <><Play size={14} style={{ marginRight: '0.5rem' }} /> Discover {selectedDocketStates.size} States</>
                    )}
                  </button>
                  <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                    Scrapes docket lists from PSC websites (may take several minutes)
                  </span>
                </div>
              )}
            </div>

            {/* Individual Docket Lookup Section */}
            <div style={{ borderTop: '1px solid var(--gray-200)', paddingTop: '1rem' }}>
              <span style={{ fontWeight: 500, fontSize: '0.875rem', display: 'block', marginBottom: '0.5rem' }}>
                <FileSearch size={14} style={{ display: 'inline', marginRight: '0.5rem', verticalAlign: 'middle' }} />
                Individual Docket Lookup
              </span>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
                <select
                  value={individualDocketState}
                  onChange={(e) => setIndividualDocketState(e.target.value)}
                  style={{
                    padding: '0.5rem',
                    borderRadius: '6px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.875rem',
                    minWidth: '150px',
                  }}
                >
                  <option value="">Select State</option>
                  {docketScrapers.filter(s => s.has_individual).map(s => (
                    <option key={s.state_code} value={s.state_code}>
                      {s.state_code} - {s.state_name}
                    </option>
                  ))}
                </select>

                <input
                  type="text"
                  placeholder="Docket number (e.g., T-21349A-25-0016)"
                  value={individualDocketNumber}
                  onChange={(e) => setIndividualDocketNumber(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && verifyIndividualDocket()}
                  style={{
                    padding: '0.5rem',
                    borderRadius: '6px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.875rem',
                    flex: 1,
                    minWidth: '200px',
                  }}
                />

                <button
                  onClick={verifyIndividualDocket}
                  disabled={verifyingDocket || !individualDocketState || !individualDocketNumber.trim()}
                  className="btn btn-primary"
                  style={{ padding: '0.5rem 1rem', whiteSpace: 'nowrap' }}
                >
                  {verifyingDocket ? (
                    <><Loader2 size={14} className="animate-spin" style={{ marginRight: '0.5rem' }} /> Verifying...</>
                  ) : (
                    <><Search size={14} style={{ marginRight: '0.5rem' }} /> Verify & Save</>
                  )}
                </button>
              </div>

              {/* Verification Result */}
              {lastVerifyResult && (
                <div style={{
                  marginTop: '0.75rem',
                  padding: '0.75rem',
                  borderRadius: '6px',
                  background: lastVerifyResult.found ? 'var(--success-bg, #f0fdf4)' : '#fef2f2',
                  border: `1px solid ${lastVerifyResult.found ? 'var(--success, #16a34a)' : '#fca5a5'}`,
                }}>
                  {lastVerifyResult.found ? (
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                        <CheckCircle size={16} style={{ color: 'var(--success, #16a34a)' }} />
                        <strong style={{ fontSize: '0.875rem' }}>
                          {lastVerifyResult.state_code}-{lastVerifyResult.docket_number}
                        </strong>
                        {lastVerifyResult.saved && (
                          <span className="badge badge-success" style={{ fontSize: '0.65rem' }}>Saved</span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-700)' }}>
                        <strong>{lastVerifyResult.company}</strong>
                        {lastVerifyResult.utility_type && (
                          <span className="badge badge-info" style={{ marginLeft: '0.5rem', fontSize: '0.65rem' }}>
                            {lastVerifyResult.utility_type}
                          </span>
                        )}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-600)', marginTop: '0.25rem' }}>
                        {lastVerifyResult.title}
                      </div>
                      {lastVerifyResult.source_url && (
                        <a
                          href={lastVerifyResult.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          style={{ fontSize: '0.75rem', color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.25rem' }}
                        >
                          <ExternalLink size={12} /> View on PSC website
                        </a>
                      )}
                    </div>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <XCircle size={16} style={{ color: '#dc2626' }} />
                      <span style={{ fontSize: '0.875rem', color: '#dc2626' }}>
                        {lastVerifyResult.error || 'Docket not found'}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Expanded Stage Panel - Sources for Discover */}
        {expandedStage === 'discover' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--gray-50)',
            borderRadius: '8px',
            border: '1px solid var(--gray-200)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 600 }}>Select sources to scan</span>
                {sources.length > 0 && (
                  <button
                    onClick={selectAllSources}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                  >
                    {selectedSources.size === sources.length ? 'Deselect All' : 'Select All'}
                  </button>
                )}
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setSources([]);
                  setSelectedSources(new Set());
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {sourcesLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--gray-400)' }} />
              </div>
            ) : sources.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No enabled sources found
              </div>
            ) : (
              <>
                <div style={{
                  maxHeight: '300px',
                  overflowY: 'auto',
                  border: '1px solid var(--gray-200)',
                  borderRadius: '6px',
                  background: 'white',
                }}>
                  {sources.map((source) => (
                    <label
                      key={source.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.75rem',
                        padding: '0.5rem 0.75rem',
                        borderBottom: '1px solid var(--gray-100)',
                        cursor: 'pointer',
                        background: selectedSources.has(source.id) ? 'var(--primary-50)' : 'transparent',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedSources.has(source.id)}
                        onChange={() => toggleSourceSelection(source.id)}
                        style={{ width: '16px', height: '16px' }}
                      />
                      <span className="badge badge-primary" style={{ flexShrink: 0 }}>{source.state_code}</span>
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem' }}>
                        {source.name}
                      </span>
                      <span
                        className={`badge ${source.status === 'active' ? 'badge-success' : 'badge-warning'}`}
                        style={{ fontSize: '0.7rem', flexShrink: 0 }}
                      >
                        {source.source_type}
                      </span>
                    </label>
                  ))}
                </div>

                {selectedSources.size > 0 && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <button
                      onClick={runSelectedSources}
                      disabled={actionLoading !== null || isRunning}
                      className="btn btn-primary"
                      style={{ padding: '0.5rem 1rem' }}
                    >
                      {actionLoading === 'scan' ? (
                        <><Loader2 size={14} className="animate-spin" /> Scanning...</>
                      ) : (
                        <><Search size={14} /> Scan {selectedSources.size} Selected</>
                      )}
                    </button>
                    <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                      {selectedSources.size} of {sources.length} selected
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Expanded Stage Panel - Completed Hearings (view only) */}
        {expandedStage === 'complete' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--success-bg)',
            borderRadius: '8px',
            border: '1px solid var(--success)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, color: 'var(--success)' }}>
                  Completed Hearings
                </span>
                <select
                  value={stageStateFilter}
                  onChange={(e) => handleStageStateFilterChange(e.target.value)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.8rem',
                    minWidth: '120px',
                  }}
                >
                  <option value="">All States</option>
                  {states.map((s) => (
                    <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                  ))}
                </select>
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  {stageHearings.length} hearing{stageHearings.length !== 1 ? 's' : ''}
                </span>
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setStageHearings([]);
                  setStageStateFilter('');
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {stageHearingsLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--success)' }} />
              </div>
            ) : stageHearings.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No completed hearings found
              </div>
            ) : (
              <div style={{
                maxHeight: '300px',
                overflowY: 'auto',
                border: '1px solid var(--gray-200)',
                borderRadius: '6px',
                background: 'white',
              }}>
                {stageHearings.map((hearing) => (
                  <div
                    key={hearing.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      padding: '0.5rem 0.75rem',
                      borderBottom: '1px solid var(--gray-100)',
                    }}
                  >
                    <CheckCircle2 size={16} style={{ color: 'var(--success)', flexShrink: 0 }} />
                    <span className="badge badge-primary" style={{ flexShrink: 0 }}>{hearing.state_code}</span>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem' }}>
                      {hearing.title}
                    </span>
                    {hearing.hearing_date && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', flexShrink: 0 }}>
                        {hearing.hearing_date}
                      </span>
                    )}
                    <button
                      onClick={() => openHearingDetail(hearing.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '0.25rem',
                        color: 'var(--gray-400)',
                        flexShrink: 0,
                      }}
                      title="View details"
                    >
                      <Eye size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Expanded Stage Panel - Skipped Hearings */}
        {expandedStage === 'skipped' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--gray-100)',
            borderRadius: '8px',
            border: '1px solid var(--gray-300)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600, color: 'var(--gray-700)' }}>
                  Skipped/Dismissed Hearings
                </span>
                <select
                  value={stageStateFilter}
                  onChange={(e) => handleStageStateFilterChange(e.target.value)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.8rem',
                    minWidth: '120px',
                  }}
                >
                  <option value="">All States</option>
                  {states.map((s) => (
                    <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                  ))}
                </select>
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  {stageHearings.length} hearing{stageHearings.length !== 1 ? 's' : ''}
                </span>
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setStageHearings([]);
                  setStageStateFilter('');
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {stageHearingsLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--gray-400)' }} />
              </div>
            ) : stageHearings.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No skipped hearings found
              </div>
            ) : (
              <div style={{
                maxHeight: '300px',
                overflowY: 'auto',
                border: '1px solid var(--gray-200)',
                borderRadius: '6px',
                background: 'white',
              }}>
                {stageHearings.map((hearing) => (
                  <div
                    key={hearing.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.75rem',
                      padding: '0.5rem 0.75rem',
                      borderBottom: '1px solid var(--gray-100)',
                    }}
                  >
                    <SkipForward size={16} style={{ color: 'var(--gray-400)', flexShrink: 0 }} />
                    <span className="badge badge-primary" style={{ flexShrink: 0 }}>{hearing.state_code}</span>
                    <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                      {hearing.title}
                    </span>
                    {hearing.hearing_date && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', flexShrink: 0 }}>
                        {hearing.hearing_date}
                      </span>
                    )}
                    <button
                      onClick={() => openHearingDetail(hearing.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '0.25rem',
                        color: 'var(--gray-400)',
                        flexShrink: 0,
                      }}
                      title="View details"
                    >
                      <Eye size={16} />
                    </button>
                    <button
                      onClick={() => restoreHearing(hearing.id)}
                      style={{
                        background: 'none',
                        border: 'none',
                        cursor: 'pointer',
                        padding: '0.25rem',
                        color: 'var(--primary)',
                        flexShrink: 0,
                      }}
                      title="Restore (un-skip)"
                    >
                      <RotateCcw size={16} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Expanded Stage Panel - Review */}
        {expandedStage === 'review' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--gray-50)',
            borderRadius: '8px',
            border: '1px solid var(--gray-200)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 600 }}>Review Entities</span>
                {reviewStats && (
                  <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.8rem' }}>
                    <span className="badge badge-info">Topics: {reviewStats.topics}</span>
                    <span className="badge badge-info">Utilities: {reviewStats.utilities}</span>
                    <span className="badge badge-info">Dockets: {reviewStats.dockets}</span>
                  </div>
                )}
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setReviewItems([]);
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {reviewLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--gray-400)' }} />
              </div>
            ) : reviewItems.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No hearings need review
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '400px', overflowY: 'auto' }}>
                {reviewItems.map((hearing) => (
                  <div
                    key={hearing.hearing_id}
                    style={{
                      padding: '0.75rem',
                      background: 'white',
                      borderRadius: '6px',
                      border: hearing.lowest_confidence && hearing.lowest_confidence < 70 ? '1px solid var(--warning)' : '1px solid var(--gray-200)',
                      opacity: bulkProcessing === hearing.hearing_id ? 0.5 : 1,
                      position: 'relative',
                    }}
                  >
                    {bulkProcessing === hearing.hearing_id && (
                      <div style={{
                        position: 'absolute',
                        inset: 0,
                        background: 'rgba(255,255,255,0.7)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        zIndex: 10,
                        borderRadius: '6px',
                      }}>
                        <Loader2 size={20} className="animate-spin" style={{ color: 'var(--primary)' }} />
                      </div>
                    )}

                    {/* Hearing header */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                          <span className="badge badge-primary">{hearing.state_code}</span>
                          <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{hearing.hearing_title || 'Untitled'}</span>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                          {hearing.hearing_date} • {hearing.total_entities} entities
                          {hearing.lowest_confidence !== undefined && (
                            <span style={{ marginLeft: '0.5rem', color: hearing.lowest_confidence < 70 ? 'var(--warning)' : 'inherit' }}>
                              • Min: {hearing.lowest_confidence}%
                            </span>
                          )}
                        </div>
                      </div>
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          className="btn btn-success"
                          onClick={() => handleBulkApprove(hearing.hearing_id, 'approve_all')}
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                        >
                          <CheckCircle size={12} /> Approve
                        </button>
                        <button
                          className="btn btn-danger"
                          onClick={() => handleBulkApprove(hearing.hearing_id, 'reject_all')}
                          style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                        >
                          <XCircle size={12} /> Reject
                        </button>
                      </div>
                    </div>

                    {/* Entities - Individual approval */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                      {/* Utilities */}
                      {hearing.utilities.map((u) => (
                        <div key={`u-${u.id}`} style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.5rem',
                          background: 'var(--primary-50)',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                        }}>
                          <div style={{ flex: 1 }}>
                            <span style={{ fontWeight: 500, color: 'var(--primary-700)' }}>Utility: {u.name}</span>
                            {u.role && <span style={{ marginLeft: '0.5rem', color: 'var(--gray-500)' }}>({u.role})</span>}
                            <div style={{ fontSize: '0.7rem', color: 'var(--gray-500)', marginTop: '0.15rem' }}>
                              {u.confidence_score}% confidence • {u.match_type || 'auto'}
                              {u.review_reason && <span> • {u.review_reason}</span>}
                            </div>
                            {u.context && <div style={{ fontSize: '0.7rem', color: 'var(--gray-600)', marginTop: '0.25rem', fontStyle: 'italic' }}>{u.context}</div>}
                          </div>
                          <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.5rem' }}>
                            <button
                              className="btn btn-success"
                              onClick={() => handleEntityAction('utility', u.id, 'approve', hearing.hearing_id)}
                              style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                              title="Approve this utility"
                            >
                              <CheckCircle size={10} />
                            </button>
                            <button
                              className="btn btn-danger"
                              onClick={() => handleEntityAction('utility', u.id, 'reject', hearing.hearing_id)}
                              style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                              title="Reject this utility"
                            >
                              <XCircle size={10} />
                            </button>
                          </div>
                        </div>
                      ))}

                      {/* Dockets */}
                      {hearing.dockets.map((d) => (
                        <div key={`d-${d.id}`} style={{
                          padding: '0.5rem',
                          background: d.known_docket_id ? 'var(--success-50)' : 'var(--warning-50)',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          border: d.known_docket_id ? '1px solid var(--success-200)' : '1px solid var(--warning-200)',
                        }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ flex: 1 }}>
                              <span style={{ fontWeight: 500, fontFamily: 'monospace' }}>Docket: {d.name}</span>
                              <div style={{ fontSize: '0.7rem', color: 'var(--gray-500)', marginTop: '0.15rem' }}>
                                {d.confidence_score}% confidence • {d.match_type || 'auto'}
                                {d.review_reason && <span> • {d.review_reason}</span>}
                              </div>
                            </div>
                            <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.5rem' }}>
                              <button
                                className="btn btn-danger"
                                onClick={() => handleEntityAction('docket', d.id, 'reject', hearing.hearing_id, d.id)}
                                style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                                title="Reject this docket"
                              >
                                <XCircle size={10} />
                              </button>
                            </div>
                          </div>

                          {/* Transcript snippet */}
                          {d.context && d.context.includes('Transcript:') && (
                            <div style={{
                              marginTop: '0.4rem',
                              padding: '0.4rem',
                              background: 'var(--gray-50)',
                              borderRadius: '4px',
                              border: '1px solid var(--gray-200)',
                              fontSize: '0.7rem',
                              fontFamily: 'monospace',
                              color: 'var(--gray-700)',
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                            }}>
                              <span style={{ color: 'var(--gray-400)', fontSize: '0.6rem', display: 'block', marginBottom: '0.2rem' }}>
                                📜 Transcript context:
                              </span>
                              {d.context.split('Transcript:')[1]?.split(';')[0]?.replace(/"/g, '').trim() || d.context}
                            </div>
                          )}

                          {/* Proposed match */}
                          {d.known_docket_id && d.suggestions && d.suggestions.length > 0 && (
                            <div style={{ marginTop: '0.5rem', padding: '0.4rem', background: 'white', borderRadius: '4px', border: '1px solid var(--success-300)' }}>
                              <div style={{ fontSize: '0.7rem', color: 'var(--success-700)', fontWeight: 500, marginBottom: '0.25rem' }}>
                                ✓ Proposed Match:
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                                <div>
                                  <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{d.suggestions[0]?.normalized_id}</span>
                                  <div style={{ fontSize: '0.7rem', color: 'var(--gray-600)' }}>
                                    {d.known_title}
                                    {d.known_utility && <span style={{ marginLeft: '0.25rem', color: 'var(--primary)' }}>({d.known_utility})</span>}
                                  </div>
                                </div>
                                <button
                                  className="btn btn-success"
                                  onClick={() => handleEntityAction('docket', d.id, 'approve', hearing.hearing_id, d.id)}
                                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.7rem' }}
                                  title="Accept this match"
                                >
                                  <CheckCircle size={12} /> Accept
                                </button>
                              </div>
                            </div>
                          )}

                          {/* Alternative suggestions */}
                          {d.suggestions && d.suggestions.length > 1 && (
                            <details style={{ marginTop: '0.4rem' }}>
                              <summary style={{ fontSize: '0.7rem', color: 'var(--gray-500)', cursor: 'pointer' }}>
                                {d.suggestions.length - 1} other suggestion{d.suggestions.length > 2 ? 's' : ''}
                              </summary>
                              <div style={{ marginTop: '0.25rem', display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                                {d.suggestions.slice(1, 4).map((s) => (
                                  <div key={s.id} style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    padding: '0.25rem 0.4rem',
                                    background: 'white',
                                    borderRadius: '3px',
                                    fontSize: '0.7rem',
                                  }}>
                                    <div>
                                      <span style={{ fontFamily: 'monospace' }}>{s.normalized_id}</span>
                                      <span style={{ marginLeft: '0.25rem', color: 'var(--gray-500)' }}>
                                        {(s.title || '').substring(0, 40)}{(s.title || '').length > 40 ? '...' : ''}
                                      </span>
                                      <span style={{ marginLeft: '0.25rem', color: 'var(--gray-400)' }}>({Math.round(s.score)}%)</span>
                                    </div>
                                    <button
                                      className="btn btn-sm"
                                      onClick={() => handleLinkDocket(hearing.hearing_id, d.id, s.id)}
                                      style={{ padding: '0.15rem 0.3rem', fontSize: '0.6rem', background: 'var(--gray-100)' }}
                                      title="Link to this docket"
                                    >
                                      <Link size={10} /> Link
                                    </button>
                                  </div>
                                ))}
                              </div>
                            </details>
                          )}

                          {/* No match found */}
                          {!d.known_docket_id && d.suggestions && d.suggestions.length > 0 && (
                            <div style={{ marginTop: '0.5rem' }}>
                              <div style={{ fontSize: '0.7rem', color: 'var(--warning-700)', fontWeight: 500, marginBottom: '0.25rem' }}>
                                ⚠ No exact match - suggestions:
                              </div>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                                {d.suggestions.slice(0, 3).map((s) => (
                                  <div key={s.id} style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'space-between',
                                    padding: '0.3rem 0.4rem',
                                    background: 'white',
                                    borderRadius: '3px',
                                    fontSize: '0.7rem',
                                  }}>
                                    <div>
                                      <span style={{ fontFamily: 'monospace', fontWeight: 500 }}>{s.normalized_id}</span>
                                      <span style={{ marginLeft: '0.25rem', color: 'var(--gray-600)' }}>
                                        {(s.title || '').substring(0, 35)}{(s.title || '').length > 35 ? '...' : ''}
                                      </span>
                                      {s.utility_name && <span style={{ marginLeft: '0.25rem', color: 'var(--primary-500)' }}>({s.utility_name.substring(0, 20)})</span>}
                                      <span style={{ marginLeft: '0.25rem', color: 'var(--gray-400)' }}>({Math.round(s.score)}%)</span>
                                    </div>
                                    <button
                                      className="btn btn-success"
                                      onClick={() => handleLinkDocket(hearing.hearing_id, d.id, s.id)}
                                      style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                                      title="Link to this docket"
                                    >
                                      <Link size={10} /> Link
                                    </button>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      ))}

                      {/* Topics */}
                      {hearing.topics.map((t) => (
                        <div key={`t-${t.id}`} style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          padding: '0.5rem',
                          background: 'var(--gray-50)',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          border: '1px solid var(--gray-200)',
                        }}>
                          <div style={{ flex: 1 }}>
                            <span style={{ fontWeight: 500 }}>Topic: {t.name}</span>
                            {t.category && <span style={{ marginLeft: '0.5rem', color: 'var(--gray-500)' }}>({t.category})</span>}
                            <div style={{ fontSize: '0.7rem', color: 'var(--gray-500)', marginTop: '0.15rem' }}>
                              {t.confidence_score}% confidence • {t.match_type || 'auto'}
                              {t.review_reason && <span> • {t.review_reason}</span>}
                            </div>
                            {t.context && <div style={{ fontSize: '0.7rem', color: 'var(--gray-600)', marginTop: '0.25rem', fontStyle: 'italic' }}>{t.context}</div>}
                          </div>
                          <div style={{ display: 'flex', gap: '0.25rem', marginLeft: '0.5rem' }}>
                            <button
                              className="btn btn-success"
                              onClick={() => handleEntityAction('topic', t.id, 'approve', hearing.hearing_id)}
                              style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                              title="Approve this topic"
                            >
                              <CheckCircle size={10} />
                            </button>
                            <button
                              className="btn btn-danger"
                              onClick={() => handleEntityAction('topic', t.id, 'reject', hearing.hearing_id)}
                              style={{ padding: '0.2rem 0.4rem', fontSize: '0.65rem' }}
                              title="Reject this topic"
                            >
                              <XCircle size={10} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Expanded Stage Panel - Hearings for other stages */}
        {expandedStage && expandedStage !== 'discover' && expandedStage !== 'complete' && expandedStage !== 'skipped' && expandedStage !== 'review' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: 'var(--gray-50)',
            borderRadius: '8px',
            border: '1px solid var(--gray-200)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
                <span style={{ fontWeight: 600 }}>
                  Select hearings for {STAGES.find(s => s.key === expandedStage)?.label}
                </span>
                <select
                  value={stageStateFilter}
                  onChange={(e) => handleStageStateFilterChange(e.target.value)}
                  style={{
                    padding: '0.25rem 0.5rem',
                    borderRadius: '4px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.8rem',
                    minWidth: '120px',
                  }}
                >
                  <option value="">All States</option>
                  {states.map((s) => (
                    <option key={s.code} value={s.code}>{s.code} - {s.name}</option>
                  ))}
                </select>
                {stageHearings.length > 0 && (
                  <button
                    onClick={selectAllHearings}
                    className="btn btn-secondary"
                    style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                  >
                    {selectedHearings.size === stageHearings.length ? 'Deselect All' : 'Select All'}
                  </button>
                )}
                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  {stageHearings.length} hearing{stageHearings.length !== 1 ? 's' : ''}
                </span>
              </div>
              <button
                onClick={() => {
                  setExpandedStage(null);
                  setStageHearings([]);
                  setSelectedHearings(new Set());
                  setStageStateFilter('');
                }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {stageHearingsLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--gray-400)' }} />
              </div>
            ) : stageHearings.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No hearings pending for this stage
              </div>
            ) : (
              <>
                {/* Sortable Header */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  padding: '0.5rem 0.75rem',
                  background: 'var(--gray-100)',
                  borderRadius: '6px 6px 0 0',
                  border: '1px solid var(--gray-200)',
                  borderBottom: 'none',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  color: 'var(--gray-600)',
                }}>
                  <div style={{ width: '16px' }} /> {/* Checkbox placeholder */}
                  <button
                    onClick={() => handleSortChange('state_code')}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      color: sortField === 'state_code' ? 'var(--primary)' : 'var(--gray-600)',
                      fontWeight: sortField === 'state_code' ? 700 : 600,
                      fontSize: '0.75rem',
                    }}
                  >
                    State
                    {sortField === 'state_code' && (sortDirection === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <button
                    onClick={() => handleSortChange('title')}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      flex: 1,
                      color: sortField === 'title' ? 'var(--primary)' : 'var(--gray-600)',
                      fontWeight: sortField === 'title' ? 700 : 600,
                      fontSize: '0.75rem',
                    }}
                  >
                    Title
                    {sortField === 'title' && (sortDirection === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <button
                    onClick={() => handleSortChange('duration_seconds')}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      color: sortField === 'duration_seconds' ? 'var(--primary)' : 'var(--gray-600)',
                      fontWeight: sortField === 'duration_seconds' ? 700 : 600,
                      fontSize: '0.75rem',
                      minWidth: '60px',
                    }}
                  >
                    Duration
                    {sortField === 'duration_seconds' && (sortDirection === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <button
                    onClick={() => handleSortChange('hearing_date')}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      color: sortField === 'hearing_date' ? 'var(--primary)' : 'var(--gray-600)',
                      fontWeight: sortField === 'hearing_date' ? 700 : 600,
                      fontSize: '0.75rem',
                      minWidth: '85px',
                    }}
                  >
                    Posted
                    {sortField === 'hearing_date' && (sortDirection === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <button
                    onClick={() => handleSortChange('created_at')}
                    style={{
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: '0.25rem 0.5rem',
                      borderRadius: '4px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem',
                      color: sortField === 'created_at' ? 'var(--primary)' : 'var(--gray-600)',
                      fontWeight: sortField === 'created_at' ? 700 : 600,
                      fontSize: '0.75rem',
                      minWidth: '85px',
                    }}
                  >
                    Discovered
                    {sortField === 'created_at' && (sortDirection === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />)}
                  </button>
                  <div style={{ width: '56px' }} /> {/* Actions placeholder */}
                </div>
                <div style={{
                  maxHeight: '300px',
                  overflowY: 'auto',
                  border: '1px solid var(--gray-200)',
                  borderRadius: '0 0 6px 6px',
                  background: 'white',
                }}>
                  {sortedStageHearings.map((hearing) => (
                    <label
                      key={hearing.id}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '0.75rem',
                        padding: '0.5rem 0.75rem',
                        borderBottom: '1px solid var(--gray-100)',
                        cursor: 'pointer',
                        background: selectedHearings.has(hearing.id) ? 'var(--primary-50)' : 'transparent',
                      }}
                    >
                      <input
                        type="checkbox"
                        checked={selectedHearings.has(hearing.id)}
                        onChange={() => toggleHearingSelection(hearing.id)}
                        style={{ width: '16px', height: '16px' }}
                      />
                      <span className="badge badge-primary" style={{ flexShrink: 0 }}>{hearing.state_code}</span>
                      <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem' }}>
                        {hearing.title}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', flexShrink: 0, minWidth: '50px', textAlign: 'right' }}>
                        {formatDuration(hearing.duration_seconds)}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', flexShrink: 0, minWidth: '80px', textAlign: 'right' }}>
                        {hearing.hearing_date || '-'}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-400)', flexShrink: 0, minWidth: '80px', textAlign: 'right' }}>
                        {hearing.created_at ? new Date(hearing.created_at).toLocaleDateString() : '-'}
                      </span>
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          openHearingDetail(hearing.id);
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '0.25rem',
                          color: 'var(--gray-400)',
                          flexShrink: 0,
                        }}
                        title="View details"
                      >
                        <Eye size={16} />
                      </button>
                      <button
                        onClick={(e) => {
                          e.preventDefault();
                          e.stopPropagation();
                          dismissHearing(hearing.id);
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: '0.25rem',
                          color: 'var(--gray-400)',
                          flexShrink: 0,
                        }}
                        title="Dismiss (skip processing)"
                      >
                        <SkipForward size={16} />
                      </button>
                    </label>
                  ))}
                </div>

                {selectedHearings.size > 0 && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <button
                      onClick={() => runSelectedHearings(STAGES.find(s => s.key === expandedStage)?.action || '')}
                      disabled={actionLoading !== null || isRunning}
                      className="btn btn-primary"
                      style={{ padding: '0.5rem 1rem' }}
                    >
                      {actionLoading ? (
                        <><Loader2 size={14} className="animate-spin" /> Running...</>
                      ) : (
                        <><Play size={14} /> Run {selectedHearings.size} Selected</>
                      )}
                    </button>
                    <button
                      onClick={() => dismissSelectedHearings()}
                      disabled={actionLoading !== null}
                      className="btn btn-secondary"
                      style={{ padding: '0.5rem 1rem' }}
                    >
                      <SkipForward size={14} /> Dismiss {selectedHearings.size} Selected
                    </button>
                    <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                      {selectedHearings.size} of {stageHearings.length} selected
                    </span>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Run Full Pipeline */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flexWrap: 'wrap' }}>
          <button
            onClick={runFullPipeline}
            disabled={actionLoading !== null || isRunning}
            className="btn btn-primary"
            style={{ padding: '0.75rem 1.5rem', fontSize: '1rem' }}
          >
            {actionLoading === 'full' ? (
              <><Loader2 size={18} className="animate-spin" /> Starting...</>
            ) : (
              <><Play size={18} /> Run Full Pipeline</>
            )}
          </button>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>States:</span>
            {states.slice(0, 6).map(s => (
              <button
                key={s.code}
                onClick={() => toggleState(s.code)}
                className={`btn ${selectedStates.has(s.code) ? 'btn-primary' : 'btn-secondary'}`}
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
              >
                {s.code} {selectedStates.has(s.code) && '✓'}
              </button>
            ))}
            {states.length > 6 && (
              <button
                onClick={selectAllStates}
                className="btn btn-secondary"
                style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
              >
                {selectedStates.size === states.length ? 'Clear' : `+${states.length - 6} more`}
              </button>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>Cost limit: $</span>
            <input
              type="number"
              value={costLimit}
              onChange={(e) => setCostLimit(e.target.value)}
              style={{ width: '70px', padding: '0.25rem 0.5rem', borderRadius: '4px', border: '1px solid var(--gray-300)' }}
            />
          </div>
        </div>
      </div>

      {/* Scraper Running - Progress Section */}
      {isScraperRunning && scraperProgress && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem', background: 'var(--primary-50)', border: '1px solid var(--primary-200)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <Search size={20} className="animate-spin" style={{ color: 'var(--primary)' }} />
              <div>
                <div style={{ fontWeight: 600, color: 'var(--primary-700)', fontSize: '1rem' }}>
                  Scanning Sources
                </div>
                {scraperProgress.current_source_name && (
                  <div style={{ color: 'var(--gray-600)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                    {scraperProgress.current_source_name}
                    {scraperProgress.current_scraper_type && (
                      <span className="badge badge-secondary" style={{ marginLeft: '0.5rem', fontSize: '0.7rem' }}>
                        {scraperProgress.current_scraper_type}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
            <div style={{ textAlign: 'right', fontSize: '0.875rem' }}>
              <div style={{ fontWeight: 600, color: 'var(--primary-700)' }}>
                {scraperProgress.new_hearings} new
              </div>
              <div style={{ color: 'var(--gray-500)', fontSize: '0.75rem' }}>
                {scraperProgress.items_found} found
              </div>
            </div>
          </div>

          {/* Progress bar */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.8rem', color: 'var(--gray-600)' }}>
              <span>Source {scraperProgress.current_source_index} of {scraperProgress.total_sources}</span>
              <span>{scraperProgress.sources_completed} completed</span>
            </div>
            <div style={{ height: '6px', background: 'var(--primary-100)', borderRadius: '3px', overflow: 'hidden' }}>
              <div
                style={{
                  width: scraperProgress.total_sources > 0
                    ? `${(scraperProgress.sources_completed / scraperProgress.total_sources) * 100}%`
                    : '0%',
                  height: '100%',
                  background: 'var(--primary)',
                  borderRadius: '3px',
                  transition: 'width 0.3s ease',
                }}
              />
            </div>
          </div>

          {scraperProgress.errors && scraperProgress.errors.length > 0 && (
            <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: 'var(--danger-50)', borderRadius: '4px', fontSize: '0.8rem', color: 'var(--danger-700)' }}>
              {scraperProgress.errors.length} error(s) during scan
            </div>
          )}
        </div>
      )}

      {/* Pipeline Currently Running - Progress Section */}
      {(isRunning || isPaused) && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem', background: 'var(--primary-50)', border: '1px solid var(--primary-200)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              {isRunning && <Loader2 size={20} className="animate-spin" style={{ color: 'var(--primary)' }} />}
              {isPaused && <Clock size={20} style={{ color: 'var(--warning)' }} />}
              <div>
                <div style={{ fontWeight: 600, color: 'var(--primary-700)', fontSize: '1rem' }}>
                  {isPaused ? 'Paused' : status?.current_stage ? `${status.current_stage.charAt(0).toUpperCase() + status.current_stage.slice(1)}ing` : 'Processing'}
                </div>
                {status?.current_hearing_title && (
                  <div style={{ color: 'var(--gray-600)', fontSize: '0.875rem', marginTop: '0.25rem' }}>
                    {status.current_hearing_title.slice(0, 80)}{status.current_hearing_title.length > 80 && '...'}
                  </div>
                )}
              </div>
            </div>
            <button
              onClick={stopPipeline}
              disabled={actionLoading === 'stop'}
              className="btn btn-danger"
              style={{ padding: '0.5rem 1rem', fontSize: '0.875rem' }}
            >
              {actionLoading === 'stop' ? <Loader2 size={14} className="animate-spin" /> : <Square size={14} />} Stop
            </button>
          </div>

          {/* Progress bar */}
          <div style={{ marginTop: '0.75rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.8rem', color: 'var(--gray-600)' }}>
              <span>Session progress</span>
              <span>{status?.hearings_processed || 0} processed • ${(status?.total_cost_usd || 0).toFixed(2)} spent</span>
            </div>
            <div style={{ height: '6px', background: 'var(--primary-100)', borderRadius: '3px', overflow: 'hidden' }}>
              <div
                className="animate-pulse"
                style={{
                  width: '100%',
                  height: '100%',
                  background: 'linear-gradient(90deg, var(--primary) 0%, var(--primary-400) 50%, var(--primary) 100%)',
                  backgroundSize: '200% 100%',
                  animation: 'shimmer 2s infinite linear',
                }}
              />
            </div>
          </div>
        </div>
      )}

      {/* Today's Stats with Activity/Errors toggles */}
      <div className="card" style={{ padding: '1rem', background: 'var(--gray-50)', marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap', fontSize: '0.9rem' }}>
            <div>
              <span style={{ color: 'var(--gray-500)' }}>Today:</span>
              <span style={{ fontWeight: 600, marginLeft: '0.5rem' }}>{status?.processed_today || 0} processed</span>
            </div>
            <div>
              <span style={{ color: 'var(--gray-500)' }}>Spent:</span>
              <span style={{ fontWeight: 600, marginLeft: '0.5rem' }}>${(status?.cost_today || 0).toFixed(2)}</span>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              onClick={() => setShowActivity(!showActivity)}
              className={`btn ${showActivity ? 'btn-primary' : 'btn-secondary'}`}
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
            >
              <Activity size={14} /> Activity ({activity.length})
            </button>
            <button
              onClick={() => setShowErrors(!showErrors)}
              className={`btn ${errors.length > 0 ? (showErrors ? 'btn-danger' : 'btn-warning') : (showErrors ? 'btn-primary' : 'btn-secondary')}`}
              style={{ padding: '0.4rem 0.75rem', fontSize: '0.8rem' }}
            >
              <AlertTriangle size={14} /> Errors ({errors.length})
            </button>
          </div>
        </div>
      </div>

      {/* Activity Panel */}
      {showActivity && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Recent Activity</h3>
            <button
              onClick={() => setShowActivity(false)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
            >
              <X size={18} color="var(--gray-500)" />
            </button>
          </div>

          {activity.length === 0 ? (
            <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
              No recent activity
            </div>
          ) : (
            <div style={{
              maxHeight: '300px',
              overflowY: 'auto',
              border: '1px solid var(--gray-200)',
              borderRadius: '6px',
            }}>
              {activity.map((item) => (
                <div
                  key={item.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.75rem',
                    padding: '0.5rem 0.75rem',
                    borderBottom: '1px solid var(--gray-100)',
                    background: item.status === 'error' ? 'var(--danger-50)' : 'transparent',
                  }}
                >
                  {item.status === 'complete' ? (
                    <CheckCircle2 size={16} style={{ color: 'var(--success)', flexShrink: 0 }} />
                  ) : (
                    <AlertCircle size={16} style={{ color: 'var(--danger)', flexShrink: 0 }} />
                  )}
                  <span className="badge badge-primary" style={{ flexShrink: 0 }}>{item.state_code}</span>
                  <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem' }}>
                    {item.hearing_title}
                  </span>
                  <span className="badge badge-secondary" style={{ flexShrink: 0, fontSize: '0.7rem' }}>{item.stage}</span>
                  {item.cost_usd && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)', flexShrink: 0 }}>
                      ${item.cost_usd.toFixed(2)}
                    </span>
                  )}
                  <span style={{ fontSize: '0.75rem', color: 'var(--gray-400)', flexShrink: 0 }}>
                    {item.completed_at ? new Date(item.completed_at).toLocaleTimeString() : ''}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Errors Panel */}
      {showErrors && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem', border: errors.length > 0 ? '1px solid var(--danger-200)' : undefined }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
            <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, color: errors.length > 0 ? 'var(--danger)' : undefined }}>
              Failed Hearings ({errors.length})
            </h3>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              {errors.length > 0 && (
                <button
                  onClick={retryAllErrors}
                  className="btn btn-secondary"
                  style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                >
                  <RotateCcw size={12} /> Retry All
                </button>
              )}
              <button
                onClick={() => setShowErrors(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>
          </div>

          {errors.length === 0 ? (
            <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
              <CheckCircle2 size={24} style={{ color: 'var(--success)', marginBottom: '0.5rem' }} />
              <div>No errors - all hearings processed successfully!</div>
            </div>
          ) : (
            <div style={{
              maxHeight: '400px',
              overflowY: 'auto',
              border: '1px solid var(--gray-200)',
              borderRadius: '6px',
            }}>
              {errors.map((err) => (
                <div
                  key={err.hearing_id}
                  style={{
                    padding: '0.75rem',
                    borderBottom: '1px solid var(--gray-100)',
                    background: 'var(--danger-50)',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.75rem' }}>
                    <AlertCircle size={16} style={{ color: 'var(--danger)', flexShrink: 0, marginTop: '0.125rem' }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <span className="badge badge-primary">{err.state_code}</span>
                        <span style={{ fontWeight: 500, fontSize: '0.875rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {err.hearing_title}
                        </span>
                      </div>
                      {err.error_message && (
                        <div style={{
                          fontSize: '0.8rem',
                          color: 'var(--danger-700)',
                          background: 'var(--danger-100)',
                          padding: '0.5rem',
                          borderRadius: '4px',
                          marginTop: '0.5rem',
                          fontFamily: 'monospace',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          maxHeight: '100px',
                          overflow: 'auto',
                        }}>
                          {err.error_message}
                        </div>
                      )}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {err.last_stage && <span>Stage: {err.last_stage}</span>}
                        <span>Retries: {err.retry_count}</span>
                        <span className={`badge ${err.status === 'failed' ? 'badge-danger' : 'badge-warning'}`} style={{ fontSize: '0.7rem' }}>
                          {err.status}
                        </span>
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '0.25rem', flexShrink: 0 }}>
                      <button
                        onClick={() => retryHearing(err.hearing_id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        title="Retry"
                      >
                        <RotateCcw size={12} />
                      </button>
                      <button
                        onClick={() => skipHearing(err.hearing_id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        title="Skip"
                      >
                        <SkipForward size={12} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Hearing Detail Modal */}
      {detailModalOpen && (
        <div className="modal-overlay" onClick={closeHearingDetail}>
          <div className="modal" style={{ maxWidth: '700px' }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Hearing Details</h3>
              <button
                onClick={closeHearingDetail}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}
              >
                <X size={20} />
              </button>
            </div>
            <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto' }}>
              {detailLoading ? (
                <div className="loading"><div className="spinner" /></div>
              ) : detailHearing ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  {/* Header Info */}
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <span className="badge badge-primary">{detailHearing.state_code}</span>
                      <span className={`badge ${
                        detailHearing.status === 'complete' ? 'badge-success' :
                        detailHearing.status === 'error' || detailHearing.status === 'failed' ? 'badge-danger' :
                        'badge-info'
                      }`}>{detailHearing.status}</span>
                    </div>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem', fontWeight: 600 }}>
                      {detailHearing.title}
                    </h4>
                    <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
                      {detailHearing.hearing_date && <span>Date: {detailHearing.hearing_date} • </span>}
                      <span>Cost: ${detailHearing.processing_cost_usd.toFixed(4)}</span>
                    </div>
                    {detailHearing.video_url && (
                      <a
                        href={detailHearing.video_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: '0.85rem', color: 'var(--primary)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.5rem' }}
                      >
                        <ExternalLink size={14} /> View source
                      </a>
                    )}
                  </div>

                  {/* Processing History */}
                  <div>
                    <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                      Processing History
                    </h5>
                    {detailHearing.jobs.length === 0 ? (
                      <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>No processing history yet</div>
                    ) : (
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {detailHearing.jobs.map((job) => (
                          <div
                            key={job.id}
                            style={{
                              padding: '0.75rem',
                              background: job.status === 'error' ? 'var(--danger-50)' : 'var(--gray-50)',
                              borderRadius: '6px',
                              border: job.status === 'error' ? '1px solid var(--danger-200)' : '1px solid var(--gray-200)',
                            }}
                          >
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{job.stage}</span>
                                <span className={`badge ${
                                  job.status === 'complete' ? 'badge-success' :
                                  job.status === 'error' ? 'badge-danger' :
                                  job.status === 'running' ? 'badge-info' :
                                  'badge-gray'
                                }`}>{job.status}</span>
                              </div>
                              {job.cost_usd !== null && job.cost_usd > 0 && (
                                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                                  ${job.cost_usd.toFixed(4)}
                                </span>
                              )}
                            </div>
                            <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                              {job.completed_at ? (
                                <span>Completed: {new Date(job.completed_at).toLocaleString()}</span>
                              ) : job.started_at ? (
                                <span>Started: {new Date(job.started_at).toLocaleString()}</span>
                              ) : null}
                              {job.retry_count > 0 && <span> • Retries: {job.retry_count}</span>}
                            </div>
                            {job.error_message && (
                              <div style={{
                                marginTop: '0.5rem',
                                padding: '0.5rem',
                                background: 'var(--danger-100)',
                                borderRadius: '4px',
                                fontSize: '0.8rem',
                                color: 'var(--danger-700)',
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                              }}>
                                {job.error_message}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Transcript Preview */}
                  {detailHearing.transcript && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                        Transcript ({detailHearing.transcript.word_count.toLocaleString()} words)
                      </h5>
                      <div style={{
                        padding: '0.75rem',
                        background: 'var(--gray-50)',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                        maxHeight: '150px',
                        overflowY: 'auto',
                        whiteSpace: 'pre-wrap',
                        lineHeight: 1.5,
                      }}>
                        {detailHearing.transcript.preview || 'No preview available'}
                      </div>
                    </div>
                  )}

                  {/* Analysis */}
                  {detailHearing.analysis && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                        Analysis
                      </h5>
                      {detailHearing.analysis.one_sentence_summary && (
                        <div style={{
                          padding: '0.75rem',
                          background: 'var(--primary-50)',
                          borderRadius: '6px',
                          fontSize: '0.9rem',
                          fontWeight: 500,
                          marginBottom: '0.75rem',
                          borderLeft: '3px solid var(--primary)',
                        }}>
                          {detailHearing.analysis.one_sentence_summary}
                        </div>
                      )}
                      <div style={{
                        padding: '0.75rem',
                        background: 'var(--gray-50)',
                        borderRadius: '6px',
                        fontSize: '0.85rem',
                        lineHeight: 1.5,
                      }}>
                        {detailHearing.analysis.summary || 'No summary available'}
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '0.75rem' }}>
                        {detailHearing.analysis.hearing_type && (
                          <div>
                            <strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Type:</strong>
                            <span className="badge badge-info" style={{ marginLeft: '0.25rem' }}>
                              {detailHearing.analysis.hearing_type}
                            </span>
                          </div>
                        )}
                        {detailHearing.analysis.utility_name && (
                          <div>
                            <strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Utility:</strong>
                            <span style={{ marginLeft: '0.25rem', fontSize: '0.85rem' }}>
                              {detailHearing.analysis.utility_name}
                            </span>
                          </div>
                        )}
                        {detailHearing.analysis.commissioner_mood && (
                          <div>
                            <strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Mood:</strong>
                            <span className="badge badge-secondary" style={{ marginLeft: '0.25rem' }}>
                              {detailHearing.analysis.commissioner_mood}
                            </span>
                          </div>
                        )}
                      </div>
                      {detailHearing.analysis.likely_outcome && (
                        <div style={{ marginTop: '0.75rem' }}>
                          <strong style={{ fontSize: '0.85rem' }}>Likely Outcome:</strong>
                          <div style={{
                            padding: '0.5rem 0.75rem',
                            background: 'var(--gray-50)',
                            borderRadius: '4px',
                            fontSize: '0.85rem',
                            marginTop: '0.25rem',
                          }}>
                            {detailHearing.analysis.likely_outcome}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Extracted Dockets */}
                  {detailHearing.dockets && detailHearing.dockets.length > 0 && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                        Extracted Dockets ({detailHearing.dockets.length})
                      </h5>
                      <div style={{
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.5rem',
                      }}>
                        {detailHearing.dockets.map((docket) => (
                          <div
                            key={docket.id}
                            style={{
                              padding: '0.75rem',
                              background: 'var(--primary-50)',
                              borderRadius: '6px',
                              border: '1px solid var(--primary-200)',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                              <span style={{ fontWeight: 600, color: 'var(--primary-700)' }}>
                                {docket.normalized_id}
                              </span>
                              {docket.status && (
                                <span className="badge badge-info">{docket.status}</span>
                              )}
                            </div>
                            {docket.title && (
                              <div style={{ fontSize: '0.85rem', color: 'var(--gray-600)', marginTop: '0.25rem' }}>
                                {docket.title}
                              </div>
                            )}
                            {docket.company && (
                              <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                                Company: {docket.company}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--gray-500)' }}>
                  Failed to load hearing details
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                {detailHearing && detailHearing.status !== 'skipped' && detailHearing.status !== 'complete' && (
                  <button
                    onClick={() => {
                      dismissHearing(detailHearing.id);
                      closeHearingDetail();
                    }}
                    className="btn btn-secondary"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                  >
                    <SkipForward size={14} /> Dismiss
                  </button>
                )}
                {detailHearing && detailHearing.status === 'skipped' && (
                  <button
                    onClick={() => {
                      restoreHearing(detailHearing.id);
                      closeHearingDetail();
                    }}
                    className="btn btn-primary"
                    style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}
                  >
                    <RotateCcw size={14} /> Restore
                  </button>
                )}
              </div>
              <button onClick={closeHearingDetail} className="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
