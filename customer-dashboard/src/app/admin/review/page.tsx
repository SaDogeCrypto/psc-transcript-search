'use client';

import { useEffect, useState } from 'react';
import {
  CheckCircle, XCircle, Link2, SkipForward,
  Search, RefreshCw, AlertCircle, Filter
} from 'lucide-react';
import { PageLayout } from '../components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface ReviewSuggestion {
  id: number;
  normalized_id?: string;
  name?: string;
  title?: string;
  utility_name?: string;
  score: number;
}

interface ReviewItem {
  id: number;
  entity_type: 'docket' | 'topic' | 'utility';
  hearing_id: number;
  hearing_title: string;
  hearing_date: string | null;
  original_text: string;
  current_entity_id: number | null;
  current_entity_name: string | null;
  confidence: string;
  confidence_score: number | null;
  match_type: string | null;
  review_reason: string | null;
  transcript_context: string | null;
  suggestions: ReviewSuggestion[];
}

interface ReviewStats {
  total: number;
  dockets: number;
  topics: number;
  utilities: number;
  hearings: number;
}

// Hearing-grouped review types
interface EntityReviewItem {
  id: number;
  entity_type: string;
  entity_id: number;
  name: string;
  role?: string;
  category?: string;
  context?: string;
  confidence: string;
  confidence_score?: number;
  match_type?: string;
  review_reason?: string;
  known_docket_id?: number;
  known_utility?: string;
  known_title?: string;
  utility_match?: boolean;
  suggestions: ReviewSuggestion[];
}

interface HearingReviewItem {
  hearing_id: number;
  hearing_title: string;
  hearing_date?: string;
  state_code?: string;
  topics: EntityReviewItem[];
  utilities: EntityReviewItem[];
  dockets: EntityReviewItem[];
  total_entities: number;
  needs_review_count: number;
  lowest_confidence?: number;
  utility_docket_matches: number;
}

// Extraction review types
interface ExtractionReviewItem {
  id: number;
  hearing_id: number;
  hearing_title: string | null;
  hearing_date: string | null;
  state_code: string | null;
  raw_text: string;
  normalized_id: string;
  context_before: string | null;
  context_after: string | null;
  trigger_phrase: string | null;
  format_valid: boolean;
  format_score: number;
  format_issues: string[] | null;
  match_type: string;
  matched_docket_id: number | null;
  matched_docket_number: string | null;
  matched_docket_title: string | null;
  fuzzy_score: number;
  context_score: number;
  confidence_score: number;
  status: string;
  review_reason: string | null;
  suggested_docket_id: number | null;
  suggested_correction: string | null;
  correction_confidence: number;
  correction_evidence: string[] | null;
}

interface ExtractionStats {
  total_pending: number;
  needs_review: number;
  by_state: Record<string, number>;
}

interface VerificationResult {
  found: boolean;
  docket_number: string;
  state_code: string;
  title: string | null;
  company: string | null;
  filing_date: string | null;
  status: string | null;
  utility_type: string | null;
  url: string | null;
  error: string | null;
}

export default function ReviewQueuePage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState<number | null>(null);

  // View mode (hearings is default, legacy for old data)
  const [activeTab, setActiveTab] = useState<'hearings' | 'legacy'>('hearings');

  // Hearing-grouped review state
  const [hearingItems, setHearingItems] = useState<HearingReviewItem[]>([]);
  const [bulkProcessing, setBulkProcessing] = useState<number | null>(null);

  // Filters
  const [entityFilter, setEntityFilter] = useState<string>('');
  const [stateFilter, setStateFilter] = useState<string>('');

  async function loadStats() {
    try {
      const res = await fetch(`${API_URL}/admin/review/stats`);
      if (res.ok) {
        setStats(await res.json());
      }
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }

  async function loadQueue() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (entityFilter) params.set('entity_type', entityFilter);
      if (stateFilter) params.set('state', stateFilter);
      params.set('limit', '50');

      const res = await fetch(`${API_URL}/admin/review/queue?${params}`);
      if (!res.ok) throw new Error('Failed to fetch review queue');
      setItems(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load queue');
    } finally {
      setLoading(false);
    }
  }

  async function loadHearingQueue() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (stateFilter) params.set('state', stateFilter);
      params.set('limit', '20');

      const res = await fetch(`${API_URL}/admin/review/hearings?${params}`);
      if (!res.ok) throw new Error('Failed to fetch hearing queue');
      setHearingItems(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load hearing queue');
    } finally {
      setLoading(false);
    }
  }

  async function handleBulkApprove(hearingId: number, action: string, threshold?: number) {
    setBulkProcessing(hearingId);
    try {
      const res = await fetch(`${API_URL}/admin/review/hearings/${hearingId}/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          confidence_threshold: threshold || 80,
        }),
      });
      if (!res.ok) throw new Error('Bulk action failed');
      // Reload the queue
      loadHearingQueue();
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Bulk action failed');
    } finally {
      setBulkProcessing(null);
    }
  }

  useEffect(() => {
    loadStats();
    if (activeTab === 'hearings') {
      loadHearingQueue();
    } else if (activeTab === 'legacy') {
      loadQueue();
    }
  }, [entityFilter, stateFilter, activeTab]);

  async function handleAction(
    item: ReviewItem,
    action: string,
    entityId?: number,
    correctedText?: string
  ) {
    setProcessing(item.id);
    try {
      const res = await fetch(`${API_URL}/admin/review/${item.entity_type}/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          correct_entity_id: entityId,
          corrected_text: correctedText,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Action failed');
      }

      // Remove from list
      setItems(items.filter(i => i.id !== item.id));
      loadStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setProcessing(null);
    }
  }

  const entityTypeLabel: Record<string, string> = {
    docket: 'Dockets',
    topic: 'Topics',
    utility: 'Utilities',
  };

  const confidenceBadge = (confidence: string) => {
    const config: Record<string, string> = {
      verified: 'badge-success',
      likely: 'badge-info',
      possible: 'badge-warning',
      unverified: 'badge-danger',
      auto: 'badge-gray',
      invalid: 'badge-danger',
    };
    return (
      <span className={`badge ${config[confidence] || config.auto}`}>
        {confidence}
      </span>
    );
  };

  return (
    <PageLayout activeTab="review" title="Review Queue" subtitle="Manual verification of entity matches">
      {/* View Mode */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', alignItems: 'center' }}>
        <span style={{ fontWeight: 600, color: 'var(--gray-600)' }}>Review entities grouped by hearing</span>
        <div style={{ flex: 1 }} />
        {/* Legacy toggle for old data */}
        {stats && stats.total > 0 && activeTab !== 'legacy' && (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => setActiveTab('legacy')}
            style={{ fontSize: '0.75rem' }}
          >
            View Legacy ({stats.total})
          </button>
        )}
        {activeTab === 'legacy' && (
          <button
            className="btn btn-primary btn-sm"
            onClick={() => setActiveTab('hearings')}
            style={{ fontSize: '0.75rem' }}
          >
            ← Back to Hearings
          </button>
        )}
      </div>

      {/* Hearings Stats */}
      {activeTab === 'hearings' && stats && (
        <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
          <div className="stat-card">
            <div className="stat-value">{stats.hearings}</div>
            <div className="stat-label">Hearings</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.total}</div>
            <div className="stat-label">Total Entities</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.dockets}</div>
            <div className="stat-label">Dockets</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.utilities}</div>
            <div className="stat-label">Utilities</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">{stats.topics}</div>
            <div className="stat-label">Topics</div>
          </div>
        </div>
      )}


      {/* Legacy Stats */}
      {activeTab === 'legacy' && stats && (
        <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
          <div className="stat-card">
            <div className="stat-value">{stats.total}</div>
            <div className="stat-label">Total Items</div>
          </div>
          <div className="stat-card" onClick={() => setEntityFilter('docket')} style={{ cursor: 'pointer' }}>
            <div className="stat-value">{stats.dockets}</div>
            <div className="stat-label">Dockets</div>
          </div>
          <div className="stat-card" onClick={() => setEntityFilter('topic')} style={{ cursor: 'pointer' }}>
            <div className="stat-value">{stats.topics}</div>
            <div className="stat-label">Topics</div>
          </div>
          <div className="stat-card" onClick={() => setEntityFilter('utility')} style={{ cursor: 'pointer' }}>
            <div className="stat-value">{stats.utilities}</div>
            <div className="stat-label">Utilities</div>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', gap: '1rem', alignItems: 'center', flexWrap: 'wrap' }}>
          <Filter size={18} style={{ color: 'var(--gray-400)' }} />

          {activeTab === 'legacy' && (
            <select
              className="form-input"
              style={{ width: '150px' }}
              value={entityFilter}
              onChange={(e) => setEntityFilter(e.target.value)}
            >
              <option value="">All Types</option>
              <option value="docket">Dockets</option>
              <option value="topic">Topics</option>
              <option value="utility">Utilities</option>
            </select>
          )}

          <select
            className="form-input"
            style={{ width: '120px' }}
            value={stateFilter}
            onChange={(e) => setStateFilter(e.target.value)}
          >
            <option value="">All States</option>
            <option value="FL">Florida</option>
            <option value="GA">Georgia</option>
            <option value="TX">Texas</option>
            <option value="CA">California</option>
            <option value="OH">Ohio</option>
          </select>

          <button
            className="btn btn-secondary"
            onClick={() => {
              if (activeTab === 'hearings') loadHearingQueue();
              else loadQueue();
            }}
          >
            <RefreshCw size={16} /> Refresh
          </button>

          {(entityFilter || stateFilter) && (
            <button
              className="btn btn-secondary"
              onClick={() => { setEntityFilter(''); setStateFilter(''); }}
            >
              Clear Filters
            </button>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
          <AlertCircle size={20} />
          <span>{error}</span>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <div className="loading">
          <div className="spinner"></div>
        </div>
      )}

      {/* Hearing-Grouped Queue */}
      {activeTab === 'hearings' && !loading && hearingItems.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <CheckCircle size={48} style={{ color: 'var(--success)', marginBottom: '1rem' }} />
          <h3 style={{ marginBottom: '0.5rem' }}>All Caught Up!</h3>
          <p style={{ color: 'var(--gray-500)' }}>No hearings need entity review right now.</p>
        </div>
      )}

      {activeTab === 'hearings' && !loading && hearingItems.map((hearing) => (
        <div
          key={`hearing-${hearing.hearing_id}`}
          className="card"
          style={{
            marginBottom: '1.5rem',
            opacity: bulkProcessing === hearing.hearing_id ? 0.5 : 1,
            position: 'relative',
            border: hearing.lowest_confidence && hearing.lowest_confidence < 70 ? '2px solid var(--warning)' : undefined,
          }}
        >
          {bulkProcessing === hearing.hearing_id && (
            <div style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10
            }}>
              <div className="spinner" style={{ width: '24px', height: '24px' }}></div>
            </div>
          )}

          {/* Hearing Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem', borderBottom: '1px solid var(--gray-200)', paddingBottom: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <span className="badge badge-primary">{hearing.state_code}</span>
                <span style={{ fontSize: '1.1rem', fontWeight: 600 }}>
                  {hearing.hearing_title || 'Untitled Hearing'}
                </span>
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                {hearing.hearing_date || 'No date'} &bull; {hearing.total_entities} entities to review
                {hearing.lowest_confidence !== undefined && (
                  <span style={{ marginLeft: '0.5rem' }}>
                    &bull; Lowest confidence: <strong style={{ color: hearing.lowest_confidence < 70 ? 'var(--warning)' : 'inherit' }}>{hearing.lowest_confidence}%</strong>
                  </span>
                )}
              </div>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn btn-success btn-sm"
                onClick={() => handleBulkApprove(hearing.hearing_id, 'approve_all')}
                title="Approve all entities"
              >
                <CheckCircle size={14} /> Approve All
              </button>
              <button
                className="btn btn-secondary btn-sm"
                onClick={() => handleBulkApprove(hearing.hearing_id, 'approve_high_confidence', 80)}
                title="Approve entities with confidence >= 80%"
              >
                Approve High Conf
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={() => handleBulkApprove(hearing.hearing_id, 'reject_all')}
                title="Reject all entities"
              >
                <XCircle size={14} /> Reject All
              </button>
            </div>
          </div>

          {/* Utilities Section */}
          {hearing.utilities.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.5rem' }}>
                Utilities ({hearing.utilities.length})
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {hearing.utilities.map((u) => (
                  <div
                    key={`util-${u.id}`}
                    style={{
                      padding: '0.5rem 0.75rem',
                      background: 'var(--gray-100)',
                      borderRadius: '4px',
                      fontSize: '0.875rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <span style={{ fontWeight: 500 }}>{u.name}</span>
                    {u.role && <span className="badge badge-gray">{u.role}</span>}
                    {confidenceBadge(u.confidence)}
                    {u.confidence_score !== null && u.confidence_score !== undefined && (
                      <span style={{ color: 'var(--gray-500)', fontSize: '0.75rem' }}>{u.confidence_score}%</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Dockets Section */}
          {hearing.dockets.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.5rem' }}>
                Dockets ({hearing.dockets.length})
                {hearing.utility_docket_matches > 0 && (
                  <span style={{ fontWeight: 400, color: 'var(--success)', marginLeft: '0.5rem' }}>
                    {hearing.utility_docket_matches} utility match{hearing.utility_docket_matches !== 1 ? 'es' : ''}
                  </span>
                )}
              </h4>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {hearing.dockets.map((d) => (
                  <div
                    key={`docket-${d.id}`}
                    style={{
                      padding: '0.75rem',
                      background: d.utility_match ? 'rgba(0, 184, 148, 0.1)' : 'var(--gray-100)',
                      borderRadius: '4px',
                      border: d.utility_match ? '1px solid var(--success)' : '1px solid var(--gray-200)',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                      <span style={{ fontFamily: 'monospace', fontWeight: 600 }}>{d.name}</span>
                      {confidenceBadge(d.confidence)}
                      {d.confidence_score !== null && d.confidence_score !== undefined && (
                        <span style={{ color: 'var(--gray-500)', fontSize: '0.75rem' }}>{d.confidence_score}%</span>
                      )}
                      {d.utility_match && (
                        <span className="badge badge-success">Utility Match</span>
                      )}
                    </div>
                    {d.known_title && (
                      <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                        {d.known_title}
                      </div>
                    )}
                    {d.known_utility && (
                      <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                        Utility: {d.known_utility}
                      </div>
                    )}
                    {d.review_reason && (
                      <div style={{ fontSize: '0.75rem', color: 'var(--warning)', marginTop: '0.25rem' }}>
                        {d.review_reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Topics Section */}
          {hearing.topics.length > 0 && (
            <div>
              <h4 style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--gray-600)', marginBottom: '0.5rem' }}>
                Topics ({hearing.topics.length})
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                {hearing.topics.map((t) => (
                  <div
                    key={`topic-${t.id}`}
                    style={{
                      padding: '0.25rem 0.5rem',
                      background: 'var(--gray-100)',
                      borderRadius: '4px',
                      fontSize: '0.875rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <span>{t.name}</span>
                    {t.category && t.category !== 'uncategorized' && (
                      <span className="badge badge-gray">{t.category}</span>
                    )}
                    {t.confidence_score !== null && t.confidence_score !== undefined && (
                      <span style={{ color: 'var(--gray-500)', fontSize: '0.75rem' }}>{t.confidence_score}%</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      ))}


      {/* Legacy Queue Items */}
      {activeTab === 'legacy' && !loading && items.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <CheckCircle size={48} style={{ color: 'var(--success)', marginBottom: '1rem' }} />
          <h3 style={{ marginBottom: '0.5rem' }}>All Caught Up!</h3>
          <p style={{ color: 'var(--gray-500)' }}>No items need review right now.</p>
        </div>
      )}

      {activeTab === 'legacy' && !loading && items.map((item) => (
        <div
          key={`${item.entity_type}-${item.id}`}
          className="card"
          style={{
            marginBottom: '1rem',
            opacity: processing === item.id ? 0.5 : 1,
            position: 'relative'
          }}
        >
          {processing === item.id && (
            <div style={{
              position: 'absolute',
              inset: 0,
              background: 'rgba(255,255,255,0.7)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 10
            }}>
              <div className="spinner" style={{ width: '24px', height: '24px' }}></div>
            </div>
          )}

          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                <span style={{ fontSize: '1.1rem', fontWeight: 600, fontFamily: 'monospace' }}>
                  {item.original_text}
                </span>
                {confidenceBadge(item.confidence)}
                <span className="badge badge-gray">{item.entity_type}</span>
                {item.confidence_score !== null && (
                  <span className="badge badge-gray">Score: {item.confidence_score}</span>
                )}
                {item.match_type && (
                  <span className={`badge ${item.match_type === 'exact' ? 'badge-success' : item.match_type === 'fuzzy' ? 'badge-warning' : 'badge-gray'}`}>
                    {item.match_type}
                  </span>
                )}
              </div>
              <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)' }}>
                {item.hearing_title} &bull; {item.hearing_date || 'No date'}
              </div>
              {item.review_reason && (
                <div style={{ fontSize: '0.875rem', color: 'var(--warning)', marginTop: '0.25rem' }}>
                  {item.review_reason}
                </div>
              )}
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn btn-secondary"
                style={{ padding: '0.375rem 0.75rem' }}
                onClick={() => handleAction(item, 'skip')}
              >
                <SkipForward size={16} /> Skip
              </button>
              <button
                className="btn btn-danger"
                style={{ padding: '0.375rem 0.75rem' }}
                onClick={() => handleAction(item, 'invalid')}
              >
                <XCircle size={16} /> Invalid
              </button>
            </div>
          </div>

          {/* Context */}
          {item.transcript_context && (
            <div style={{
              background: 'var(--gray-100)',
              padding: '0.75rem',
              borderRadius: 'var(--radius)',
              marginBottom: '1rem',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              color: 'var(--gray-600)'
            }}>
              "...{item.transcript_context}..."
            </div>
          )}

          {/* Suggestions */}
          {item.suggestions.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.5rem', color: 'var(--gray-600)' }}>
                Suggested matches:
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                {item.suggestions.map((suggestion) => (
                  <div
                    key={suggestion.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '0.5rem 0.75rem',
                      border: '1px solid var(--gray-200)',
                      borderRadius: 'var(--radius)',
                      background: 'white'
                    }}
                  >
                    <div>
                      <span style={{ fontWeight: 500 }}>
                        {suggestion.normalized_id || suggestion.name}
                      </span>
                      {(suggestion.title || suggestion.utility_name) && (
                        <span style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginLeft: '0.5rem' }}>
                          {suggestion.title || suggestion.utility_name}
                        </span>
                      )}
                      <span className="badge badge-info" style={{ marginLeft: '0.5rem' }}>
                        {Math.round(suggestion.score)}% match
                      </span>
                    </div>
                    <button
                      className="btn btn-primary"
                      style={{ padding: '0.25rem 0.75rem' }}
                      onClick={() => handleAction(item, 'link', suggestion.id)}
                    >
                      <Link2 size={16} /> Link
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Manual Correction */}
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <input
              type="text"
              className="form-input"
              placeholder="Or enter corrected value..."
              style={{ flex: 1 }}
              id={`correct-${item.entity_type}-${item.id}`}
            />
            <button
              className="btn btn-secondary"
              onClick={() => {
                const input = document.getElementById(`correct-${item.entity_type}-${item.id}`) as HTMLInputElement;
                if (input.value) {
                  handleAction(item, 'correct', undefined, input.value);
                }
              }}
            >
              <CheckCircle size={16} /> Correct
            </button>
          </div>

          {/* Search Link */}
          <div style={{ marginTop: '0.5rem' }}>
            <button
              className="btn"
              style={{
                padding: '0.25rem 0.5rem',
                fontSize: '0.75rem',
                background: 'transparent',
                color: 'var(--primary)'
              }}
            >
              <Search size={14} /> Search all {item.entity_type}s
            </button>
          </div>
        </div>
      ))}
    </PageLayout>
  );
}
