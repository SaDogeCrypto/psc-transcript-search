'use client';

import { useEffect, useState, useCallback } from 'react';
import { PageLayout } from '@/components/Layout';
import {
  CheckCircle2,
  XCircle,
  Link2,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Loader2,
  Building2,
  FileText,
  Tag,
  Plus,
  Search,
  RefreshCw,
} from 'lucide-react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001';

// Types
interface ReviewStats {
  total: number;
  dockets: number;
  utilities: number;
  topics: number;
  hearings_with_pending: number;
}

interface ReviewItem {
  type: string;
  link_id: number;
  hearing_id: number;
  hearing_title: string | null;
  hearing_date: string | null;
  entity_id: number;
  entity_name: string | null;
  entity_title?: string | null;
  role?: string | null;
  category?: string | null;
  confidence_score: number | null;
  match_type: string | null;
  review_reason: string | null;
  context_summary: string | null;
  relevance_score?: number | null;
}

interface HearingReviewItem {
  hearing_id: number;
  hearing_title: string | null;
  hearing_date: string | null;
  docket_number: string | null;
  pending_dockets: number;
  pending_utilities: number;
  pending_topics: number;
  total_pending: number;
}

interface Utility {
  id: number;
  name: string;
  normalized_name: string;
  utility_type: string | null;
  sectors: string[];
  aliases: string[];
  mention_count: number;
}

interface Topic {
  id: number;
  name: string;
  slug: string;
  category: string | null;
  description: string | null;
  mention_count: number;
}

interface HearingLinks {
  hearing_id: number;
  hearing_title: string | null;
  dockets: Array<{
    link_id: number;
    docket_id: number;
    docket_number: string | null;
    docket_title: string | null;
    is_primary: boolean;
    confidence_score: number | null;
    needs_review: boolean;
  }>;
  utilities: Array<{
    link_id: number;
    utility_id: number;
    utility_name: string | null;
    role: string | null;
    confidence_score: number | null;
    needs_review: boolean;
  }>;
  topics: Array<{
    link_id: number;
    topic_id: number;
    topic_name: string | null;
    category: string | null;
    relevance_score: number | null;
    confidence_score: number | null;
    needs_review: boolean;
  }>;
}

export default function ReviewPage() {
  const [stats, setStats] = useState<ReviewStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Review queue
  const [reviewQueue, setReviewQueue] = useState<ReviewItem[]>([]);
  const [hearingsQueue, setHearingsQueue] = useState<HearingReviewItem[]>([]);
  const [selectedEntityType, setSelectedEntityType] = useState<string | null>(null);

  // Entity management
  const [utilities, setUtilities] = useState<Utility[]>([]);
  const [topics, setTopics] = useState<Topic[]>([]);
  const [showUtilities, setShowUtilities] = useState(false);
  const [showTopics, setShowTopics] = useState(false);

  // Hearing detail view
  const [selectedHearing, setSelectedHearing] = useState<number | null>(null);
  const [hearingLinks, setHearingLinks] = useState<HearingLinks | null>(null);
  const [loadingLinks, setLoadingLinks] = useState(false);

  // Action state
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const loadStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/review/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to load stats:', err);
    }
  }, []);

  const loadReviewQueue = useCallback(async (entityType?: string) => {
    try {
      const url = entityType
        ? `${API_URL}/admin/review/queue?entity_type=${entityType}&limit=50`
        : `${API_URL}/admin/review/queue?limit=50`;
      const res = await fetch(url);
      if (res.ok) {
        const data = await res.json();
        setReviewQueue(data.items || []);
      }
    } catch (err) {
      console.error('Failed to load review queue:', err);
    }
  }, []);

  const loadHearingsQueue = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/review/hearings?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setHearingsQueue(data.items || []);
      }
    } catch (err) {
      console.error('Failed to load hearings queue:', err);
    }
  }, []);

  const loadUtilities = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/review/utilities?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setUtilities(data.items || []);
      }
    } catch (err) {
      console.error('Failed to load utilities:', err);
    }
  }, []);

  const loadTopics = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/admin/review/topics?limit=100`);
      if (res.ok) {
        const data = await res.json();
        setTopics(data.items || []);
      }
    } catch (err) {
      console.error('Failed to load topics:', err);
    }
  }, []);

  const loadHearingLinks = useCallback(async (hearingId: number) => {
    setLoadingLinks(true);
    try {
      const res = await fetch(`${API_URL}/admin/review/hearings/${hearingId}/links`);
      if (res.ok) {
        const data = await res.json();
        setHearingLinks(data);
      }
    } catch (err) {
      console.error('Failed to load hearing links:', err);
    } finally {
      setLoadingLinks(false);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      await Promise.all([
        loadStats(),
        loadReviewQueue(selectedEntityType || undefined),
        loadHearingsQueue(),
        loadUtilities(),
        loadTopics(),
      ]);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load data');
    } finally {
      setLoading(false);
    }
  }, [loadStats, loadReviewQueue, loadHearingsQueue, loadUtilities, loadTopics, selectedEntityType]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  useEffect(() => {
    if (selectedHearing) {
      loadHearingLinks(selectedHearing);
    }
  }, [selectedHearing, loadHearingLinks]);

  // Review actions
  const reviewLink = async (linkType: string, linkId: number, action: string, correctEntityId?: number) => {
    setActionLoading(linkId);
    try {
      const endpoint = linkType === 'docket' ? 'docket-link' : linkType === 'utility' ? 'utility-link' : 'topic-link';
      const res = await fetch(`${API_URL}/admin/review/${endpoint}/${linkId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, correct_entity_id: correctEntityId }),
      });

      if (res.ok) {
        await loadData();
        if (selectedHearing) {
          await loadHearingLinks(selectedHearing);
        }
      }
    } catch (err) {
      console.error('Failed to review link:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const bulkReview = async (hearingId: number, action: string) => {
    setActionLoading(hearingId);
    try {
      const res = await fetch(`${API_URL}/admin/review/hearings/${hearingId}/bulk`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, confidence_threshold: 80 }),
      });

      if (res.ok) {
        await loadData();
      }
    } catch (err) {
      console.error('Failed to bulk review:', err);
    } finally {
      setActionLoading(null);
    }
  };

  const getConfidenceColor = (score: number | null) => {
    if (score === null) return 'var(--gray-400)';
    if (score >= 80) return 'var(--success)';
    if (score >= 50) return 'var(--warning)';
    return 'var(--danger)';
  };

  const getConfidenceBadge = (score: number | null) => {
    if (score === null) return 'badge-secondary';
    if (score >= 80) return 'badge-success';
    if (score >= 50) return 'badge-warning';
    return 'badge-danger';
  };

  if (loading) {
    return (
      <PageLayout activeTab="review">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
          <Loader2 className="animate-spin" size={32} />
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="review">
      <div style={{ padding: '1.5rem' }}>
        {error && (
          <div className="alert alert-danger" style={{ marginBottom: '1rem' }}>
            <AlertCircle size={16} /> {error}
          </div>
        )}

        {/* Stats Row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: '1rem', marginBottom: '1.5rem' }}>
          <div className="card" style={{ padding: '1rem', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--primary)' }}>{stats?.total || 0}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Total Pending</div>
          </div>
          <div className="card" style={{ padding: '1rem', textAlign: 'center', cursor: 'pointer', background: selectedEntityType === 'docket' ? 'var(--primary-50)' : undefined }}
            onClick={() => { setSelectedEntityType(selectedEntityType === 'docket' ? null : 'docket'); loadReviewQueue('docket'); }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--info)' }}>{stats?.dockets || 0}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Dockets</div>
          </div>
          <div className="card" style={{ padding: '1rem', textAlign: 'center', cursor: 'pointer', background: selectedEntityType === 'utility' ? 'var(--primary-50)' : undefined }}
            onClick={() => { setSelectedEntityType(selectedEntityType === 'utility' ? null : 'utility'); loadReviewQueue('utility'); }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--success)' }}>{stats?.utilities || 0}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Utilities</div>
          </div>
          <div className="card" style={{ padding: '1rem', textAlign: 'center', cursor: 'pointer', background: selectedEntityType === 'topic' ? 'var(--primary-50)' : undefined }}
            onClick={() => { setSelectedEntityType(selectedEntityType === 'topic' ? null : 'topic'); loadReviewQueue('topic'); }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--warning)' }}>{stats?.topics || 0}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Topics</div>
          </div>
          <div className="card" style={{ padding: '1rem', textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', fontWeight: 700, color: 'var(--gray-600)' }}>{stats?.hearings_with_pending || 0}</div>
            <div style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>Hearings</div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
          {/* Left Column - Review Queue */}
          <div>
            {/* Hearings with Pending Reviews */}
            <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileText size={18} style={{ color: 'var(--primary)' }} />
                  Hearings for Review
                </h3>
                <button onClick={loadData} className="btn btn-secondary" style={{ padding: '0.25rem 0.5rem' }}>
                  <RefreshCw size={14} />
                </button>
              </div>

              {hearingsQueue.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                  <CheckCircle2 size={32} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
                  <p>No hearings need review</p>
                </div>
              ) : (
                <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                  {hearingsQueue.map((hearing) => (
                    <div
                      key={hearing.hearing_id}
                      style={{
                        padding: '0.75rem',
                        borderBottom: '1px solid var(--gray-200)',
                        cursor: 'pointer',
                        background: selectedHearing === hearing.hearing_id ? 'var(--primary-50)' : undefined,
                      }}
                      onClick={() => setSelectedHearing(hearing.hearing_id)}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ fontWeight: 500, fontSize: '0.9rem' }}>
                            {hearing.hearing_title || 'Untitled Hearing'}
                          </div>
                          <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                            {hearing.hearing_date} {hearing.docket_number && `- ${hearing.docket_number}`}
                          </div>
                        </div>
                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          {hearing.pending_dockets > 0 && (
                            <span className="badge badge-info" style={{ fontSize: '0.7rem' }}>
                              {hearing.pending_dockets} docket{hearing.pending_dockets > 1 ? 's' : ''}
                            </span>
                          )}
                          {hearing.pending_utilities > 0 && (
                            <span className="badge badge-success" style={{ fontSize: '0.7rem' }}>
                              {hearing.pending_utilities} util
                            </span>
                          )}
                          {hearing.pending_topics > 0 && (
                            <span className="badge badge-warning" style={{ fontSize: '0.7rem' }}>
                              {hearing.pending_topics} topic{hearing.pending_topics > 1 ? 's' : ''}
                            </span>
                          )}
                        </div>
                      </div>
                      {selectedHearing === hearing.hearing_id && (
                        <div style={{ marginTop: '0.5rem', display: 'flex', gap: '0.5rem' }}>
                          <button
                            onClick={(e) => { e.stopPropagation(); bulkReview(hearing.hearing_id, 'approve_all'); }}
                            disabled={actionLoading === hearing.hearing_id}
                            className="btn btn-success"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                          >
                            {actionLoading === hearing.hearing_id ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                            {' '}Approve All
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); bulkReview(hearing.hearing_id, 'approve_high_confidence'); }}
                            disabled={actionLoading === hearing.hearing_id}
                            className="btn btn-secondary"
                            style={{ padding: '0.25rem 0.5rem', fontSize: '0.75rem' }}
                          >
                            Approve High Conf
                          </button>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Individual Review Queue */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>
                Review Queue {selectedEntityType && `(${selectedEntityType}s)`}
              </h3>

              {reviewQueue.length === 0 ? (
                <div style={{ padding: '2rem', textAlign: 'center', color: 'var(--gray-500)' }}>
                  <CheckCircle2 size={32} style={{ marginBottom: '0.5rem', opacity: 0.5 }} />
                  <p>No items need review</p>
                </div>
              ) : (
                <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
                  {reviewQueue.map((item) => (
                    <div
                      key={`${item.type}-${item.link_id}`}
                      style={{
                        padding: '0.75rem',
                        borderBottom: '1px solid var(--gray-200)',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                        <div>
                          <span className={`badge ${item.type === 'docket' ? 'badge-info' : item.type === 'utility' ? 'badge-success' : 'badge-warning'}`} style={{ fontSize: '0.7rem', marginRight: '0.5rem' }}>
                            {item.type}
                          </span>
                          <span style={{ fontWeight: 500 }}>{item.entity_name}</span>
                          {item.entity_title && (
                            <div style={{ fontSize: '0.8rem', color: 'var(--gray-600)' }}>{item.entity_title}</div>
                          )}
                        </div>
                        <span className={`badge ${getConfidenceBadge(item.confidence_score)}`} style={{ fontSize: '0.7rem' }}>
                          {item.confidence_score !== null ? `${item.confidence_score}%` : 'N/A'}
                        </span>
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', marginBottom: '0.5rem' }}>
                        {item.hearing_title || 'Unknown Hearing'} ({item.hearing_date})
                      </div>
                      {item.review_reason && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--warning-600)', marginBottom: '0.5rem' }}>
                          {item.review_reason}
                        </div>
                      )}
                      <div style={{ display: 'flex', gap: '0.5rem' }}>
                        <button
                          onClick={() => reviewLink(item.type, item.link_id, 'approve')}
                          disabled={actionLoading === item.link_id}
                          className="btn btn-success"
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                        >
                          <CheckCircle2 size={12} /> Approve
                        </button>
                        <button
                          onClick={() => reviewLink(item.type, item.link_id, 'reject')}
                          disabled={actionLoading === item.link_id}
                          className="btn btn-danger"
                          style={{ padding: '0.2rem 0.5rem', fontSize: '0.75rem' }}
                        >
                          <XCircle size={12} /> Reject
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Right Column - Hearing Detail & Entity Management */}
          <div>
            {/* Hearing Links Detail */}
            {selectedHearing && (
              <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
                <h3 style={{ margin: '0 0 1rem 0', fontSize: '1rem', fontWeight: 600 }}>
                  Hearing #{selectedHearing} Links
                </h3>

                {loadingLinks ? (
                  <div style={{ display: 'flex', justifyContent: 'center', padding: '2rem' }}>
                    <Loader2 className="animate-spin" size={24} />
                  </div>
                ) : hearingLinks ? (
                  <div>
                    {/* Docket Links */}
                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--info)' }}>
                        Dockets ({hearingLinks.dockets.length})
                      </div>
                      {hearingLinks.dockets.length === 0 ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', padding: '0.5rem 0' }}>No dockets linked</div>
                      ) : (
                        hearingLinks.dockets.map((d) => (
                          <div key={d.link_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0', borderBottom: '1px solid var(--gray-100)' }}>
                            <div>
                              <span style={{ fontWeight: 500 }}>{d.docket_number}</span>
                              {d.is_primary && <span className="badge badge-primary" style={{ marginLeft: '0.5rem', fontSize: '0.65rem' }}>Primary</span>}
                              {d.needs_review && <span className="badge badge-warning" style={{ marginLeft: '0.5rem', fontSize: '0.65rem' }}>Review</span>}
                            </div>
                            <span className={`badge ${getConfidenceBadge(d.confidence_score)}`} style={{ fontSize: '0.65rem' }}>
                              {d.confidence_score}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Utility Links */}
                    <div style={{ marginBottom: '1rem' }}>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--success)' }}>
                        Utilities ({hearingLinks.utilities.length})
                      </div>
                      {hearingLinks.utilities.length === 0 ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', padding: '0.5rem 0' }}>No utilities linked</div>
                      ) : (
                        hearingLinks.utilities.map((u) => (
                          <div key={u.link_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0', borderBottom: '1px solid var(--gray-100)' }}>
                            <div>
                              <span style={{ fontWeight: 500 }}>{u.utility_name}</span>
                              {u.role && <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-500)' }}>({u.role})</span>}
                              {u.needs_review && <span className="badge badge-warning" style={{ marginLeft: '0.5rem', fontSize: '0.65rem' }}>Review</span>}
                            </div>
                            <span className={`badge ${getConfidenceBadge(u.confidence_score)}`} style={{ fontSize: '0.65rem' }}>
                              {u.confidence_score}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>

                    {/* Topic Links */}
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.85rem', marginBottom: '0.5rem', color: 'var(--warning)' }}>
                        Topics ({hearingLinks.topics.length})
                      </div>
                      {hearingLinks.topics.length === 0 ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', padding: '0.5rem 0' }}>No topics linked</div>
                      ) : (
                        hearingLinks.topics.map((t) => (
                          <div key={t.link_id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.4rem 0', borderBottom: '1px solid var(--gray-100)' }}>
                            <div>
                              <span style={{ fontWeight: 500 }}>{t.topic_name}</span>
                              {t.category && <span style={{ marginLeft: '0.5rem', fontSize: '0.75rem', color: 'var(--gray-500)' }}>({t.category})</span>}
                              {t.needs_review && <span className="badge badge-warning" style={{ marginLeft: '0.5rem', fontSize: '0.65rem' }}>Review</span>}
                            </div>
                            <span className={`badge ${getConfidenceBadge(t.confidence_score)}`} style={{ fontSize: '0.65rem' }}>
                              {t.confidence_score}%
                            </span>
                          </div>
                        ))
                      )}
                    </div>
                  </div>
                ) : null}
              </div>
            )}

            {/* Utilities List */}
            <div className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                onClick={() => setShowUtilities(!showUtilities)}
              >
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Building2 size={18} style={{ color: 'var(--success)' }} />
                  Utilities ({utilities.length})
                </h3>
                {showUtilities ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
              </div>

              {showUtilities && (
                <div style={{ marginTop: '1rem', maxHeight: '300px', overflowY: 'auto' }}>
                  {utilities.map((u) => (
                    <div key={u.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--gray-100)', fontSize: '0.85rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontWeight: 500 }}>{u.name}</span>
                        <span className="badge badge-secondary" style={{ fontSize: '0.65rem' }}>{u.mention_count} mentions</span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {u.utility_type} | {u.sectors.join(', ')}
                      </div>
                      {u.aliases.length > 0 && (
                        <div style={{ fontSize: '0.7rem', color: 'var(--gray-400)' }}>
                          Aliases: {u.aliases.join(', ')}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Topics List */}
            <div className="card" style={{ padding: '1.25rem' }}>
              <div
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer' }}
                onClick={() => setShowTopics(!showTopics)}
              >
                <h3 style={{ margin: 0, fontSize: '1rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Tag size={18} style={{ color: 'var(--warning)' }} />
                  Topics ({topics.length})
                </h3>
                {showTopics ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
              </div>

              {showTopics && (
                <div style={{ marginTop: '1rem', maxHeight: '300px', overflowY: 'auto' }}>
                  {topics.map((t) => (
                    <div key={t.id} style={{ padding: '0.5rem 0', borderBottom: '1px solid var(--gray-100)', fontSize: '0.85rem' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ fontWeight: 500 }}>{t.name}</span>
                        <span className="badge badge-secondary" style={{ fontSize: '0.65rem' }}>{t.mention_count} mentions</span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                        {t.category} {t.description && `- ${t.description}`}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </PageLayout>
  );
}
