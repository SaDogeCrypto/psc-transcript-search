'use client';

import { useEffect, useState } from 'react';
import { AlertCircle, FileAudio, RefreshCw, Filter, ChevronLeft, ChevronRight, ExternalLink } from 'lucide-react';
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

interface StateOption {
  code: string;
  name: string;
  hearing_count: number;
}

interface PaginatedResponse {
  items: Hearing[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

const STATUS_OPTIONS = [
  { value: '', label: 'All Statuses' },
  { value: 'discovered', label: 'Discovered' },
  { value: 'downloaded', label: 'Downloaded' },
  { value: 'transcribed', label: 'Transcribed' },
  { value: 'analyzed', label: 'Analyzed' },
  { value: 'complete', label: 'Complete' },
  { value: 'error', label: 'Error' },
  { value: 'failed', label: 'Failed' },
];

const PAGE_SIZE = 50;

export default function HearingsPage() {
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [states, setStates] = useState<StateOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedState, setSelectedState] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');

  // Pagination
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(0);

  async function loadStates() {
    try {
      const res = await fetch(`${API_URL}/admin/states`);
      if (res.ok) {
        const data = await res.json();
        setStates(data);
      }
    } catch (err) {
      console.error('Failed to load states:', err);
    }
  }

  async function loadHearings(pageNum: number = 1) {
    try {
      setLoading(true);
      const params = new URLSearchParams({
        page: pageNum.toString(),
        page_size: PAGE_SIZE.toString()
      });
      if (selectedState) params.set('states', selectedState);
      if (selectedStatus) params.set('status', selectedStatus);

      const res = await fetch(`${API_URL}/admin/hearings?${params}`);
      if (!res.ok) throw new Error('Failed to fetch hearings');
      const data: PaginatedResponse = await res.json();
      setHearings(data.items);
      setTotalCount(data.total);
      setTotalPages(data.total_pages);
      setPage(data.page);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hearings');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStates();
  }, []);

  useEffect(() => {
    setPage(1);
    loadHearings(1);
  }, [selectedState, selectedStatus]);

  const getStatusBadge = (status: string) => {
    const classes: Record<string, string> = {
      complete: 'badge-success',
      error: 'badge-danger',
      failed: 'badge-danger',
      downloading: 'badge-info',
      transcribing: 'badge-info',
      analyzing: 'badge-info',
      extracting: 'badge-info',
      downloaded: 'badge-warning',
      transcribed: 'badge-warning',
      analyzed: 'badge-warning',
      discovered: 'badge-gray',
    };
    return classes[status] || 'badge-gray';
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      loadHearings(newPage);
    }
  };

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
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Hearings</h2>
          <p style={{ color: 'var(--gray-500)' }}>
            {totalCount.toLocaleString()} total hearings
          </p>
        </div>
        <button onClick={() => loadHearings(page)} className="btn btn-secondary" disabled={loading}>
          <RefreshCw size={16} className={loading ? 'spin' : ''} /> Refresh
        </button>
      </div>

      {/* Filters */}
      <div className="card" style={{ marginBottom: '1.5rem', padding: '1rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <Filter size={18} color="var(--gray-500)" />

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>State:</label>
            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              style={{
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--gray-300)',
                minWidth: '180px'
              }}
            >
              <option value="">All States ({states.reduce((sum, s) => sum + s.hearing_count, 0)})</option>
              {states.filter(s => s.hearing_count > 0).map((s) => (
                <option key={s.code} value={s.code}>{s.code} - {s.name} ({s.hearing_count})</option>
              ))}
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <label style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>Status:</label>
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              style={{
                padding: '0.5rem',
                borderRadius: '6px',
                border: '1px solid var(--gray-300)',
                minWidth: '150px'
              }}
            >
              {STATUS_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>{opt.label}</option>
              ))}
            </select>
          </div>

          {(selectedState || selectedStatus) && (
            <button
              onClick={() => { setSelectedState(''); setSelectedStatus(''); }}
              className="btn btn-secondary"
              style={{ padding: '0.5rem 0.75rem', fontSize: '0.875rem' }}
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="loading"><div className="spinner" /></div>
      ) : hearings.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <FileAudio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem' }}>No hearings found</h3>
          <p style={{ color: 'var(--gray-500)' }}>Try adjusting your filters</p>
        </div>
      ) : (
        <>
          <div className="table-container">
            <table>
              <thead>
                <tr>
                  <th>Title</th>
                  <th>State</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Created</th>
                  <th style={{ width: '60px' }}></th>
                </tr>
              </thead>
              <tbody>
                {hearings.map((h) => (
                  <tr key={h.id}>
                    <td style={{ maxWidth: '400px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {h.title}
                    </td>
                    <td><span className="badge badge-primary">{h.state_code}</span></td>
                    <td>{h.hearing_date || '-'}</td>
                    <td><span className={`badge ${getStatusBadge(h.pipeline_status)}`}>{h.pipeline_status}</span></td>
                    <td>{new Date(h.created_at).toLocaleDateString()}</td>
                    <td>
                      {(h.pipeline_status === 'complete' || h.pipeline_status === 'transcribed' || h.pipeline_status === 'analyzed') && (
                        <a
                          href={`/dashboard/hearings/${h.id}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="btn btn-secondary"
                          style={{ padding: '0.25rem 0.5rem' }}
                          title="View hearing"
                        >
                          <ExternalLink size={14} />
                        </a>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginTop: '1rem',
              padding: '0.75rem',
              background: 'var(--gray-50)',
              borderRadius: '8px'
            }}>
              <span style={{ color: 'var(--gray-600)', fontSize: '0.875rem' }}>
                Showing {((page - 1) * PAGE_SIZE) + 1} - {Math.min(page * PAGE_SIZE, totalCount)} of {totalCount.toLocaleString()}
              </span>

              <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                <button
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page <= 1}
                  className="btn btn-secondary"
                  style={{ padding: '0.5rem' }}
                >
                  <ChevronLeft size={18} />
                </button>

                <span style={{ padding: '0 0.75rem', fontSize: '0.875rem' }}>
                  Page {page} of {totalPages}
                </span>

                <button
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= totalPages}
                  className="btn btn-secondary"
                  style={{ padding: '0.5rem' }}
                >
                  <ChevronRight size={18} />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}
