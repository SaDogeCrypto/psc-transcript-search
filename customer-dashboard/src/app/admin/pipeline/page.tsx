'use client';

import { useEffect, useState, useCallback } from 'react';
import {
  AlertCircle,
  Play,
  Square,
  Pause,
  PlayCircle,
  RefreshCw,
  RotateCcw,
  SkipForward,
  CheckCircle2,
  Clock,
  Loader2,
  XCircle,
  ChevronRight,
} from 'lucide-react';
import { PageLayout } from '../components/Layout';
import {
  getPipelineStatus,
  getPipelineActivity,
  getPipelineErrors,
  startPipeline,
  stopPipeline,
  pausePipeline,
  resumePipeline,
  retryPipelineHearing,
  skipPipelineHearing,
  retryAllPipelineErrors,
  getStates,
  PipelineStatus,
  PipelineActivityItem,
  PipelineErrorItem,
  State,
} from '@/lib/admin-api';

const STAGES = ['discovered', 'downloading', 'transcribing', 'analyzing', 'extracting', 'complete'];
const STAGE_LABELS: Record<string, string> = {
  discovered: 'Discovered',
  downloading: 'Download',
  transcribing: 'Transcribe',
  analyzing: 'Analyze',
  extracting: 'Extract',
  complete: 'Complete',
};

export default function PipelinePage() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [activity, setActivity] = useState<PipelineActivityItem[]>([]);
  const [errors, setErrors] = useState<PipelineErrorItem[]>([]);
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<string | null>(null);

  // Start form state
  const [showStartForm, setShowStartForm] = useState(false);
  const [selectedStates, setSelectedStates] = useState<string[]>([]);
  const [maxCost, setMaxCost] = useState<string>('');
  const [maxHearings, setMaxHearings] = useState<string>('');
  const [onlyStage, setOnlyStage] = useState<string>('');

  const loadData = useCallback(async () => {
    try {
      const [statusData, activityData, errorsData, statesData] = await Promise.all([
        getPipelineStatus(),
        getPipelineActivity(50),
        getPipelineErrors(50),
        getStates(),
      ]);
      setStatus(statusData);
      setActivity(activityData.items);
      setErrors(errorsData.items);
      setStates(statesData);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000); // Poll every 5 seconds
    return () => clearInterval(interval);
  }, [loadData]);

  const handleStart = async () => {
    setActionLoading('start');
    try {
      await startPipeline({
        states: selectedStates.length > 0 ? selectedStates : undefined,
        max_cost: maxCost ? parseFloat(maxCost) : undefined,
        max_hearings: maxHearings ? parseInt(maxHearings) : undefined,
        only_stage: onlyStage || undefined,
      });
      setShowStartForm(false);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const handleStop = async () => {
    setActionLoading('stop');
    try {
      await stopPipeline();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const handlePause = async () => {
    setActionLoading('pause');
    try {
      await pausePipeline();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to pause pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const handleResume = async () => {
    setActionLoading('resume');
    try {
      await resumePipeline();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to resume pipeline');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRetry = async (hearingId: number) => {
    setActionLoading(`retry-${hearingId}`);
    try {
      await retryPipelineHearing(hearingId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry hearing');
    } finally {
      setActionLoading(null);
    }
  };

  const handleSkip = async (hearingId: number) => {
    setActionLoading(`skip-${hearingId}`);
    try {
      await skipPipelineHearing(hearingId);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to skip hearing');
    } finally {
      setActionLoading(null);
    }
  };

  const handleRetryAll = async () => {
    if (!confirm('Retry all failed hearings?')) return;
    setActionLoading('retry-all');
    try {
      await retryAllPipelineErrors();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to retry all');
    } finally {
      setActionLoading(null);
    }
  };

  const getStatusIcon = (pipelineStatus: string) => {
    switch (pipelineStatus) {
      case 'running':
        return <Loader2 size={20} className="animate-spin" style={{ color: 'var(--primary)' }} />;
      case 'paused':
        return <Pause size={20} style={{ color: 'var(--warning)' }} />;
      case 'stopping':
        return <Square size={20} style={{ color: 'var(--warning)' }} />;
      default:
        return <Clock size={20} style={{ color: 'var(--gray-500)' }} />;
    }
  };

  const getStatusBadge = (jobStatus: string) => {
    const classes: Record<string, string> = {
      complete: 'badge-success',
      error: 'badge-danger',
      running: 'badge-info',
    };
    return classes[jobStatus] || 'badge-warning';
  };

  if (loading) {
    return (
      <PageLayout activeTab="pipeline">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="pipeline">
      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={20} />
          <div><strong>Error:</strong> {error}</div>
        </div>
      )}

      {/* Header with controls */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {getStatusIcon(status?.status || 'idle')}
            Pipeline Orchestrator
            <span className={`badge ${status?.status === 'running' ? 'badge-success' : status?.status === 'paused' ? 'badge-warning' : 'badge-secondary'}`} style={{ marginLeft: '0.5rem' }}>
              {status?.status || 'idle'}
            </span>
          </h2>
          {status?.current_hearing_title && (
            <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>
              Processing: {status.current_hearing_title}
            </p>
          )}
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          {status?.status === 'idle' && (
            <button onClick={() => setShowStartForm(true)} className="btn btn-primary" disabled={actionLoading !== null}>
              <Play size={16} /> Start Pipeline
            </button>
          )}
          {status?.status === 'running' && (
            <>
              <button onClick={handlePause} className="btn btn-warning" disabled={actionLoading !== null}>
                <Pause size={16} /> Pause
              </button>
              <button onClick={handleStop} className="btn btn-danger" disabled={actionLoading !== null}>
                <Square size={16} /> Stop
              </button>
            </>
          )}
          {status?.status === 'paused' && (
            <>
              <button onClick={handleResume} className="btn btn-primary" disabled={actionLoading !== null}>
                <PlayCircle size={16} /> Resume
              </button>
              <button onClick={handleStop} className="btn btn-danger" disabled={actionLoading !== null}>
                <Square size={16} /> Stop
              </button>
            </>
          )}
          <button onClick={loadData} className="btn btn-secondary">
            <RefreshCw size={16} /> Refresh
          </button>
        </div>
      </div>

      {/* Start form modal */}
      {showStartForm && (
        <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Start Pipeline</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>States (optional)</label>
              <select
                multiple
                value={selectedStates}
                onChange={(e) => setSelectedStates(Array.from(e.target.selectedOptions, o => o.value))}
                style={{ width: '100%', minHeight: '100px', padding: '0.5rem' }}
              >
                {states.map(s => (
                  <option key={s.code} value={s.code}>{s.name} ({s.code})</option>
                ))}
              </select>
            </div>
            <div>
              <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Only Stage</label>
              <select
                value={onlyStage}
                onChange={(e) => setOnlyStage(e.target.value)}
                style={{ width: '100%', padding: '0.5rem' }}
              >
                <option value="">All stages</option>
                <option value="download">Download</option>
                <option value="transcribe">Transcribe</option>
                <option value="analyze">Analyze</option>
                <option value="extract">Extract</option>
              </select>
              <div style={{ marginTop: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Max Cost ($)</label>
                <input
                  type="number"
                  value={maxCost}
                  onChange={(e) => setMaxCost(e.target.value)}
                  placeholder="No limit"
                  style={{ width: '100%', padding: '0.5rem' }}
                />
              </div>
              <div style={{ marginTop: '1rem' }}>
                <label style={{ display: 'block', marginBottom: '0.5rem', fontWeight: 500 }}>Max Hearings</label>
                <input
                  type="number"
                  value={maxHearings}
                  onChange={(e) => setMaxHearings(e.target.value)}
                  placeholder="No limit"
                  style={{ width: '100%', padding: '0.5rem' }}
                />
              </div>
            </div>
          </div>
          <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', justifyContent: 'flex-end' }}>
            <button onClick={() => setShowStartForm(false)} className="btn btn-secondary">Cancel</button>
            <button onClick={handleStart} className="btn btn-primary" disabled={actionLoading === 'start'}>
              {actionLoading === 'start' ? <><Loader2 size={16} className="animate-spin" /> Starting...</> : <><Play size={16} /> Start</>}
            </button>
          </div>
        </div>
      )}

      {/* Stats row */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-value">{status?.processed_today || 0}</div>
          <div className="stat-label">Processed Today</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">${(status?.cost_today || 0).toFixed(2)}</div>
          <div className="stat-label">Cost Today</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: (status?.errors_today || 0) > 0 ? '#dc2626' : 'inherit' }}>
            {status?.errors_today || 0}
          </div>
          <div className="stat-label">Errors Today</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{status?.hearings_processed || 0}</div>
          <div className="stat-label">Total Processed</div>
        </div>
      </div>

      {/* Stage progress */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1.5rem' }}>
        <h3 style={{ marginBottom: '1rem' }}>Pipeline Stages</h3>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', overflowX: 'auto' }}>
          {STAGES.map((stage, idx) => {
            const count = status?.stage_counts?.[stage] || 0;
            const isActive = status?.current_stage === stage || (stage === 'discovered' && status?.status === 'idle');
            return (
              <div key={stage} style={{ display: 'flex', alignItems: 'center' }}>
                <div
                  style={{
                    padding: '0.75rem 1rem',
                    borderRadius: '0.5rem',
                    background: isActive ? 'var(--primary)' : 'var(--gray-100)',
                    color: isActive ? 'white' : 'var(--gray-700)',
                    textAlign: 'center',
                    minWidth: '100px',
                  }}
                >
                  <div style={{ fontWeight: 600, fontSize: '1.25rem' }}>{count}</div>
                  <div style={{ fontSize: '0.875rem' }}>{STAGE_LABELS[stage]}</div>
                </div>
                {idx < STAGES.length - 1 && (
                  <ChevronRight size={20} style={{ color: 'var(--gray-400)', margin: '0 0.25rem' }} />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Two column layout for activity and errors */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
        {/* Recent Activity */}
        <div className="card" style={{ padding: '1.5rem' }}>
          <h3 style={{ marginBottom: '1rem' }}>Recent Activity</h3>
          {activity.length === 0 ? (
            <p style={{ color: 'var(--gray-500)', textAlign: 'center', padding: '2rem' }}>
              No recent activity
            </p>
          ) : (
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {activity.slice(0, 20).map((item) => (
                <div
                  key={item.id}
                  style={{
                    padding: '0.75rem',
                    borderBottom: '1px solid var(--gray-200)',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}
                >
                  <div>
                    <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>
                      {item.hearing_title.slice(0, 50)}
                      {item.hearing_title.length > 50 && '...'}
                    </div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                      {item.state_code} | {item.stage} | {item.completed_at && new Date(item.completed_at).toLocaleTimeString()}
                    </div>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {item.cost_usd !== null && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        ${item.cost_usd.toFixed(3)}
                      </span>
                    )}
                    <span className={`badge ${getStatusBadge(item.status)}`}>
                      {item.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Errors */}
        <div className="card" style={{ padding: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3>Errors ({errors.length})</h3>
            {errors.length > 0 && (
              <button
                onClick={handleRetryAll}
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                disabled={actionLoading === 'retry-all'}
              >
                <RotateCcw size={14} /> Retry All
              </button>
            )}
          </div>
          {errors.length === 0 ? (
            <div style={{ color: 'var(--gray-500)', textAlign: 'center', padding: '2rem' }}>
              <CheckCircle2 size={32} style={{ color: 'var(--success)', marginBottom: '0.5rem' }} />
              <p>No errors</p>
            </div>
          ) : (
            <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
              {errors.map((item) => (
                <div
                  key={item.hearing_id}
                  style={{
                    padding: '0.75rem',
                    borderBottom: '1px solid var(--gray-200)',
                    background: 'var(--danger-bg)',
                    borderRadius: '0.25rem',
                    marginBottom: '0.5rem',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 500, fontSize: '0.875rem' }}>
                        {item.hearing_title.slice(0, 50)}
                        {item.hearing_title.length > 50 && '...'}
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {item.state_code} | Stage: {item.last_stage || 'N/A'} | Retries: {item.retry_count}
                      </div>
                      {item.error_message && (
                        <div style={{ fontSize: '0.75rem', color: '#dc2626', marginTop: '0.25rem' }}>
                          {item.error_message.slice(0, 100)}
                          {item.error_message.length > 100 && '...'}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '0.25rem' }}>
                      <button
                        onClick={() => handleRetry(item.hearing_id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        disabled={actionLoading === `retry-${item.hearing_id}`}
                        title="Retry"
                      >
                        <RotateCcw size={14} />
                      </button>
                      <button
                        onClick={() => handleSkip(item.hearing_id)}
                        className="btn btn-secondary"
                        style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                        disabled={actionLoading === `skip-${item.hearing_id}`}
                        title="Skip"
                      >
                        <SkipForward size={14} />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </PageLayout>
  );
}
