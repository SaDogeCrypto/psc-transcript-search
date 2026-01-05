'use client';

import { useState, useEffect } from 'react';
import { X } from 'lucide-react';
import { getStates, createSource, State, SourceCreateData } from '@/lib/api';

const SOURCE_TYPES = [
  { value: 'youtube_channel', label: 'YouTube Channel' },
  { value: 'admin_monitor', label: 'Admin Monitor (State Website)' },
  { value: 'rss_feed', label: 'RSS Feed' },
  { value: 'granicus', label: 'Granicus' },
  { value: 'other', label: 'Other' },
];

interface AddSourceModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function AddSourceModal({ isOpen, onClose, onSuccess }: AddSourceModalProps) {
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [formData, setFormData] = useState<SourceCreateData>({
    state_id: 0,
    name: '',
    source_type: 'youtube_channel',
    url: '',
    check_frequency_hours: 24,
    enabled: true,
  });

  useEffect(() => {
    if (isOpen) {
      loadStates();
    }
  }, [isOpen]);

  async function loadStates() {
    try {
      const data = await getStates();
      setStates(data);
      if (data.length > 0 && formData.state_id === 0) {
        setFormData(prev => ({ ...prev, state_id: data[0].id }));
      }
    } catch (err) {
      console.error('Failed to load states:', err);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!formData.name.trim()) {
      setError('Name is required');
      return;
    }
    if (!formData.url.trim()) {
      setError('URL is required');
      return;
    }
    if (!formData.state_id) {
      setError('Please select a state');
      return;
    }

    setLoading(true);
    try {
      await createSource(formData);
      onSuccess();
      onClose();
      // Reset form
      setFormData({
        state_id: states[0]?.id || 0,
        name: '',
        source_type: 'youtube_channel',
        url: '',
        check_frequency_hours: 24,
        enabled: true,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create source');
    } finally {
      setLoading(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add New Source</h3>
          <button onClick={onClose} className="modal-close">
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="modal-body">
            {error && (
              <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
                {error}
              </div>
            )}

            <div className="form-group">
              <label htmlFor="state">State</label>
              <select
                id="state"
                value={formData.state_id}
                onChange={e => setFormData(prev => ({ ...prev, state_id: parseInt(e.target.value) }))}
                className="form-input"
              >
                {states.map(state => (
                  <option key={state.id} value={state.id}>
                    {state.name} ({state.code})
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="name">Source Name</label>
              <input
                type="text"
                id="name"
                value={formData.name}
                onChange={e => setFormData(prev => ({ ...prev, name: e.target.value }))}
                className="form-input"
                placeholder="e.g., California PUC YouTube Channel"
              />
            </div>

            <div className="form-group">
              <label htmlFor="source_type">Source Type</label>
              <select
                id="source_type"
                value={formData.source_type}
                onChange={e => setFormData(prev => ({ ...prev, source_type: e.target.value }))}
                className="form-input"
              >
                {SOURCE_TYPES.map(type => (
                  <option key={type.value} value={type.value}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label htmlFor="url">URL</label>
              <input
                type="url"
                id="url"
                value={formData.url}
                onChange={e => setFormData(prev => ({ ...prev, url: e.target.value }))}
                className="form-input"
                placeholder="https://www.youtube.com/@channel"
              />
            </div>

            <div className="form-group">
              <label htmlFor="frequency">Check Frequency (hours)</label>
              <select
                id="frequency"
                value={formData.check_frequency_hours}
                onChange={e => setFormData(prev => ({ ...prev, check_frequency_hours: parseInt(e.target.value) }))}
                className="form-input"
              >
                <option value={6}>Every 6 hours</option>
                <option value={12}>Every 12 hours</option>
                <option value={24}>Every 24 hours</option>
                <option value={48}>Every 48 hours</option>
                <option value={168}>Weekly</option>
              </select>
            </div>

            <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <input
                type="checkbox"
                id="enabled"
                checked={formData.enabled}
                onChange={e => setFormData(prev => ({ ...prev, enabled: e.target.checked }))}
                style={{ width: 'auto' }}
              />
              <label htmlFor="enabled" style={{ marginBottom: 0 }}>Enable immediately</label>
            </div>
          </div>

          <div className="modal-footer">
            <button type="button" onClick={onClose} className="btn btn-secondary">
              Cancel
            </button>
            <button type="submit" disabled={loading} className="btn btn-primary">
              {loading ? 'Creating...' : 'Add Source'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
