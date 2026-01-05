'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, FileAudio, RefreshCw } from 'lucide-react';
import { PageLayout } from '../components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface Hearing {
  id: number;
  state_code: string;
  title: string;
  hearing_date: string | null;
  pipeline_status: string;
  created_at: string;
}

export default function HearingsPage() {
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function loadHearings() {
    try {
      setLoading(true);
      const res = await fetch(`${API_URL}/admin/hearings?page_size=50`);
      if (!res.ok) throw new Error('Failed to fetch hearings');
      const data = await res.json();
      setHearings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hearings');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadHearings();
  }, []);

  const getStatusBadge = (status: string) => {
    const classes: Record<string, string> = {
      complete: 'badge-success',
      error: 'badge-danger',
      downloading: 'badge-info',
      transcribing: 'badge-info',
      analyzing: 'badge-info',
      discovered: 'badge-gray',
    };
    return classes[status] || 'badge-gray';
  };

  if (loading) {
    return (
      <PageLayout activeTab="hearings">
        <div className="loading"><div className="spinner" /></div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="hearings">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div><strong>Error:</strong> {error}</div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="hearings">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Hearings Pipeline</h2>
          <p style={{ color: 'var(--gray-500)' }}>Monitor hearing processing</p>
        </div>
        <button onClick={loadHearings} className="btn btn-secondary">
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {hearings.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <FileAudio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem' }}>No hearings found</h3>
        </div>
      ) : (
        <div className="table-container">
          <table>
            <thead>
              <tr>
                <th>Title</th>
                <th>State</th>
                <th>Date</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {hearings.map((h) => (
                <tr key={h.id}>
                  <td style={{ maxWidth: '300px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.title}</td>
                  <td><span className="badge badge-primary">{h.state_code}</span></td>
                  <td>{h.hearing_date || '-'}</td>
                  <td><span className={`badge ${getStatusBadge(h.pipeline_status)}`}>{h.pipeline_status}</span></td>
                  <td>{new Date(h.created_at).toLocaleDateString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
}
