'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, Radio, RefreshCw, ExternalLink } from 'lucide-react';
import { PageLayout } from '../components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Source {
  id: number;
  state_code: string;
  state_name: string;
  name: string;
  source_type: string;
  url: string;
  enabled: boolean;
  status: string;
  last_checked_at: string | null;
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadSources() {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/admin/sources`);
      if (!res.ok) throw new Error('Failed to fetch sources');
      const data = await res.json();
      setSources(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadSources();
  }, []);

  const getStatusBadge = (status: string) => {
    const classes: Record<string, string> = {
      healthy: 'badge-success',
      error: 'badge-danger',
      checking: 'badge-info',
      pending: 'badge-warning',
    };
    return classes[status] || 'badge-gray';
  };

  if (loading) {
    return (
      <PageLayout activeTab="sources">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="sources">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div><strong>Error:</strong> {error}</div>
        </div>
      </PageLayout>
    );
  }

  const healthyCount = sources.filter(s => s.status === 'healthy').length;
  const errorCount = sources.filter(s => s.status === 'error').length;

  return (
    <PageLayout activeTab="sources">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Sources</h2>
          <p style={{ color: 'var(--gray-500)' }}>{healthyCount} healthy, {errorCount} errors</p>
        </div>
        <button onClick={loadSources} className="btn btn-secondary">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {sources.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <Radio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem' }}>No sources configured</h3>
        </div>
      ) : (
        <div className="grid-2">
          {sources.map((s) => (
            <div key={s.id} className="card" style={{ opacity: s.enabled ? 1 : 0.6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                <div>
                  <h4 style={{ fontWeight: 600 }}>{s.name}</h4>
                  <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>{s.state_name} ({s.state_code})</p>
                </div>
                <span className={`badge ${getStatusBadge(s.status)}`}>{s.status}</span>
              </div>
              <div style={{ fontSize: '0.85rem', color: 'var(--gray-600)' }}>
                <p>Type: {s.source_type}</p>
                <p>Last checked: {s.last_checked_at ? new Date(s.last_checked_at).toLocaleString() : 'Never'}</p>
              </div>
              <a href={s.url} target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', color: 'var(--primary)', fontSize: '0.85rem', marginTop: '0.5rem', textDecoration: 'none' }}>
                <ExternalLink size={14} /> View Source
              </a>
            </div>
          ))}
        </div>
      )}
    </PageLayout>
  );
}
