'use client';

import { useEffect, useState } from 'react';
import {
  AlertCircle,
  Calendar,
  Clock,
  ExternalLink,
  FileAudio,
  Play,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getHearings, runPipelineSingle, type Hearing, type PaginatedResponse } from '@/lib/api';

function HearingCard({
  hearing,
  onProcess,
}: {
  hearing: Hearing;
  onProcess: (id: string, stage: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [processing, setProcessing] = useState(false);

  const getStatusBadge = () => {
    switch (hearing.transcript_status) {
      case 'analyzed':
        return 'badge-success';
      case 'failed':
        return 'badge-danger';
      case 'transcribed':
      case 'transcribing':
        return 'badge-info';
      default:
        return 'badge-gray';
    }
  };

  const handleProcess = async (stage: string) => {
    setProcessing(true);
    try {
      await onProcess(hearing.id, stage);
    } finally {
      setProcessing(false);
    }
  };

  const canTranscribe = ['pending', 'discovered'].includes(hearing.transcript_status || '') && hearing.video_url;
  const canAnalyze = hearing.transcript_status === 'transcribed';

  return (
    <div className="card" style={{ cursor: 'pointer' }} onClick={() => setExpanded(!expanded)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            <h4 style={{ fontWeight: 600, fontSize: '0.95rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {hearing.title || 'Untitled Hearing'}
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
          <span className={`badge ${getStatusBadge()}`}>{hearing.transcript_status || 'pending'}</span>
        </div>
      </div>

      {expanded && (
        <div style={{ marginTop: '1rem', paddingTop: '1rem', borderTop: '1px solid var(--gray-200)' }} onClick={(e) => e.stopPropagation()}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
            {hearing.docket_number && (
              <div>
                <div style={{ color: 'var(--gray-500)' }}>Docket</div>
                <div style={{ fontWeight: 500 }}>{hearing.docket_number}</div>
              </div>
            )}
            {hearing.hearing_type && (
              <div>
                <div style={{ color: 'var(--gray-500)' }}>Type</div>
                <div style={{ fontWeight: 500 }}>{hearing.hearing_type}</div>
              </div>
            )}
            {hearing.sector && (
              <div>
                <div style={{ color: 'var(--gray-500)' }}>Sector</div>
                <div style={{ fontWeight: 500 }}>{hearing.sector}</div>
              </div>
            )}
            {hearing.video_url && (
              <div>
                <div style={{ color: 'var(--gray-500)' }}>Video</div>
                <a href={hearing.video_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--primary)', textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                  View <ExternalLink size={12} />
                </a>
              </div>
            )}
          </div>

          {hearing.one_sentence_summary && (
            <div style={{ marginBottom: '1rem', padding: '0.75rem', background: 'var(--gray-50)', borderRadius: 'var(--radius)' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '0.25rem' }}>Summary</div>
              <p style={{ fontSize: '0.85rem', color: 'var(--gray-700)' }}>{hearing.one_sentence_summary}</p>
            </div>
          )}

          <div style={{ display: 'flex', gap: '0.5rem' }}>
            {canTranscribe && (
              <button
                onClick={() => handleProcess('transcribe')}
                disabled={processing}
                className="btn btn-primary"
                style={{ fontSize: '0.8rem' }}
              >
                {processing ? <RefreshCw size={14} className="animate-spin" /> : <Play size={14} />}
                Transcribe
              </button>
            )}
            {canAnalyze && (
              <button
                onClick={() => handleProcess('analyze')}
                disabled={processing}
                className="btn btn-secondary"
                style={{ fontSize: '0.8rem' }}
              >
                {processing ? <RefreshCw size={14} className="animate-spin" /> : <Sparkles size={14} />}
                Analyze
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
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  useEffect(() => {
    loadHearings();
  }, [filter, page]);

  async function loadHearings() {
    try {
      setLoading(true);
      const params: { status?: string; limit: number; offset: number } = {
        limit: pageSize,
        offset: page * pageSize,
      };
      if (filter !== 'all') {
        params.status = filter;
      }
      const data = await getHearings(params);
      setHearings(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hearings');
    } finally {
      setLoading(false);
    }
  }

  async function handleProcess(hearingId: string, stage: string) {
    try {
      await runPipelineSingle(hearingId, stage);
      await loadHearings();
    } catch (err) {
      console.error('Failed to process hearing:', err);
    }
  }

  const filteredHearings = hearings.filter((h) =>
    (h.title || '').toLowerCase().includes(searchQuery.toLowerCase()) ||
    (h.docket_number || '').toLowerCase().includes(searchQuery.toLowerCase())
  );

  const totalPages = Math.ceil(total / pageSize);

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
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>Hearings</h2>
          <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>Manage hearing processing ({total} total)</p>
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
        {['all', 'pending', 'transcribed', 'analyzed', 'failed'].map((status) => (
          <button
            key={status}
            onClick={() => { setFilter(status); setPage(0); }}
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
              textTransform: 'capitalize',
            }}
          >
            {status}
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
        <>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {filteredHearings.map((hearing) => (
              <HearingCard
                key={hearing.id}
                hearing={hearing}
                onProcess={handleProcess}
              />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '1rem', marginTop: '1.5rem' }}>
              <button
                onClick={() => setPage(Math.max(0, page - 1))}
                disabled={page === 0}
                className="btn btn-secondary"
                style={{ fontSize: '0.85rem' }}
              >
                Previous
              </button>
              <span style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
                Page {page + 1} of {totalPages}
              </span>
              <button
                onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
                disabled={page >= totalPages - 1}
                className="btn btn-secondary"
                style={{ fontSize: '0.85rem' }}
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </PageLayout>
  );
}
