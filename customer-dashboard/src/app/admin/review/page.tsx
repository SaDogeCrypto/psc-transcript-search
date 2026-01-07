'use client';

import { useEffect, useState } from 'react';
import {
  CheckCircle, XCircle, Link2, SkipForward,
  Search, RefreshCw, AlertCircle, Filter, Sparkles,
  ExternalLink, Globe, Loader2
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

  // Extraction review state
  const [extractionItems, setExtractionItems] = useState<ExtractionReviewItem[]>([]);
  const [extractionStats, setExtractionStats] = useState<ExtractionStats | null>(null);
  const [activeTab, setActiveTab] = useState<'extraction' | 'legacy'>('extraction');
  const [verifications, setVerifications] = useState<Record<number, VerificationResult>>({});
  const [verifying, setVerifying] = useState<number | null>(null);
  const [matching, setMatching] = useState<number | null>(null);
  const [matchResults, setMatchResults] = useState<Record<number, { success: boolean; message: string }>>({});

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

  async function loadExtractionStats() {
    try {
      const res = await fetch(`${API_URL}/admin/review/extraction/stats`);
      if (res.ok) {
        setExtractionStats(await res.json());
      }
    } catch (err) {
      console.error('Failed to load extraction stats:', err);
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

  async function loadExtractionQueue() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (stateFilter) params.set('state', stateFilter);
      params.set('status', 'needs_review');
      params.set('limit', '50');

      const res = await fetch(`${API_URL}/admin/review/extraction/queue?${params}`);
      if (!res.ok) throw new Error('Failed to fetch extraction queue');
      setExtractionItems(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load extraction queue');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
    loadExtractionStats();
    if (activeTab === 'extraction') {
      loadExtractionQueue();
    } else {
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

  async function handleExtractionAction(
    item: ExtractionReviewItem,
    action: 'accept' | 'accept_suggestion' | 'correct' | 'reject',
    correctedDocketId?: number
  ) {
    setProcessing(item.id);
    try {
      const res = await fetch(`${API_URL}/admin/review/extraction/${item.id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          action,
          corrected_docket_id: correctedDocketId,
        }),
      });

      if (!res.ok) {
        const error = await res.json();
        throw new Error(error.detail || 'Action failed');
      }

      // Remove from list
      setExtractionItems(extractionItems.filter(i => i.id !== item.id));
      loadExtractionStats();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Action failed');
    } finally {
      setProcessing(null);
    }
  }

  async function verifyExtraction(item: ExtractionReviewItem) {
    setVerifying(item.id);
    try {
      const res = await fetch(`${API_URL}/admin/review/extraction/${item.id}/verify`);
      if (!res.ok) {
        throw new Error('Verification failed');
      }
      const result: VerificationResult = await res.json();
      setVerifications(prev => ({ ...prev, [item.id]: result }));
    } catch (err) {
      setVerifications(prev => ({
        ...prev,
        [item.id]: {
          found: false,
          docket_number: item.raw_text,
          state_code: item.state_code || '',
          title: null,
          company: null,
          filing_date: null,
          status: null,
          utility_type: null,
          url: null,
          error: err instanceof Error ? err.message : 'Verification failed'
        }
      }));
    } finally {
      setVerifying(null);
    }
  }

  async function matchFromSource(item: ExtractionReviewItem) {
    setMatching(item.id);
    try {
      const res = await fetch(`${API_URL}/admin/review/extraction/${item.id}/match-from-source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      if (!res.ok) {
        throw new Error('Match failed');
      }
      const result = await res.json();
      setMatchResults(prev => ({ ...prev, [item.id]: { success: result.success, message: result.message } }));

      if (result.success) {
        // Remove from list after successful match
        setExtractionItems(prev => prev.filter(i => i.id !== item.id));
        // Refresh stats
        loadExtractionStats();
      }
    } catch (err) {
      setMatchResults(prev => ({
        ...prev,
        [item.id]: { success: false, message: err instanceof Error ? err.message : 'Match failed' }
      }));
    } finally {
      setMatching(null);
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
      {/* Tab Switcher */}
      <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
        <button
          className={`btn ${activeTab === 'extraction' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('extraction')}
        >
          <Sparkles size={16} />
          Smart Extraction
          {extractionStats && extractionStats.needs_review > 0 && (
            <span className="badge badge-warning" style={{ marginLeft: '0.5rem' }}>
              {extractionStats.needs_review}
            </span>
          )}
        </button>
        <button
          className={`btn ${activeTab === 'legacy' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setActiveTab('legacy')}
        >
          Legacy Review
          {stats && stats.total > 0 && (
            <span className="badge badge-gray" style={{ marginLeft: '0.5rem' }}>
              {stats.total}
            </span>
          )}
        </button>
      </div>

      {/* Extraction Stats */}
      {activeTab === 'extraction' && extractionStats && (
        <div className="stats-grid" style={{ marginBottom: '1.5rem' }}>
          <div className="stat-card">
            <div className="stat-value">{extractionStats.needs_review}</div>
            <div className="stat-label">Needs Review</div>
          </div>
          {Object.entries(extractionStats.by_state).map(([state, count]) => (
            <div
              key={state}
              className="stat-card"
              onClick={() => setStateFilter(state)}
              style={{ cursor: 'pointer' }}
            >
              <div className="stat-value">{count}</div>
              <div className="stat-label">{state}</div>
            </div>
          ))}
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
            onClick={() => activeTab === 'extraction' ? loadExtractionQueue() : loadQueue()}
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

      {/* Extraction Queue Items */}
      {activeTab === 'extraction' && !loading && extractionItems.length === 0 && (
        <div className="card" style={{ textAlign: 'center', padding: '3rem' }}>
          <CheckCircle size={48} style={{ color: 'var(--success)', marginBottom: '1rem' }} />
          <h3 style={{ marginBottom: '0.5rem' }}>All Caught Up!</h3>
          <p style={{ color: 'var(--gray-500)' }}>No extraction candidates need review right now.</p>
        </div>
      )}

      {activeTab === 'extraction' && !loading && extractionItems.map((item) => (
        <div
          key={`extraction-${item.id}`}
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
                <span style={{ fontSize: '1.25rem', fontWeight: 600, fontFamily: 'monospace' }}>
                  {item.raw_text}
                </span>
                <span className="badge badge-info">{item.state_code}</span>
                <span className={`badge ${item.format_valid ? 'badge-success' : 'badge-warning'}`}>
                  {item.format_valid ? 'Valid Format' : 'Invalid Format'}
                </span>
                <span className="badge badge-gray">
                  Score: {item.confidence_score}
                </span>
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
              {/* Verify button for new docket candidates */}
              {item.match_type === 'none' && !verifications[item.id] && (
                <button
                  className="btn btn-secondary"
                  style={{ padding: '0.375rem 0.75rem' }}
                  onClick={() => verifyExtraction(item)}
                  disabled={verifying === item.id}
                >
                  {verifying === item.id ? (
                    <><Loader2 size={16} className="spin" /> Verifying...</>
                  ) : (
                    <><Globe size={16} /> Verify on Source</>
                  )}
                </button>
              )}
              {!item.suggested_correction && item.match_type === 'none' && (
                <button
                  className="btn btn-primary"
                  style={{ padding: '0.375rem 0.75rem' }}
                  onClick={() => handleExtractionAction(item, 'accept')}
                >
                  <CheckCircle size={16} /> Accept as New
                </button>
              )}
              <button
                className="btn btn-danger"
                style={{ padding: '0.375rem 0.75rem' }}
                onClick={() => handleExtractionAction(item, 'reject')}
              >
                <XCircle size={16} /> Reject
              </button>
            </div>
          </div>

          {/* Context */}
          {(item.context_before || item.context_after) && (
            <div style={{
              background: 'var(--gray-100)',
              padding: '0.75rem',
              borderRadius: 'var(--radius)',
              marginBottom: '1rem',
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              color: 'var(--gray-600)'
            }}>
              {item.context_before && <span>...{item.context_before}</span>}
              <span style={{ fontWeight: 700, color: 'var(--primary)' }}> [{item.raw_text}] </span>
              {item.context_after && <span>{item.context_after}...</span>}
            </div>
          )}

          {/* Verification Result */}
          {verifications[item.id] && (
            <div style={{
              background: verifications[item.id].found ? 'var(--success-bg)' : 'var(--danger-bg)',
              border: `1px solid ${verifications[item.id].found ? 'var(--success)' : 'var(--danger)'}`,
              padding: '0.75rem',
              borderRadius: 'var(--radius)',
              marginBottom: '1rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
                    {verifications[item.id].found ? (
                      <CheckCircle size={18} style={{ color: 'var(--success)' }} />
                    ) : (
                      <XCircle size={18} style={{ color: 'var(--danger)' }} />
                    )}
                    <span style={{ fontWeight: 600 }}>
                      {verifications[item.id].found ? 'Verified on Source' : 'Not Found on Source'}
                    </span>
                  </div>
                  {verifications[item.id].found && (
                    <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>
                      {verifications[item.id].title && (
                        <div><strong>Title:</strong> {verifications[item.id].title}</div>
                      )}
                      {verifications[item.id].company && (
                        <div><strong>Company:</strong> {verifications[item.id].company}</div>
                      )}
                      {verifications[item.id].utility_type && (
                        <div><strong>Utility Type:</strong> {verifications[item.id].utility_type}</div>
                      )}
                      {verifications[item.id].filing_date && (
                        <div><strong>Filed:</strong> {verifications[item.id].filing_date}</div>
                      )}
                      {verifications[item.id].status && (
                        <div><strong>Status:</strong> {verifications[item.id].status}</div>
                      )}
                    </div>
                  )}
                  {verifications[item.id].error && (
                    <div style={{ fontSize: '0.875rem', color: 'var(--danger)' }}>
                      Error: {verifications[item.id].error}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', alignItems: 'flex-end' }}>
                  {verifications[item.id].url && (
                    <a
                      href={verifications[item.id].url!}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="btn btn-secondary"
                      style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                    >
                      <ExternalLink size={14} /> View on PSC
                    </a>
                  )}
                  {verifications[item.id].found && !matchResults[item.id]?.success && (
                    <button
                      onClick={() => matchFromSource(item)}
                      disabled={matching === item.id}
                      className="btn btn-primary"
                      style={{ padding: '0.25rem 0.75rem', fontSize: '0.75rem' }}
                    >
                      {matching === item.id ? (
                        <><Loader2 size={14} className="spin" /> Matching...</>
                      ) : (
                        <><CheckCircle size={14} /> Match &amp; Create Docket</>
                      )}
                    </button>
                  )}
                  {matchResults[item.id] && (
                    <span style={{
                      fontSize: '0.75rem',
                      color: matchResults[item.id].success ? 'var(--success)' : 'var(--danger)'
                    }}>
                      {matchResults[item.id].message}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Format Issues */}
          {item.format_issues && item.format_issues.length > 0 && (
            <div style={{ marginBottom: '1rem' }}>
              <div style={{ fontSize: '0.875rem', fontWeight: 500, marginBottom: '0.5rem', color: 'var(--gray-600)' }}>
                Format issues:
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                {item.format_issues.map((issue, idx) => (
                  <span key={idx} className="badge badge-warning">{issue}</span>
                ))}
              </div>
            </div>
          )}

          {/* Suggested Correction */}
          {item.suggested_correction && (
            <div style={{
              background: 'var(--success-bg)',
              border: '1px solid var(--success)',
              padding: '0.75rem',
              borderRadius: 'var(--radius)',
              marginBottom: '1rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.25rem' }}>
                    Suggested correction:
                  </div>
                  <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                    {item.raw_text} → <span style={{ color: 'var(--success)' }}>{item.suggested_correction}</span>
                  </div>
                  {item.matched_docket_title && (
                    <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                      {item.matched_docket_title}
                    </div>
                  )}
                  {item.correction_evidence && item.correction_evidence.length > 0 && (
                    <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                      Evidence: {item.correction_evidence.join(', ')}
                    </div>
                  )}
                </div>
                <button
                  className="btn btn-success"
                  onClick={() => handleExtractionAction(item, 'accept_suggestion')}
                >
                  <CheckCircle size={16} /> Accept Correction
                </button>
              </div>
            </div>
          )}

          {/* Matched Known Docket */}
          {item.match_type === 'exact' && item.matched_docket_number && (
            <div style={{
              background: 'var(--info-bg)',
              border: '1px solid var(--info)',
              padding: '0.75rem',
              borderRadius: 'var(--radius)',
              marginBottom: '1rem',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ fontSize: '0.875rem', color: 'var(--gray-600)', marginBottom: '0.25rem' }}>
                    Exact match found:
                  </div>
                  <div style={{ fontFamily: 'monospace', fontWeight: 600 }}>
                    {item.matched_docket_number}
                  </div>
                  {item.matched_docket_title && (
                    <div style={{ fontSize: '0.875rem', color: 'var(--gray-500)', marginTop: '0.25rem' }}>
                      {item.matched_docket_title}
                    </div>
                  )}
                </div>
                <button
                  className="btn btn-primary"
                  onClick={() => handleExtractionAction(item, 'accept')}
                >
                  <Link2 size={16} /> Link & Accept
                </button>
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
