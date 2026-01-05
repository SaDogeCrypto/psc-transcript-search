'use client';

import { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  Download,
  ExternalLink,
  FileAudio,
  Mic,
  RefreshCw,
  RotateCcw,
  Search,
  Sparkles,
  XCircle,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getHearings, retryHearing, cancelHearing, Hearing, PipelineJob } from '@/lib/api';

const PIPELINE_STAGES = ['download', 'transcribe', 'analyze'];

function PipelineStage({ stage, job }: { stage: string; job?: PipelineJob }) {
  const stageIcons: Record<string, React.ComponentType<{ size?: number; color?: string }>> = {
    download: Download,
    transcribe: Mic,
    analyze: Sparkles,
  };

  const Icon = stageIcons[stage] || Clock;

  const getStatusClass = () => {
    if (!job) return 'pending';
    return job.status;
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
      <div className={`stage-icon ${getStatusClass()}`}>
        {job?.status === 'running' ? (
          <RefreshCw size={14} className="animate-spin" />
        ) : (
          <Icon size={14} />
        )}
      </div>
      <span style={{ marginTop: '0.25rem', fontSize: '0.7rem', color: 'var(--gray-500)', textTransform: 'capitalize' }}>{stage}</span>
    </div>
  );
}

function HearingCard({
  hearing,
  onRetry,
  onCancel,
}: {
  hearing: Hearing;
  onRetry: (id: number) => void;
  onCancel: (id: number) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  const jobsByStage = hearing.pipeline_jobs.reduce((acc, job) => {
    acc[job.stage] = job;
    return acc;
  }, {} as Record<string, PipelineJob>);

  const hasError = hearing.pipeline_jobs.some((j) => j.status === 'error');
  const isRunning = hearing.pipeline_jobs.some((j) => j.status === 'running');

  const getStatusBadge = () => {
    switch (hearing.pipeline_status) {
      case 'complete':
        return 'badge-success';
      case 'error':
        return 'badge-danger';
      case 'downloading':
      case 'transcribing':
      case 'analyzing':
        return 'badge-info';
      default:
        return 'badge-gray';
    }
  };

  return (
    <div className="card" style={{ cursor: 'pointer' }} onClick={() => setExpanded(!expanded)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <h4 style={{ fontWeight: 600, fontSize: '0.95rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {hearing.title}
            </h4>
            <span className="badge badge-primary" style={{ fontSize: '0.7rem' }}>{hearing.state_code}</span>
          </div>
          <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
            {hearing.hearing_date || 'No date'}
            {hearing.utility_name && ` · ${hearing.utility_name}`}
            {hearing.duration_seconds && ` · ${Math.round(hearing.duration_seconds / 60)} min`}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {/* Pipeline stages */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            {PIPELINE_STAGES.map((stage, idx) => (
              <div key={stage} style={{ display: 'flex', alignItems: 'center' }}>
                <PipelineStage stage={stage} job={jobsByStage[stage]} />
                {idx < PIPELINE_STAGES.length - 1 && (
                  <div style={{ width: '16px', height: '2px', background: 'var(--gray-200)', margin: '0 0.25rem' }} />
                )}
              </div>
            ))}
          </div>
          <span className={`badge ${getStatusBadge()}`}>{hearing.pipeline_status}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gray-200)' }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
            <div>
              <div style={{ color: 'var(--gray-500)' }}>Created</div>
              <div style={{ fontWeight: 500 }}>{new Date(hearing.created_at).toLocaleString()}</div>
            </div>
            {hearing.source_url && (
              <div>
                <div style={{ color: 'var(--gray-500)' }}>Source</div>
                <a href={hearing.source_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                  View <ExternalLink size={12} />
                </a>
              </div>
            )}
          </div>

          {hearing.pipeline_jobs.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.5rem' }}>Pipeline Jobs</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {hearing.pipeline_jobs.map((job) => (
                  <div
                    key={job.id}
                    style={{
                      padding: '0.75rem',
                      background: job.status === 'error' ? '#fee2e2' : 'var(--gray-50)',
                      borderRadius: 'var(--radius)',
                      fontSize: '0.85rem',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <span style={{ fontWeight: 500, textTransform: 'capitalize' }}>{job.stage}</span>
                        <span className={`badge ${job.status === 'complete' ? 'badge-success' : job.status === 'error' ? 'badge-danger' : job.status === 'running' ? 'badge-info' : 'badge-gray'}`} style={{ fontSize: '0.7rem' }}>
                          {job.status}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {job.retry_count > 0 && <span style={{ marginRight: '0.5rem' }}>Retries: {job.retry_count}</span>}
                        {job.cost_usd && <span>${job.cost_usd.toFixed(4)}</span>}
                      </div>
                    </div>
                    {job.error_message && (
                      <div style={{ marginTop: '0.5rem', color: '#991b1b', fontSize: '0.8rem' }}>{job.error_message}</div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {hasError && (
              <button onClick={() => onRetry(hearing.id)} className="btn btn-primary" style={{ fontSize: '0.8rem' }}>
                <RotateCcw size={14} /> Retry Failed
              </button>
            )}
            {isRunning && (
              <button onClick={() => onCancel(hearing.id)} className="btn btn-danger" style={{ fontSize: '0.8rem' }}>
                <XCircle size={14} /> Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default function HearingsPage() {
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');

  useEffect(() => {
    loadHearings();
  }, [filter]);

  async function loadHearings() {
    try {
      setLoading(true);
      const params: { pipeline_status?: string } = {};
      if (filter !== 'all') {
        params.pipeline_status = filter;
      }
      const data = await getHearings(params);
      setHearings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hearings');
    } finally {
      setLoading(false);
    }
  }

  async function handleRetry(hearingId: number) {
    try {
      await retryHearing(hearingId);
      await loadHearings();
    } catch (err) {
      console.error('Failed to retry hearing:', err);
    }
  }

  async function handleCancel(hearingId: number) {
    try {
      await cancelHearing(hearingId);
      await loadHearings();
    } catch (err) {
      console.error('Failed to cancel hearing:', err);
    }
  }

  const filteredHearings = hearings.filter((h) =>
    h.title.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const statusCounts = hearings.reduce((acc, h) => {
    acc[h.pipeline_status] = (acc[h.pipeline_status] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);

  if (loading && hearings.length === 0) {
    return (
      <PageLayout activeTab="hearings">
        <div className="loading">
          <div className="spinner" />
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="hearings">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div>
            <strong>Error loading hearings</strong>
            <p style={{ marginTop: '0.25rem' }}>{error}</p>
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="hearings">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>Hearings Pipeline</h2>
          <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>Monitor and manage hearing processing</p>
        </div>
        <button onClick={loadHearings} className="btn btn-secondary">
          <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      {/* Search */}
      <div style={{ marginBottom: '1rem', position: 'relative' }}>
        <Search size={18} style={{ position: 'absolute', left: '0.75rem', top: '50%', transform: 'translateY(-50%)', color: 'var(--gray-400)' }} />
        <input
          type="text"
          placeholder="Search hearings..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={{
            width: '100%',
            padding: '0.75rem 0.75rem 0.75rem 2.5rem',
            border: '1px solid var(--gray-300)',
            borderRadius: 'var(--radius)',
            fontSize: '0.9rem',
          }}
        />
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', overflowX: 'auto', borderBottom: '1px solid var(--gray-200)', paddingBottom: '0.5rem' }}>
        {['all', 'discovered', 'downloading', 'transcribing', 'analyzing', 'complete', 'error'].map((status) => (
          <button
            key={status}
            onClick={() => setFilter(status)}
            style={{
              background: 'none',
              border: 'none',
              padding: '0.5rem 0.75rem',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.85rem',
              color: filter === status ? 'var(--primary)' : 'var(--gray-500)',
              borderBottom: filter === status ? '2px solid var(--primary)' : '2px solid transparent',
              marginBottom: '-0.55rem',
              whiteSpace: 'nowrap',
            }}
          >
            {status.charAt(0).toUpperCase() + status.slice(1)}
            {status === 'all' ? ` (${hearings.length})` : ` (${statusCounts[status] || 0})`}
          </button>
        ))}
      </div>

      {filteredHearings.length === 0 ? (
        <div className="empty-state">
          <FileAudio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--gray-700)' }}>No hearings found</h3>
          <p className="hint">
            {searchQuery ? 'Try a different search term.' : filter === 'all' ? 'No hearings discovered yet.' : `No hearings with status "${filter}".`}
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {filteredHearings.map((hearing) => (
            <HearingCard
              key={hearing.id}
              hearing={hearing}
              onRetry={handleRetry}
              onCancel={handleCancel}
            />
          ))}
        </div>
      )}
    </PageLayout>
  );
}
