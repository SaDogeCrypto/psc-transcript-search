'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  AlertCircle,
  Play,
  Square,
  RefreshCw,
  Search,
  CheckCircle2,
  ChevronDown,
  Loader2,
  X,
  SkipForward,
  ExternalLink,
  ArrowUpDown,
  Eye,
  RotateCcw,
  FileText,
  Sparkles,
  Mic,
  Activity,
  Rss,
  Ban,
  Settings,
  Clock,
  DollarSign,
  Database,
  FolderSearch,
  FileCheck,
  Zap,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// ============================================================================
// TYPES
// ============================================================================

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

interface StageHearing {
  id: number;
  title: string;
  state_code: string;
  hearing_date: string | null;
  created_at: string | null;
  duration_seconds: number | null;
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

interface HearingDetails {
  id: number;
  title: string;
  hearing_date: string | null;
  hearing_type: string | null;
  source_url: string | null;
  video_url: string | null;
  transcript_status: string | null;
  segment_count: number;
  has_analysis: boolean;
  analysis_summary: string | null;
  processing_cost_usd: number | null;
  analysis_cost: number | null;
  jobs: {
    id: number;
    stage: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    cost_usd: number | null;
    details: string | null;
  }[];
  transcript_preview: {
    speaker: string;
    text: string;
    start_time: number;
    end_time: number;
  }[];
  analysis: {
    summary: string | null;
    one_sentence_summary: string | null;
    hearing_type: string | null;
    utility_name: string | null;
    sector: string | null;
    commissioner_mood: string | null;
    likely_outcome: string | null;
    topics: string[] | null;
    issues: unknown[] | null;
  } | null;
}

interface DataQuality {
  total_hearings: number;
  hearings_with_transcripts: number;
  hearings_with_analysis: number;
  transcript_coverage: number;
  analysis_coverage: number;
  docket_confidence: {
    verified: number;
    likely: number;
    possible: number;
    unverified: number;
  };
}

interface ScraperStatus {
  status: string;
  items_found: number;
  new_hearings: number;
  last_run: string | null;
  errors: string[];
}

interface DocketDiscoveryStats {
  total_dockets: number;
  by_year: Record<string, number>;
  by_sector: Record<string, number>;
  by_status: Record<string, number>;
}

interface DocketDiscoveryStatus {
  status: string;
  started_at: string | null;
  completed_at: string | null;
  dockets_found: number;
  dockets_new: number;
  dockets_updated: number;
  errors: string[];
}

interface DocketVerifyResult {
  valid: boolean;
  docket_number: string;
  title?: string;
  status?: string;
  filed_date?: string;
  industry_type?: string;
  error?: string;
}

interface ThunderstoneResult {
  title: string;
  url: string;
  description: string;
  docket_number: string | null;
  document_type: string | null;
  date: string | null;
}

interface Source {
  id: number;
  state_code: string;
  state_name: string;
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
  last_checked_at: string | null;
  last_hearing_at: string | null;
  status: string;
}

type SortField = 'hearing_date' | 'created_at' | 'title' | 'duration_seconds';
type SortDirection = 'asc' | 'desc';

// Stage configuration - Full Florida pipeline
const STAGES = [
  { key: 'discover', label: 'Discover', pendingStatus: 'discover', action: 'discover', description: 'Scan Florida Channel RSS feed for new PSC hearing videos' },
  { key: 'transcribe', label: 'Transcribe', pendingStatus: 'pending', action: 'transcribe', description: 'Convert audio to text using Groq Whisper (~$0.04/hour)' },
  { key: 'analyze', label: 'Analyze', pendingStatus: 'transcribed', action: 'analyze', description: 'Extract topics, utilities, and dockets using GPT-4o-mini' },
];

// ============================================================================
// COMPONENT
// ============================================================================

export default function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Run options
  const [runLimit, setRunLimit] = useState<number>(5);

  // Expanded stage panel
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [stageHearings, setStageHearings] = useState<StageHearing[]>([]);
  const [stageHearingsLoading, setStageHearingsLoading] = useState(false);
  const [selectedHearings, setSelectedHearings] = useState<Set<number>>(new Set());

  // Sorting for stage hearings
  const [sortField, setSortField] = useState<SortField>('hearing_date');
  const [sortDirection, setSortDirection] = useState<SortDirection>('desc');

  // Activity and Errors
  const [activity, setActivity] = useState<ActivityItem[]>([]);
  const [errors, setErrors] = useState<PipelineError[]>([]);
  const [showActivity, setShowActivity] = useState(true);
  const [showErrors, setShowErrors] = useState(true);

  // Hearing detail modal
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailHearing, setDetailHearing] = useState<HearingDetails | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Data quality
  const [dataQuality, setDataQuality] = useState<DataQuality | null>(null);

  // Scraper & Sources
  const [scraperStatus, setScraperStatus] = useState<ScraperStatus | null>(null);
  const [lastDiscoverResult, setLastDiscoverResult] = useState<{ found: number; new: number } | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [showSources, setShowSources] = useState(false);

  // Docket Discovery
  const [showDocketDiscovery, setShowDocketDiscovery] = useState(false);
  const [docketStats, setDocketStats] = useState<DocketDiscoveryStats | null>(null);
  const [docketDiscoveryStatus, setDocketDiscoveryStatus] = useState<DocketDiscoveryStatus | null>(null);
  const [docketDiscoveryLoading, setDocketDiscoveryLoading] = useState(false);
  const [verifyDocketNumber, setVerifyDocketNumber] = useState('');
  const [verifyResult, setVerifyResult] = useState<DocketVerifyResult | null>(null);
  const [verifyLoading, setVerifyLoading] = useState(false);
  const [thunderstoneQuery, setThunderstoneQuery] = useState('');
  const [thunderstoneResults, setThunderstoneResults] = useState<ThunderstoneResult[]>([]);
  const [thunderstoneLoading, setThunderstoneLoading] = useState(false);
  const [docketYear, setDocketYear] = useState<number>(new Date().getFullYear());

  const loadData = useCallback(async () => {
    try {
      const [statusRes, activityRes, errorsRes, qualityRes, scraperRes, sourcesRes, docketStatsRes] = await Promise.all([
        fetch(`${API_URL}/admin/pipeline/status`),
        fetch(`${API_URL}/admin/pipeline/activity?limit=20`),
        fetch(`${API_URL}/admin/pipeline/errors?limit=20`),
        fetch(`${API_URL}/admin/pipeline/data-quality`),
        fetch(`${API_URL}/admin/scraper/status`),
        fetch(`${API_URL}/admin/sources`),
        fetch(`${API_URL}/admin/pipeline/docket-discovery/stats`),
      ]);

      if (!statusRes.ok) throw new Error('Failed to load pipeline status');

      const statusData = await statusRes.json();
      setStatus(statusData);

      if (activityRes.ok) {
        const activityData = await activityRes.json();
        setActivity(activityData.items || []);
      }

      if (errorsRes.ok) {
        const errorsData = await errorsRes.json();
        setErrors(errorsData.items || []);
      }

      if (qualityRes.ok) {
        const qualityData = await qualityRes.json();
        setDataQuality(qualityData);
      }

      if (scraperRes.ok) {
        const scraperData = await scraperRes.json();
        setScraperStatus(scraperData);
      }

      if (sourcesRes.ok) {
        const sourcesData = await sourcesRes.json();
        setSources(sourcesData || []);
      }

      if (docketStatsRes.ok) {
        const docketStatsData = await docketStatsRes.json();
        setDocketStats(docketStatsData);
      }

      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, [loadData]);

  const runScraper = async () => {
    setActionLoading('discover');
    setLastDiscoverResult(null);
    try {
      const res = await fetch(`${API_URL}/admin/scrapers/run?state_code=FL&scraper=rss`, {
        method: 'POST',
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to run scraper');
      }

      const result = await res.json();
      setLastDiscoverResult({
        found: result.items_found || 0,
        new: result.hearings_created || 0,
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run scraper');
    } finally {
      setActionLoading(null);
    }
  };

  const runStage = async (stage: string) => {
    if (stage === 'discover') {
      await runScraper();
      return;
    }

    if (status?.status === 'running') {
      setError('Pipeline is currently running. Please wait or stop it first.');
      return;
    }

    setActionLoading(stage);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage, limit: runLimit }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to run stage');
      }

      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run stage');
    } finally {
      setActionLoading(null);
    }
  };

  const stopPipeline = async () => {
    setActionLoading('stop');
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/stop`, { method: 'POST' });
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

  const loadStageHearings = async (stage: string) => {
    setStageHearingsLoading(true);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/pending?stage=${stage}&limit=100`);
      if (!res.ok) throw new Error('Failed to load hearings');
      const data = await res.json();

      const hearings = (data.hearings || []).map((h: { id: string | number; title: string | null; hearing_date: string | null }) => ({
        id: typeof h.id === 'string' ? parseInt(h.id, 10) : h.id,
        title: h.title || `Hearing ${h.id}`,
        state_code: 'FL',
        hearing_date: h.hearing_date,
        created_at: null,
        duration_seconds: null,
      }));

      setStageHearings(hearings);
    } catch (err) {
      console.error('Failed to load stage hearings:', err);
      setStageHearings([]);
    } finally {
      setStageHearingsLoading(false);
    }
  };

  const loadCompletedHearings = async () => {
    setStageHearingsLoading(true);
    try {
      const res = await fetch(`${API_URL}/admin/hearings?status=analyzed&page_size=100`);
      if (!res.ok) throw new Error('Failed to load hearings');
      const data = await res.json();

      const hearings = (data.items || []).map((h: { id: number; title: string | null; hearing_date: string | null; duration_seconds: number | null; created_at: string | null }) => ({
        id: h.id,
        title: h.title || `Hearing ${h.id}`,
        state_code: 'FL',
        hearing_date: h.hearing_date,
        created_at: h.created_at,
        duration_seconds: h.duration_seconds,
      }));

      setStageHearings(hearings);
    } catch (err) {
      console.error('Failed to load completed hearings:', err);
      setStageHearings([]);
    } finally {
      setStageHearingsLoading(false);
    }
  };

  const loadSkippedHearings = async () => {
    setStageHearingsLoading(true);
    try {
      const res = await fetch(`${API_URL}/admin/hearings?status=skipped&page_size=100`);
      if (!res.ok) throw new Error('Failed to load hearings');
      const data = await res.json();

      const hearings = (data.items || []).map((h: { id: number; title: string | null; hearing_date: string | null }) => ({
        id: h.id,
        title: h.title || `Hearing ${h.id}`,
        state_code: 'FL',
        hearing_date: h.hearing_date,
        created_at: null,
        duration_seconds: null,
      }));

      setStageHearings(hearings);
    } catch (err) {
      console.error('Failed to load skipped hearings:', err);
      setStageHearings([]);
    } finally {
      setStageHearingsLoading(false);
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

  const toggleStageExpand = (stageKey: string) => {
    if (expandedStage === stageKey) {
      setExpandedStage(null);
      setStageHearings([]);
      setSelectedHearings(new Set());
    } else {
      setExpandedStage(stageKey);
      setSelectedHearings(new Set());

      if (stageKey === 'complete') {
        loadCompletedHearings();
      } else if (stageKey === 'skipped') {
        loadSkippedHearings();
      } else {
        const stage = STAGES.find(s => s.key === stageKey);
        if (stage) {
          loadStageHearings(stage.action);
        }
      }
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

    if (status?.status === 'running') {
      setError('Pipeline is currently running. Please wait or stop it first.');
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
        throw new Error(data.detail || 'Failed to run stage');
      }

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
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/retry`, { method: 'POST' });
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
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/skip`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to skip hearing');
      }
      setStageHearings(prev => prev.filter(h => h.id !== hearingId));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip hearing');
    }
  };

  const restoreHearing = async (hearingId: number) => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/hearings/${hearingId}/retry`, { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to restore hearing');
      }
      setStageHearings(prev => prev.filter(h => h.id !== hearingId));
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to restore hearing');
    }
  };

  const retryAllErrors = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/retry-all`, { method: 'POST' });
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
    setDocketDiscoveryLoading(true);
    setDocketDiscoveryStatus(null);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/start?year=${docketYear}&limit=500`, {
        method: 'POST',
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to start docket discovery');
      }

      const result = await res.json();
      setDocketDiscoveryStatus(result);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start docket discovery');
    } finally {
      setDocketDiscoveryLoading(false);
    }
  };

  const verifyDocket = async () => {
    if (!verifyDocketNumber.trim()) return;

    setVerifyLoading(true);
    setVerifyResult(null);
    try {
      const res = await fetch(`${API_URL}/admin/pipeline/docket-discovery/verify?docket_number=${encodeURIComponent(verifyDocketNumber.trim())}&save=true`);

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to verify docket');
      }

      const result = await res.json();
      setVerifyResult(result);
      if (result.valid) {
        await loadData();
      }
    } catch (err) {
      setVerifyResult({
        valid: false,
        docket_number: verifyDocketNumber,
        error: err instanceof Error ? err.message : 'Failed to verify docket',
      });
    } finally {
      setVerifyLoading(false);
    }
  };

  const searchThunderstone = async () => {
    if (!thunderstoneQuery.trim()) return;

    setThunderstoneLoading(true);
    setThunderstoneResults([]);
    try {
      const res = await fetch(`${API_URL}/admin/thunderstone/search?query=${encodeURIComponent(thunderstoneQuery.trim())}&limit=20`);

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Failed to search Thunderstone');
      }

      const result = await res.json();
      setThunderstoneResults(result.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to search Thunderstone');
    } finally {
      setThunderstoneLoading(false);
    }
  };

  const getStageCount = (pendingStatus: string) => {
    if (pendingStatus === 'pending') {
      return status?.stage_counts?.['pending'] || status?.stage_counts?.['downloaded'] || 0;
    }
    return status?.stage_counts?.[pendingStatus] || 0;
  };

  const getCompleteCount = () => status?.stage_counts?.['complete'] || status?.stage_counts?.['analyzed'] || 0;
  const getErrorCount = () => status?.stage_counts?.['error'] || 0;

  const sortedStageHearings = [...stageHearings].sort((a, b) => {
    let comparison = 0;
    switch (sortField) {
      case 'hearing_date':
        const dateA = a.hearing_date ? new Date(a.hearing_date).getTime() : 0;
        const dateB = b.hearing_date ? new Date(b.hearing_date).getTime() : 0;
        comparison = dateA - dateB;
        break;
      case 'title':
        comparison = (a.title || '').localeCompare(b.title || '');
        break;
      default:
        comparison = 0;
    }
    return sortDirection === 'desc' ? -comparison : comparison;
  });

  const handleSortChange = (field: SortField) => {
    if (field === sortField) {
      setSortDirection(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const isRunning = status?.status === 'running';

  if (loading) {
    return (
      <PageLayout activeTab="runs">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  const StageIcon = ({ stageKey }: { stageKey: string }) => {
    switch (stageKey) {
      case 'discover': return <Rss size={20} />;
      case 'transcribe': return <Mic size={20} />;
      case 'analyze': return <Sparkles size={20} />;
      default: return <FileText size={20} />;
    }
  };

  return (
    <PageLayout activeTab="runs">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 700, margin: 0 }}>Pipeline Control</h1>
          <p style={{ color: 'var(--gray-500)', margin: '0.25rem 0 0 0', fontSize: '0.9rem' }}>
            Florida PSC Hearing Processing Pipeline
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span
            className={`badge ${isRunning ? 'badge-success' : 'badge-secondary'}`}
            style={{ padding: '0.4rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
          >
            {isRunning && <Loader2 size={14} className="animate-spin" />}
            {status?.status || 'idle'}
          </span>
          <select
            value={runLimit}
            onChange={(e) => setRunLimit(parseInt(e.target.value, 10))}
            style={{
              padding: '0.4rem 0.75rem',
              borderRadius: '6px',
              border: '1px solid var(--gray-300)',
              fontSize: '0.85rem',
              background: 'white',
            }}
          >
            <option value={1}>1 at a time</option>
            <option value={5}>5 hearings</option>
            <option value={10}>10 hearings</option>
            <option value={25}>25 hearings</option>
          </select>
          <button onClick={loadData} className="btn btn-secondary" style={{ padding: '0.5rem' }}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={20} />
          <div style={{ flex: 1 }}>{error}</div>
          <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '1.25rem' }}>&times;</button>
        </div>
      )}

      {/* Active Processing Banner */}
      {isRunning && (
        <div className="card" style={{
          marginBottom: '1rem',
          padding: '1rem 1.25rem',
          background: 'linear-gradient(90deg, var(--primary-50) 0%, var(--primary-100) 100%)',
          border: '1px solid var(--primary-200)',
        }}>
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
              {' '}Stop
            </button>
          </div>
          <div style={{ marginTop: '0.75rem', height: '4px', background: 'var(--primary-200)', borderRadius: '2px', overflow: 'hidden' }}>
            <div style={{ height: '100%', width: '30%', background: 'var(--primary)', borderRadius: '2px', animation: 'progress-indeterminate 1.5s ease-in-out infinite' }} />
          </div>
        </div>
      )}

      {/* Summary Stats Row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <FileText size={18} style={{ color: 'var(--primary)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Total Hearings</span>
          </div>
          <div className="stat-value">{dataQuality?.total_hearings || 0}</div>
        </div>
        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <Mic size={18} style={{ color: 'var(--info)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Transcribed</span>
          </div>
          <div className="stat-value">{dataQuality?.hearings_with_transcripts || 0}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{dataQuality?.transcript_coverage || 0}% coverage</div>
        </div>
        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <Sparkles size={18} style={{ color: 'var(--success)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Analyzed</span>
          </div>
          <div className="stat-value">{dataQuality?.hearings_with_analysis || 0}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{dataQuality?.analysis_coverage || 0}% coverage</div>
        </div>
        <div className="stat-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
            <DollarSign size={18} style={{ color: 'var(--warning)' }} />
            <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Total Cost</span>
          </div>
          <div className="stat-value">${(status?.total_cost_usd || 0).toFixed(2)}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>${(status?.cost_today || 0).toFixed(4)} today</div>
        </div>
      </div>

      {/* Source Management Card */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <div
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setShowSources(!showSources)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Settings size={20} style={{ color: 'var(--primary)' }} />
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Data Sources</h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                {sources.length} source{sources.length !== 1 ? 's' : ''} configured
              </p>
            </div>
          </div>
          <ChevronDown size={20} style={{ color: 'var(--gray-400)', transform: showSources ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }} />
        </div>

        {showSources && (
          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--gray-200)', paddingTop: '1rem' }}>
            {sources.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--gray-500)' }}>No sources configured</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {sources.map(source => (
                  <div key={source.id} style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '1rem',
                    padding: '0.75rem',
                    background: 'var(--gray-50)',
                    borderRadius: '8px',
                    border: '1px solid var(--gray-200)',
                  }}>
                    <Rss size={18} style={{ color: 'var(--info)' }} />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600 }}>{source.name}</div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                        {source.source_type} • {source.url}
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                      {source.last_checked_at && (
                        <div>Last checked: {new Date(source.last_checked_at).toLocaleDateString()}</div>
                      )}
                    </div>
                    <span className={`badge ${source.status === 'active' ? 'badge-success' : 'badge-secondary'}`}>
                      {source.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Docket Discovery Card */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
        <div
          style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
          onClick={() => setShowDocketDiscovery(!showDocketDiscovery)}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <Database size={20} style={{ color: 'var(--info)' }} />
            <div>
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Docket Discovery</h3>
              <p style={{ margin: 0, fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                {docketStats?.total_dockets || 0} dockets in database
              </p>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {docketDiscoveryLoading && (
              <span className="badge badge-info" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                <Loader2 size={12} className="animate-spin" /> Scanning...
              </span>
            )}
            <ChevronDown size={20} style={{ color: 'var(--gray-400)', transform: showDocketDiscovery ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }} />
          </div>
        </div>

        {showDocketDiscovery && (
          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--gray-200)', paddingTop: '1rem' }}>
            {/* Docket Stats */}
            {docketStats && docketStats.total_dockets > 0 && (
              <div style={{ marginBottom: '1.25rem' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', marginBottom: '1rem' }}>
                  {Object.entries(docketStats.by_sector || {}).slice(0, 4).map(([sector, count]) => (
                    <div key={sector} style={{
                      padding: '0.75rem',
                      background: 'var(--gray-50)',
                      borderRadius: '8px',
                      textAlign: 'center',
                    }}>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--primary)' }}>{count}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {sector === 'E' ? 'Electric' : sector === 'G' ? 'Gas' : sector === 'T' ? 'Telecom' : sector === 'W' ? 'Water' : sector}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Year breakdown */}
                {Object.keys(docketStats.by_year || {}).length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.5rem' }}>By Year</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                      {Object.entries(docketStats.by_year).sort(([a], [b]) => Number(b) - Number(a)).slice(0, 6).map(([year, count]) => (
                        <span key={year} className="badge badge-secondary" style={{ fontSize: '0.75rem' }}>
                          {year}: {count}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Scan Controls */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '1rem',
              padding: '1rem',
              background: 'var(--info-50)',
              borderRadius: '8px',
              marginBottom: '1rem',
            }}>
              <FolderSearch size={24} style={{ color: 'var(--info)' }} />
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>Scan Florida PSC</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>
                  Discover dockets from the ClerkOffice API
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <select
                  value={docketYear}
                  onChange={(e) => setDocketYear(parseInt(e.target.value, 10))}
                  style={{
                    padding: '0.4rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.85rem',
                    background: 'white',
                  }}
                >
                  {Array.from({ length: 10 }, (_, i) => new Date().getFullYear() - i).map(year => (
                    <option key={year} value={year}>{year}</option>
                  ))}
                </select>
                <button
                  onClick={startDocketDiscovery}
                  disabled={docketDiscoveryLoading}
                  className="btn btn-primary"
                  style={{ padding: '0.5rem 1rem', background: 'var(--info)' }}
                >
                  {docketDiscoveryLoading ? (
                    <><Loader2 size={14} className="animate-spin" /> Scanning...</>
                  ) : (
                    <><Search size={14} /> Scan PSC</>
                  )}
                </button>
              </div>
            </div>

            {/* Discovery Result */}
            {docketDiscoveryStatus && (
              <div style={{
                padding: '0.75rem',
                background: (docketDiscoveryStatus.errors?.length || 0) > 0 ? 'var(--danger-50)' : 'var(--success-bg)',
                borderRadius: '6px',
                marginBottom: '1rem',
                fontSize: '0.85rem',
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  {(docketDiscoveryStatus.errors?.length || 0) > 0 ? (
                    <AlertCircle size={16} style={{ color: 'var(--danger)' }} />
                  ) : (
                    <CheckCircle2 size={16} style={{ color: 'var(--success)' }} />
                  )}
                  <span>
                    Found {docketDiscoveryStatus.dockets_found || docketDiscoveryStatus.total_scraped || 0} dockets
                    {(docketDiscoveryStatus.dockets_new || docketDiscoveryStatus.new_dockets || 0) > 0 && ` (+${docketDiscoveryStatus.dockets_new || docketDiscoveryStatus.new_dockets} new)`}
                    {(docketDiscoveryStatus.dockets_updated || docketDiscoveryStatus.updated_dockets || 0) > 0 && ` (${docketDiscoveryStatus.dockets_updated || docketDiscoveryStatus.updated_dockets} updated)`}
                  </span>
                </div>
                {(docketDiscoveryStatus.errors?.length || 0) > 0 && (
                  <div style={{ marginTop: '0.5rem', color: 'var(--danger-600)' }}>
                    {docketDiscoveryStatus.errors?.join(', ')}
                  </div>
                )}
              </div>
            )}

            {/* Verify Individual Docket */}
            <div style={{
              padding: '1rem',
              background: 'var(--gray-50)',
              borderRadius: '8px',
              marginBottom: '1rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <FileCheck size={18} style={{ color: 'var(--gray-600)' }} />
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Verify Docket</span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text"
                  placeholder="e.g. 20250001-EI"
                  value={verifyDocketNumber}
                  onChange={(e) => setVerifyDocketNumber(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && verifyDocket()}
                  style={{
                    flex: 1,
                    padding: '0.5rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.9rem',
                  }}
                />
                <button
                  onClick={verifyDocket}
                  disabled={verifyLoading || !verifyDocketNumber.trim()}
                  className="btn btn-secondary"
                  style={{ padding: '0.5rem 1rem' }}
                >
                  {verifyLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  {' '}Verify
                </button>
              </div>

              {verifyResult && (
                <div style={{
                  marginTop: '0.75rem',
                  padding: '0.75rem',
                  background: verifyResult.valid ? 'var(--success-bg)' : 'var(--danger-50)',
                  borderRadius: '6px',
                  fontSize: '0.85rem',
                }}>
                  {verifyResult.valid ? (
                    <>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                        <CheckCircle2 size={14} style={{ color: 'var(--success)' }} />
                        <strong>{verifyResult.docket_number}</strong>
                        <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>{verifyResult.status}</span>
                      </div>
                      <div style={{ color: 'var(--gray-700)' }}>{verifyResult.title}</div>
                      {verifyResult.filed_date && (
                        <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                          Filed: {verifyResult.filed_date}
                        </div>
                      )}
                    </>
                  ) : (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--danger-600)' }}>
                      <X size={14} />
                      {verifyResult.error || 'Docket not found'}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Thunderstone Search */}
            <div style={{
              padding: '1rem',
              background: 'var(--gray-50)',
              borderRadius: '8px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <Zap size={18} style={{ color: 'var(--warning)' }} />
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>Thunderstone Document Search</span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text"
                  placeholder="Search PSC documents..."
                  value={thunderstoneQuery}
                  onChange={(e) => setThunderstoneQuery(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && searchThunderstone()}
                  style={{
                    flex: 1,
                    padding: '0.5rem 0.75rem',
                    borderRadius: '6px',
                    border: '1px solid var(--gray-300)',
                    fontSize: '0.9rem',
                  }}
                />
                <button
                  onClick={searchThunderstone}
                  disabled={thunderstoneLoading || !thunderstoneQuery.trim()}
                  className="btn btn-secondary"
                  style={{ padding: '0.5rem 1rem' }}
                >
                  {thunderstoneLoading ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                  {' '}Search
                </button>
              </div>

              {thunderstoneResults.length > 0 && (
                <div style={{ marginTop: '0.75rem', maxHeight: '200px', overflowY: 'auto' }}>
                  {thunderstoneResults.map((result, idx) => (
                    <div key={idx} style={{
                      padding: '0.5rem 0.75rem',
                      borderBottom: '1px solid var(--gray-200)',
                      fontSize: '0.85rem',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <a href={result.url} target="_blank" rel="noopener noreferrer"
                          style={{ color: 'var(--primary)', fontWeight: 500, textDecoration: 'none' }}>
                          {result.title}
                        </a>
                        {result.docket_number && (
                          <span className="badge badge-secondary" style={{ fontSize: '0.7rem' }}>
                            {result.docket_number}
                          </span>
                        )}
                      </div>
                      {result.description && (
                        <div style={{ fontSize: '0.8rem', color: 'var(--gray-600)', marginTop: '0.25rem' }}>
                          {result.description.length > 100 ? result.description.substring(0, 100) + '...' : result.description}
                        </div>
                      )}
                      {result.date && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                          {result.date}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Pipeline Stages */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
        <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Activity size={18} style={{ color: 'var(--primary)' }} />
          Pipeline Workflow
        </h3>

        <div style={{ display: 'flex', alignItems: 'stretch', gap: '0.5rem', overflowX: 'auto', paddingBottom: '0.5rem' }}>
          {STAGES.map((stage, idx) => {
            const isDiscover = stage.key === 'discover';
            const count = isDiscover ? 0 : getStageCount(stage.pendingStatus);
            const isActive = status?.current_stage === stage.key;
            const isExpanded = expandedStage === stage.key;
            const canExpand = !isDiscover && count > 0;

            return (
              <div key={stage.key} style={{ display: 'flex', alignItems: 'center' }}>
                <div
                  onClick={() => canExpand && toggleStageExpand(stage.key)}
                  title={stage.description}
                  style={{
                    padding: '1rem',
                    borderRadius: '10px',
                    background: isDiscover
                      ? (actionLoading === 'discover' ? 'var(--info-100)' : 'var(--info-50)')
                      : isExpanded ? 'var(--primary-100)' : isActive ? 'var(--primary)' : 'var(--gray-50)',
                    color: isActive && !isExpanded && !isDiscover ? 'white' : isDiscover ? 'var(--info-700)' : 'var(--gray-700)',
                    border: isDiscover
                      ? '2px solid var(--info-300)'
                      : isExpanded ? '2px solid var(--primary)' : isActive ? 'none' : '1px solid var(--gray-200)',
                    minWidth: '150px',
                    textAlign: 'center',
                    cursor: canExpand ? 'pointer' : 'default',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    <StageIcon stageKey={stage.key} />
                    <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>{stage.label}</span>
                    {canExpand && (
                      <ChevronDown size={14} style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.15s ease' }} />
                    )}
                  </div>

                  {isDiscover ? (
                    <>
                      {lastDiscoverResult ? (
                        <div style={{ marginBottom: '0.75rem' }}>
                          <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)' }}>
                            +{lastDiscoverResult.new}
                          </div>
                          <div style={{ fontSize: '0.75rem', opacity: 0.8 }}>
                            {lastDiscoverResult.found} in feed
                          </div>
                        </div>
                      ) : (
                        <div style={{ marginBottom: '0.75rem', opacity: 0.8, fontSize: '0.85rem' }}>
                          {scraperStatus?.last_run ? (
                            <div>
                              <Clock size={14} style={{ verticalAlign: 'middle', marginRight: '0.25rem' }} />
                              {new Date(scraperStatus.last_run).toLocaleDateString()}
                            </div>
                          ) : (
                            <span>Scan for new hearings</span>
                          )}
                        </div>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); runStage(stage.action); }}
                        disabled={actionLoading !== null}
                        className="btn btn-primary"
                        style={{ padding: '0.5rem 1rem', fontSize: '0.85rem', width: '100%', background: 'var(--info)' }}
                      >
                        {actionLoading === 'discover' ? (
                          <><Loader2 size={14} className="animate-spin" /> Scanning...</>
                        ) : (
                          <><Search size={14} /> Scan RSS</>
                        )}
                      </button>
                    </>
                  ) : (
                    <>
                      <div style={{ fontSize: '2.25rem', fontWeight: 700, lineHeight: 1.1 }}>{count}</div>
                      <div style={{ fontSize: '0.75rem', opacity: 0.7, marginBottom: '0.75rem' }}>pending</div>
                      <button
                        onClick={(e) => { e.stopPropagation(); runStage(stage.action); }}
                        disabled={actionLoading !== null || isRunning || count === 0}
                        className="btn btn-primary"
                        style={{
                          padding: '0.5rem 1rem',
                          fontSize: '0.85rem',
                          width: '100%',
                          opacity: count === 0 ? 0.5 : 1,
                        }}
                      >
                        {actionLoading === stage.action ? (
                          <Loader2 size={14} className="animate-spin" />
                        ) : (
                          <><Play size={14} /> Run {runLimit}</>
                        )}
                      </button>
                    </>
                  )}
                </div>

                {idx < STAGES.length - 1 && (
                  <div style={{ width: '30px', height: '2px', background: 'var(--gray-300)', margin: '0 0.25rem' }} />
                )}
              </div>
            );
          })}

          {/* Arrow to Complete */}
          <div style={{ width: '30px', height: '2px', background: 'var(--gray-300)', margin: '0 0.25rem', alignSelf: 'center' }} />

          {/* Complete */}
          <div
            onClick={() => getCompleteCount() > 0 && toggleStageExpand('complete')}
            style={{
              padding: '1rem',
              borderRadius: '10px',
              background: expandedStage === 'complete' ? 'var(--success)' : 'var(--success-bg)',
              border: expandedStage === 'complete' ? '2px solid var(--success)' : '2px solid var(--success-200)',
              minWidth: '150px',
              textAlign: 'center',
              cursor: getCompleteCount() > 0 ? 'pointer' : 'default',
              color: expandedStage === 'complete' ? 'white' : 'var(--success-700)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <CheckCircle2 size={20} />
              <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>Complete</span>
              {getCompleteCount() > 0 && (
                <ChevronDown size={14} style={{ transform: expandedStage === 'complete' ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.15s ease' }} />
              )}
            </div>
            <div style={{ fontSize: '2.25rem', fontWeight: 700, lineHeight: 1.1 }}>{getCompleteCount()}</div>
            <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>processed</div>
          </div>

          {/* Skipped */}
          <div
            onClick={() => toggleStageExpand('skipped')}
            style={{
              padding: '1rem',
              borderRadius: '10px',
              background: expandedStage === 'skipped' ? 'var(--gray-600)' : 'var(--gray-100)',
              border: '1px solid var(--gray-300)',
              minWidth: '100px',
              textAlign: 'center',
              cursor: 'pointer',
              color: expandedStage === 'skipped' ? 'white' : 'var(--gray-600)',
              marginLeft: '0.5rem',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem', marginBottom: '0.25rem' }}>
              <Ban size={16} />
              <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Skipped</span>
            </div>
            <div style={{ fontSize: '1.25rem', fontWeight: 600 }}>-</div>
          </div>

          {/* Errors */}
          {getErrorCount() > 0 && (
            <div
              onClick={() => setShowErrors(!showErrors)}
              style={{
                padding: '1rem',
                borderRadius: '10px',
                background: 'var(--danger-50)',
                border: '2px solid var(--danger-200)',
                minWidth: '100px',
                textAlign: 'center',
                cursor: 'pointer',
                color: 'var(--danger-700)',
                marginLeft: '0.5rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem', marginBottom: '0.25rem' }}>
                <AlertCircle size={16} />
                <span style={{ fontWeight: 600, fontSize: '0.85rem' }}>Errors</span>
              </div>
              <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>{getErrorCount()}</div>
            </div>
          )}
        </div>

        {/* Expanded Stage Panel */}
        {expandedStage && expandedStage !== 'discover' && (
          <div style={{
            marginTop: '1rem',
            padding: '1rem',
            background: expandedStage === 'complete' ? 'var(--success-bg)' : expandedStage === 'skipped' ? 'var(--gray-100)' : 'var(--gray-50)',
            borderRadius: '8px',
            border: `1px solid ${expandedStage === 'complete' ? 'var(--success-200)' : 'var(--gray-200)'}`,
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span style={{ fontWeight: 600 }}>
                  {expandedStage === 'complete' ? 'Completed Hearings' :
                   expandedStage === 'skipped' ? 'Skipped Hearings' :
                   `Select hearings to ${expandedStage}`}
                </span>
                {stageHearings.length > 0 && expandedStage !== 'complete' && expandedStage !== 'skipped' && (
                  <button onClick={selectAllHearings} className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}>
                    {selectedHearings.size === stageHearings.length ? 'Deselect All' : 'Select All'}
                  </button>
                )}
              </div>
              <button onClick={() => { setExpandedStage(null); setStageHearings([]); setSelectedHearings(new Set()); }}
                style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}>
                <X size={18} color="var(--gray-500)" />
              </button>
            </div>

            {stageHearingsLoading ? (
              <div style={{ padding: '2rem', textAlign: 'center' }}>
                <Loader2 size={24} className="animate-spin" style={{ color: 'var(--gray-400)' }} />
              </div>
            ) : stageHearings.length === 0 ? (
              <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                No hearings in this stage
              </div>
            ) : (
              <>
                <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid var(--gray-200)', borderRadius: '6px', background: 'white' }}>
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: expandedStage === 'complete' || expandedStage === 'skipped' ? '1fr 100px 80px' : '40px 1fr 100px 80px',
                    padding: '0.5rem 0.75rem',
                    background: 'var(--gray-100)',
                    borderBottom: '1px solid var(--gray-200)',
                    fontSize: '0.75rem',
                    fontWeight: 600,
                    color: 'var(--gray-600)',
                    position: 'sticky',
                    top: 0,
                  }}>
                    {expandedStage !== 'complete' && expandedStage !== 'skipped' && <div></div>}
                    <div onClick={() => handleSortChange('title')} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      Title <ArrowUpDown size={12} />
                    </div>
                    <div onClick={() => handleSortChange('hearing_date')} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                      Date <ArrowUpDown size={12} />
                    </div>
                    <div>Actions</div>
                  </div>

                  {sortedStageHearings.map((hearing) => (
                    <div
                      key={hearing.id}
                      style={{
                        display: 'grid',
                        gridTemplateColumns: expandedStage === 'complete' || expandedStage === 'skipped' ? '1fr 100px 80px' : '40px 1fr 100px 80px',
                        alignItems: 'center',
                        padding: '0.5rem 0.75rem',
                        borderBottom: '1px solid var(--gray-100)',
                        background: selectedHearings.has(hearing.id) ? 'var(--primary-50)' : 'transparent',
                      }}
                    >
                      {expandedStage !== 'complete' && expandedStage !== 'skipped' && (
                        <input
                          type="checkbox"
                          checked={selectedHearings.has(hearing.id)}
                          onChange={() => toggleHearingSelection(hearing.id)}
                          style={{ width: '16px', height: '16px', cursor: 'pointer' }}
                        />
                      )}
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.875rem', paddingRight: '0.5rem' }}>
                        {hearing.title}
                      </span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {hearing.hearing_date || '-'}
                      </span>
                      <div style={{ display: 'flex', gap: '0.25rem' }}>
                        <button
                          onClick={() => openHearingDetail(hearing.id)}
                          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', color: 'var(--gray-400)' }}
                          title="View details"
                        >
                          <Eye size={16} />
                        </button>
                        {expandedStage === 'skipped' ? (
                          <button
                            onClick={() => restoreHearing(hearing.id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', color: 'var(--success)' }}
                            title="Restore hearing"
                          >
                            <RotateCcw size={16} />
                          </button>
                        ) : expandedStage !== 'complete' && (
                          <button
                            onClick={() => skipHearing(hearing.id)}
                            style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem', color: 'var(--gray-400)' }}
                            title="Skip hearing"
                          >
                            <SkipForward size={16} />
                          </button>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {selectedHearings.size > 0 && expandedStage !== 'complete' && expandedStage !== 'skipped' && (
                  <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                    <button
                      onClick={() => {
                        const stage = STAGES.find(s => s.key === expandedStage);
                        if (stage) runSelectedHearings(stage.action);
                      }}
                      disabled={actionLoading !== null || isRunning}
                      className="btn btn-primary"
                      style={{ padding: '0.5rem 1rem' }}
                    >
                      {actionLoading ? (
                        <><Loader2 size={14} className="animate-spin" /> Processing...</>
                      ) : (
                        <><Play size={14} /> {expandedStage === 'transcribe' ? 'Transcribe' : 'Analyze'} {selectedHearings.size} Selected</>
                      )}
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

      {/* Activity & Errors */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
        {/* Recent Activity */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <div
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showActivity ? '1rem' : 0, cursor: 'pointer' }}
            onClick={() => setShowActivity(!showActivity)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Activity size={18} style={{ color: 'var(--primary)' }} />
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Recent Activity</h3>
              <span className="badge badge-secondary">{activity.length}</span>
            </div>
            <ChevronDown size={16} style={{ transform: showActivity ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.15s ease', color: 'var(--gray-400)' }} />
          </div>

          {showActivity && (
            <div style={{ maxHeight: '250px', overflowY: 'auto' }}>
              {activity.length === 0 ? (
                <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>No recent activity</div>
              ) : (
                activity.map((item) => (
                  <div key={item.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--gray-100)', fontSize: '0.85rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '200px' }}>
                        {item.hearing_title}
                      </span>
                      <span className={`badge ${item.status === 'completed' ? 'badge-success' : 'badge-info'}`}>{item.stage}</span>
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                      {item.completed_at && new Date(item.completed_at).toLocaleString()}
                      {item.cost_usd && ` · $${item.cost_usd.toFixed(4)}`}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        {/* Errors */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <div
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: showErrors ? '1rem' : 0, cursor: 'pointer' }}
            onClick={() => setShowErrors(!showErrors)}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <AlertCircle size={18} style={{ color: errors.length > 0 ? 'var(--danger)' : 'var(--gray-400)' }} />
              <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600 }}>Errors</h3>
              {errors.length > 0 && <span className="badge badge-danger">{errors.length}</span>}
            </div>
            <ChevronDown size={16} style={{ transform: showErrors ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.15s ease', color: 'var(--gray-400)' }} />
          </div>

          {showErrors && (
            <>
              {errors.length > 0 && (
                <button onClick={retryAllErrors} className="btn btn-secondary" style={{ marginBottom: '0.75rem', fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}>
                  <RotateCcw size={14} /> Retry All
                </button>
              )}
              <div style={{ maxHeight: '200px', overflowY: 'auto' }}>
                {errors.length === 0 ? (
                  <div style={{ padding: '1rem', textAlign: 'center', color: 'var(--gray-500)' }}>No errors</div>
                ) : (
                  errors.map((item) => (
                    <div key={item.hearing_id} style={{
                      padding: '0.5rem 0.75rem',
                      background: 'var(--danger-50)',
                      borderRadius: '6px',
                      marginBottom: '0.5rem',
                      fontSize: '0.85rem',
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ fontWeight: 500 }}>{item.hearing_title}</span>
                        <button onClick={() => retryHearing(item.hearing_id)} className="btn btn-secondary" style={{ padding: '0.2rem 0.5rem', fontSize: '0.7rem' }}>
                          <RotateCcw size={12} /> Retry
                        </button>
                      </div>
                      {item.error_message && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--danger-600)', marginTop: '0.25rem' }}>{item.error_message}</div>
                      )}
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Hearing Detail Modal */}
      {detailModalOpen && (
        <div
          onClick={closeHearingDetail}
          style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0, 0, 0, 0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '700px',
              width: '90%',
              maxHeight: '90vh',
              background: 'white',
              borderRadius: '12px',
              boxShadow: '0 4px 20px rgba(0,0,0,0.2)',
              display: 'flex',
              flexDirection: 'column',
            }}
          >
            <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--gray-200)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem' }}>Hearing Details</h3>
              <button onClick={closeHearingDetail} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: '0.25rem' }}>
                <X size={20} />
              </button>
            </div>
            <div style={{ padding: '1.25rem', overflowY: 'auto', flex: 1 }}>
              {detailLoading ? (
                <div style={{ padding: '2rem', textAlign: 'center' }}>
                  <Loader2 size={32} className="animate-spin" style={{ color: 'var(--primary)' }} />
                </div>
              ) : detailHearing ? (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  <div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                      <span className="badge badge-primary">FL</span>
                      <span className={`badge ${detailHearing.has_analysis ? 'badge-success' : detailHearing.segment_count > 0 ? 'badge-info' : 'badge-warning'}`}>
                        {detailHearing.has_analysis ? 'Analyzed' : detailHearing.segment_count > 0 ? 'Transcribed' : 'Pending'}
                      </span>
                    </div>
                    <h4 style={{ margin: '0 0 0.5rem 0', fontSize: '1rem', fontWeight: 600 }}>{detailHearing.title}</h4>
                    <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
                      {detailHearing.hearing_date && <span>Date: {detailHearing.hearing_date} · </span>}
                      {(detailHearing.processing_cost_usd || detailHearing.analysis_cost) && (
                        <span>Cost: ${((detailHearing.processing_cost_usd || 0) + (detailHearing.analysis_cost || 0)).toFixed(4)}</span>
                      )}
                    </div>
                    {detailHearing.video_url && (
                      <a href={detailHearing.video_url} target="_blank" rel="noopener noreferrer"
                        style={{ fontSize: '0.85rem', color: 'var(--primary)', display: 'inline-flex', alignItems: 'center', gap: '0.25rem', marginTop: '0.5rem' }}>
                        <ExternalLink size={14} /> View source
                      </a>
                    )}
                  </div>

                  {detailHearing.jobs && detailHearing.jobs.length > 0 && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>Processing History</h5>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                        {detailHearing.jobs.map((job) => (
                          <div key={job.id} style={{
                            padding: '0.75rem',
                            background: job.status === 'error' ? 'var(--danger-50)' : 'var(--gray-50)',
                            borderRadius: '6px',
                            border: job.status === 'error' ? '1px solid var(--danger-200)' : '1px solid var(--gray-200)',
                          }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                                <span style={{ fontWeight: 600, textTransform: 'capitalize' }}>{job.stage}</span>
                                <span className={`badge ${job.status === 'completed' ? 'badge-success' : job.status === 'error' ? 'badge-danger' : 'badge-secondary'}`}>
                                  {job.status}
                                </span>
                              </div>
                              {job.cost_usd !== null && job.cost_usd > 0 && (
                                <span style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>${job.cost_usd.toFixed(4)}</span>
                              )}
                            </div>
                            {job.details && <div style={{ fontSize: '0.8rem', color: 'var(--gray-600)', marginTop: '0.25rem' }}>{job.details}</div>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailHearing.transcript_preview && detailHearing.transcript_preview.length > 0 && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>
                        Transcript Preview ({detailHearing.segment_count} segments)
                      </h5>
                      <div style={{ padding: '0.75rem', background: 'var(--gray-50)', borderRadius: '6px', fontSize: '0.85rem', maxHeight: '150px', overflowY: 'auto', lineHeight: 1.5 }}>
                        {detailHearing.transcript_preview.map((seg, idx) => (
                          <div key={idx} style={{ marginBottom: '0.5rem' }}>
                            <span style={{ fontWeight: 600, color: 'var(--primary)' }}>{seg.speaker}:</span> {seg.text}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {detailHearing.analysis && (
                    <div>
                      <h5 style={{ margin: '0 0 0.75rem 0', fontSize: '0.9rem', fontWeight: 600, color: 'var(--gray-700)' }}>Analysis</h5>
                      {detailHearing.analysis.one_sentence_summary && (
                        <div style={{ padding: '0.75rem', background: 'var(--primary-50)', borderRadius: '6px', fontSize: '0.9rem', fontWeight: 500, marginBottom: '0.75rem', borderLeft: '3px solid var(--primary)' }}>
                          {detailHearing.analysis.one_sentence_summary}
                        </div>
                      )}
                      <div style={{ padding: '0.75rem', background: 'var(--gray-50)', borderRadius: '6px', fontSize: '0.85rem', lineHeight: 1.5, maxHeight: '150px', overflowY: 'auto' }}>
                        {detailHearing.analysis.summary || 'No summary available'}
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginTop: '0.75rem' }}>
                        {detailHearing.analysis.hearing_type && (
                          <div><strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Type:</strong> <span className="badge badge-info">{detailHearing.analysis.hearing_type}</span></div>
                        )}
                        {detailHearing.analysis.utility_name && (
                          <div><strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Utility:</strong> <span style={{ fontSize: '0.85rem' }}>{detailHearing.analysis.utility_name}</span></div>
                        )}
                        {detailHearing.analysis.commissioner_mood && (
                          <div><strong style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>Mood:</strong> <span className="badge badge-secondary">{detailHearing.analysis.commissioner_mood}</span></div>
                        )}
                      </div>
                      {detailHearing.analysis.likely_outcome && (
                        <div style={{ marginTop: '0.75rem' }}>
                          <strong style={{ fontSize: '0.85rem' }}>Likely Outcome:</strong>
                          <div style={{ padding: '0.5rem 0.75rem', background: 'var(--gray-50)', borderRadius: '4px', fontSize: '0.85rem', marginTop: '0.25rem' }}>
                            {detailHearing.analysis.likely_outcome}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div style={{ textAlign: 'center', color: 'var(--gray-500)' }}>Failed to load hearing details</div>
              )}
            </div>
            <div style={{ padding: '1rem 1.25rem', borderTop: '1px solid var(--gray-200)', display: 'flex', justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                {detailHearing && !detailHearing.has_analysis && (
                  <button onClick={() => { skipHearing(detailHearing.id); closeHearingDetail(); }} className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
                    <SkipForward size={14} /> Skip
                  </button>
                )}
              </div>
              <button onClick={closeHearingDetail} className="btn btn-secondary">Close</button>
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes progress-indeterminate {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(400%); }
        }
        .animate-spin {
          animation: spin 1s linear infinite;
        }
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </PageLayout>
  );
}
