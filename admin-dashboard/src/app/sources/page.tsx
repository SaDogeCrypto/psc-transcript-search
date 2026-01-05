'use client';

import { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  Clock,
  ExternalLink,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Radio,
  Trash2,
  X,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getSources, toggleSource, triggerSourceCheck, deleteSource, Source } from '@/lib/api';
import { AddSourceModal } from '@/components/AddSourceModal';
import ScraperPanel from '@/components/ScraperPanel';

function SourceCard({
  source,
  onToggle,
  onCheck,
  onDelete,
}: {
  source: Source;
  onToggle: (id: number) => void;
  onCheck: (id: number) => void;
  onDelete: (id: number, name: string) => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleToggle = async () => {
    setLoading(true);
    await onToggle(source.id);
    setLoading(false);
  };

  const handleCheck = async () => {
    setLoading(true);
    await onCheck(source.id);
    setLoading(false);
  };

  const getStatusBadge = () => {
    switch (source.status) {
      case 'healthy':
        return 'badge-success';
      case 'error':
        return 'badge-danger';
      case 'checking':
        return 'badge-info';
      default:
        return 'badge-warning';
    }
  };

  return (
    <div className={`card clickable-card ${!source.enabled ? 'opacity-60' : ''}`} style={{ opacity: source.enabled ? 1 : 0.6 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            background: source.enabled ? '#dbeafe' : 'var(--gray-200)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Radio size={20} color={source.enabled ? '#2563eb' : '#9ca3af'} />
          </div>
          <div>
            <h4 style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{source.name}</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              {source.state_name} ({source.state_code})
            </p>
          </div>
        </div>
        <span className={`badge ${getStatusBadge()}`}>
          {source.status}
        </span>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem', fontSize: '0.85rem' }}>
        <div>
          <div style={{ color: 'var(--gray-500)' }}>Type</div>
          <div style={{ fontWeight: 500, textTransform: 'capitalize' }}>{source.source_type.replace('_', ' ')}</div>
        </div>
        <div>
          <div style={{ color: 'var(--gray-500)' }}>Check Frequency</div>
          <div style={{ fontWeight: 500 }}>Every {source.check_frequency_hours}h</div>
        </div>
        <div>
          <div style={{ color: 'var(--gray-500)' }}>Last Checked</div>
          <div style={{ fontWeight: 500 }}>{source.last_checked_at ? new Date(source.last_checked_at).toLocaleString() : 'Never'}</div>
        </div>
        <div>
          <div style={{ color: 'var(--gray-500)' }}>Last Hearing</div>
          <div style={{ fontWeight: 500 }}>{source.last_hearing_at ? new Date(source.last_hearing_at).toLocaleDateString() : 'None'}</div>
        </div>
      </div>

      {source.error_message && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={16} />
          <span style={{ fontSize: '0.85rem' }}>{source.error_message}</span>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--gray-200)', paddingTop: '1rem' }}>
        <a
          href={source.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem', color: 'var(--primary)', fontSize: '0.85rem', textDecoration: 'none' }}
        >
          <ExternalLink size={14} />
          View Source
        </a>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button
            onClick={() => onDelete(source.id, source.name)}
            disabled={loading}
            className="btn btn-secondary"
            style={{ fontSize: '0.8rem', padding: '0.4rem 0.75rem', color: 'var(--danger)' }}
            title="Delete source"
          >
            <Trash2 size={14} />
          </button>
          <button
            onClick={handleCheck}
            disabled={loading || !source.enabled}
            className="btn btn-secondary"
            style={{ fontSize: '0.8rem', padding: '0.4rem 0.75rem' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Check
          </button>
          <button
            onClick={handleToggle}
            disabled={loading}
            className={source.enabled ? 'btn btn-danger' : 'btn btn-success'}
            style={{ fontSize: '0.8rem', padding: '0.4rem 0.75rem' }}
          >
            {source.enabled ? <><Pause size={14} /> Disable</> : <><Play size={14} /> Enable</>}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function SourcesPage() {
  const [sources, setSources] = useState<Source[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'healthy' | 'error'>('all');
  const [showAddModal, setShowAddModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState<{ id: number; name: string } | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    loadSources();
  }, []);

  async function loadSources() {
    try {
      setLoading(true);
      const data = await getSources();
      setSources(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load sources');
    } finally {
      setLoading(false);
    }
  }

  async function handleToggle(sourceId: number) {
    try {
      await toggleSource(sourceId);
      await loadSources();
    } catch (err) {
      console.error('Failed to toggle source:', err);
    }
  }

  async function handleCheck(sourceId: number) {
    try {
      await triggerSourceCheck(sourceId);
      await loadSources();
    } catch (err) {
      console.error('Failed to trigger check:', err);
    }
  }

  async function handleDelete() {
    if (!deleteConfirm) return;
    setDeleting(true);
    try {
      await deleteSource(deleteConfirm.id);
      await loadSources();
      setDeleteConfirm(null);
    } catch (err) {
      console.error('Failed to delete source:', err);
    } finally {
      setDeleting(false);
    }
  }

  const filteredSources = sources.filter((s) => {
    if (filter === 'all') return true;
    return s.status === filter;
  });

  const healthyCount = sources.filter((s) => s.status === 'healthy').length;
  const errorCount = sources.filter((s) => s.status === 'error').length;

  if (loading) {
    return (
      <PageLayout activeTab="sources">
        <div className="loading">
          <div className="spinner" />
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="sources">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div>
            <strong>Error loading sources</strong>
            <p style={{ marginTop: '0.25rem' }}>{error}</p>
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="sources">
      {/* Scraper Control Panel */}
      <div style={{ marginBottom: '2rem' }}>
        <ScraperPanel />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>Sources</h2>
          <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>Manage hearing sources across all states</p>
        </div>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <button onClick={loadSources} className="btn btn-secondary">
            <RefreshCw size={16} />
            Refresh
          </button>
          <button onClick={() => setShowAddModal(true)} className="btn btn-primary">
            <Plus size={16} />
            Add Source
          </button>
        </div>
      </div>

      {/* Filter tabs */}
      <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem', borderBottom: '1px solid var(--gray-200)', paddingBottom: '0.5rem' }}>
        {[
          { id: 'all', label: `All (${sources.length})` },
          { id: 'healthy', label: `Healthy (${healthyCount})` },
          { id: 'error', label: `Errors (${errorCount})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setFilter(tab.id as any)}
            style={{
              background: 'none',
              border: 'none',
              padding: '0.5rem 0',
              cursor: 'pointer',
              fontWeight: 500,
              fontSize: '0.9rem',
              color: filter === tab.id ? 'var(--primary)' : 'var(--gray-500)',
              borderBottom: filter === tab.id ? '2px solid var(--primary)' : '2px solid transparent',
              marginBottom: '-0.55rem',
            }}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {filteredSources.length === 0 ? (
        <div className="empty-state">
          <Radio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--gray-700)' }}>No sources found</h3>
          <p className="hint">
            {filter === 'all' ? 'Add sources to start monitoring hearings.' : `No sources with status "${filter}".`}
          </p>
        </div>
      ) : (
        <div className="grid-2">
          {filteredSources.map((source) => (
            <SourceCard
              key={source.id}
              source={source}
              onToggle={handleToggle}
              onCheck={handleCheck}
              onDelete={(id, name) => setDeleteConfirm({ id, name })}
            />
          ))}
        </div>
      )}

      {/* Add Source Modal */}
      <AddSourceModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSuccess={loadSources}
      />

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="modal-overlay" onClick={() => setDeleteConfirm(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px' }}>
            <div className="modal-header">
              <h3>Delete Source</h3>
              <button onClick={() => setDeleteConfirm(null)} className="modal-close">
                <X size={20} />
              </button>
            </div>
            <div className="modal-body">
              <div className="confirm-dialog">
                <AlertCircle size={48} color="var(--danger)" style={{ marginBottom: '1rem' }} />
                <p>Are you sure you want to delete this source?</p>
                <p className="source-name">{deleteConfirm.name}</p>
                <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)', marginTop: '0.75rem' }}>
                  This will not delete any hearings that were discovered from this source.
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={() => setDeleteConfirm(null)} className="btn btn-secondary">
                Cancel
              </button>
              <button onClick={handleDelete} disabled={deleting} className="btn btn-danger">
                {deleting ? 'Deleting...' : 'Delete Source'}
              </button>
            </div>
          </div>
        </div>
      )}
    </PageLayout>
  );
}
