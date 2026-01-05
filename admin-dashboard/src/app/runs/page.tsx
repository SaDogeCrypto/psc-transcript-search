'use client';

import { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  DollarSign,
  FileAudio,
  History,
  Radio,
  RefreshCw,
  XCircle,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getPipelineRuns, PipelineRun } from '@/lib/api';

function formatDuration(startedAt: string, completedAt: string | null): string {
  if (!completedAt) return 'Running...';
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  const durationMs = end - start;

  if (durationMs < 60000) return `${Math.round(durationMs / 1000)}s`;
  if (durationMs < 3600000) return `${Math.round(durationMs / 60000)}m`;
  return `${(durationMs / 3600000).toFixed(1)}h`;
}

function RunCard({ run }: { run: PipelineRun }) {
  const [expanded, setExpanded] = useState(false);

  const getStatusBadge = () => {
    switch (run.status) {
      case 'complete':
        return 'badge-success';
      case 'running':
        return 'badge-info';
      case 'error':
        return 'badge-danger';
      default:
        return 'badge-warning';
    }
  };

  return (
    <div className="card clickable-card" onClick={() => setExpanded(!expanded)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div style={{
            width: '48px',
            height: '48px',
            borderRadius: '50%',
            background: run.status === 'complete' ? '#d1fae5' : run.status === 'running' ? '#dbeafe' : run.status === 'error' ? '#fee2e2' : 'var(--gray-200)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <History size={24} color={run.status === 'complete' ? '#065f46' : run.status === 'running' ? '#1e40af' : run.status === 'error' ? '#991b1b' : '#6b7280'} />
          </div>
          <div>
            <div style={{ fontWeight: 600, color: 'var(--gray-800)' }}>Pipeline Run #{run.id}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              {new Date(run.started_at).toLocaleString()}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span className={`badge ${getStatusBadge()}`}>{run.status}</span>
          <span style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
            {formatDuration(run.started_at, run.completed_at)}
          </span>
        </div>
      </div>

      {/* Quick stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem', marginTop: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Radio size={16} color="var(--gray-400)" />
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Sources</div>
            <div style={{ fontWeight: 600 }}>{run.sources_checked}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <FileAudio size={16} color="var(--gray-400)" />
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>New</div>
            <div style={{ fontWeight: 600 }}>{run.new_hearings}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <CheckCircle size={16} color="var(--gray-400)" />
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Processed</div>
            <div style={{ fontWeight: 600 }}>{run.hearings_processed}</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <DollarSign size={16} color="var(--gray-400)" />
          <div>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>Cost</div>
            <div style={{ fontWeight: 600 }}>${run.total_cost_usd.toFixed(2)}</div>
          </div>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gray-200)' }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.75rem' }}>Timing</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--gray-500)' }}>Started</span>
                  <span>{new Date(run.started_at).toLocaleString()}</span>
                </div>
                {run.completed_at && (
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span style={{ color: 'var(--gray-500)' }}>Completed</span>
                    <span>{new Date(run.completed_at).toLocaleString()}</span>
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--gray-500)' }}>Duration</span>
                  <span>{formatDuration(run.started_at, run.completed_at)}</span>
                </div>
              </div>
            </div>
            <div>
              <h4 style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.75rem' }}>Cost Breakdown</h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.85rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--gray-500)' }}>Transcription</span>
                  <span>${run.transcription_cost_usd.toFixed(4)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--gray-500)' }}>Analysis</span>
                  <span>${run.analysis_cost_usd.toFixed(4)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderTop: '1px solid var(--gray-200)', paddingTop: '0.5rem' }}>
                  <span style={{ fontWeight: 600 }}>Total</span>
                  <span style={{ fontWeight: 600 }}>${run.total_cost_usd.toFixed(4)}</span>
                </div>
              </div>
            </div>
          </div>

          {run.errors > 0 && (
            <div className="alert alert-danger" style={{ marginTop: '1rem' }}>
              <AlertCircle size={16} />
              <span>{run.errors} error(s) occurred during this run</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function PipelineRunsPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadRuns();
  }, []);

  async function loadRuns() {
    try {
      setLoading(true);
      const data = await getPipelineRuns(50);
      setRuns(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load pipeline runs');
    } finally {
      setLoading(false);
    }
  }

  const totalRuns = runs.length;
  const totalCost = runs.reduce((sum, r) => sum + r.total_cost_usd, 0);
  const totalHearings = runs.reduce((sum, r) => sum + r.hearings_processed, 0);
  const totalErrors = runs.reduce((sum, r) => sum + r.errors, 0);

  if (loading) {
    return (
      <PageLayout activeTab="runs">
        <div className="loading">
          <div className="spinner" />
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="runs">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div>
            <strong>Error loading pipeline runs</strong>
            <p style={{ marginTop: '0.25rem' }}>{error}</p>
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="runs">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>Pipeline Runs</h2>
          <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>History of daily pipeline executions</p>
        </div>
        <button onClick={loadRuns} className="btn btn-secondary">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {/* Summary stats */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-value">{totalRuns}</div>
          <div className="stat-label">Total Runs</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">{totalHearings}</div>
          <div className="stat-label">Hearings Processed</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">${totalCost.toFixed(2)}</div>
          <div className="stat-label">Total Cost</div>
        </div>
        <div className="stat-card">
          <div className="stat-value" style={{ color: totalErrors > 0 ? '#dc2626' : 'inherit' }}>{totalErrors}</div>
          <div className="stat-label">Total Errors</div>
        </div>
      </div>

      {runs.length === 0 ? (
        <div className="empty-state">
          <History size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--gray-700)' }}>No pipeline runs</h3>
          <p className="hint">Pipeline runs will appear here after the first execution.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {runs.map((run) => (
            <RunCard key={run.id} run={run} />
          ))}
        </div>
      )}
    </PageLayout>
  );
}
