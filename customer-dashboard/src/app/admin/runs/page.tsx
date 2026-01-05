'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, History, RefreshCw } from 'lucide-react';
import { PageLayout } from '../components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface PipelineRun {
  id: number;
  started_at: string;
  completed_at: string | null;
  status: string;
  sources_checked: number;
  new_hearings: number;
  hearings_processed: number;
  errors: number;
  total_cost_usd: number;
}

export default function PipelineRunsPage() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadRuns() {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/admin/runs?limit=50`);
      if (!res.ok) throw new Error('Failed to fetch runs');
      const data = await res.json();
      setRuns(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadRuns();
  }, []);

  const getStatusBadge = (status: string) => {
    const classes: Record<string, string> = {
      complete: 'badge-success',
      running: 'badge-info',
      error: 'badge-danger',
    };
    return classes[status] || 'badge-warning';
  };

  if (loading) {
    return (
      <PageLayout activeTab="runs">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="runs">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div><strong>Error:</strong> {error}</div>
        </div>
      </PageLayout>
    );
  }

  const totalCost = runs.reduce((sum, r) => sum + r.total_cost_usd, 0);
  const totalHearings = runs.reduce((sum, r) => sum + r.hearings_processed, 0);

  return (
    <PageLayout activeTab="runs">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Pipeline Runs</h2>
          <p style={{ color: 'var(--gray-500)' }}>{runs.length} runs, ${totalCost.toFixed(2)} total cost</p>
        </div>
        <button onClick={loadRuns} className="btn btn-secondary">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {/* Summary stats */}
      <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
        <div className="stat-card">
          <div className="stat-value">{runs.length}</div>
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
      </div>

      {runs.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <History size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem' }}>No pipeline runs yet</h3>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Run #</th>
                <th>Started</th>
                <th>Status</th>
                <th>Sources</th>
                <th>New</th>
                <th>Processed</th>
                <th>Errors</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>{new Date(r.started_at).toLocaleString()}</td>
                  <td><span className={`badge ${getStatusBadge(r.status)}`}>{r.status}</span></td>
                  <td>{r.sources_checked}</td>
                  <td>{r.new_hearings}</td>
                  <td>{r.hearings_processed}</td>
                  <td style={{ color: r.errors > 0 ? '#dc2626' : 'inherit' }}>{r.errors}</td>
                  <td>${r.total_cost_usd.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}
