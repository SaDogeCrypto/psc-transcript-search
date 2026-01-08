'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  AlertCircle,
  Clock,
  DollarSign,
  FileAudio,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getAdminStats, getHearings, type AdminStats, type Hearing } from '@/lib/api';

function StatCard({ value, label }: { value: string | number; label: string }) {
  return (
    <div className="stat-card">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
    </div>
  );
}

function PipelineStatusCard({
  pending,
  transcribed,
  analyzed,
  failed,
}: {
  pending: number;
  transcribed: number;
  analyzed: number;
  failed: number;
}) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Processing Status</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Clock size={18} color="#ca8a04" />
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Pending</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{pending}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} color="#2563eb" />
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Transcribed</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{transcribed}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={18} color="#16a34a" />
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Analyzed</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{analyzed}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={18} color="#dc2626" />
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Failed</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600, color: failed > 0 ? '#dc2626' : 'inherit' }}>{failed}</span>
        </div>
      </div>
    </div>
  );
}

function CostCard({
  transcription,
  analysis,
  total,
}: {
  transcription: number;
  analysis: number;
  total: number;
}) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Cost Breakdown</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.9rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--gray-500)' }}>Transcription</span>
          <span style={{ fontWeight: 600 }}>${transcription.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--gray-500)' }}>Analysis</span>
          <span style={{ fontWeight: 600 }}>${analysis.toFixed(2)}</span>
        </div>
        <div style={{ borderTop: '1px solid var(--gray-200)', paddingTop: '0.5rem', marginTop: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600 }}>Total</span>
          <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>${total.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}

function RecentHearingsCard({ hearings }: { hearings: Hearing[] }) {
  const getStatusBadge = (status: string | null) => {
    const classes: Record<string, string> = {
      analyzed: 'badge-success',
      failed: 'badge-danger',
      transcribed: 'badge-info',
      transcribing: 'badge-info',
      pending: 'badge-gray',
    };
    return classes[status || 'pending'] || 'badge-gray';
  };

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ color: 'var(--gray-700)' }}>Recent Hearings</h3>
        <Link href="/hearings" style={{ color: 'var(--primary)', fontSize: '0.85rem', textDecoration: 'none' }}>
          View all
        </Link>
      </div>
      {hearings.length === 0 ? (
        <p style={{ color: 'var(--gray-500)', textAlign: 'center', padding: '1rem' }}>No hearings yet</p>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
          {hearings.slice(0, 5).map((h) => (
            <div key={h.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0', borderBottom: '1px solid var(--gray-100)' }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 500, fontSize: '0.9rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {h.title || 'Untitled Hearing'}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  {h.state_code} · {h.hearing_date || 'No date'}
                </div>
              </div>
              <span className={`badge ${getStatusBadge(h.transcript_status)}`}>
                {h.transcript_status || 'pending'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function DashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [hearings, setHearings] = useState<Hearing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const [statsData, hearingsData] = await Promise.all([
          getAdminStats(),
          getHearings({ limit: 5 }),
        ]);
        setStats(statsData);
        // Handle both array and paginated response formats
        setHearings(Array.isArray(hearingsData) ? hearingsData : hearingsData.items || []);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load data');
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <PageLayout activeTab="overview">
        <div className="loading">
          <div className="spinner" />
        </div>
      </PageLayout>
    );
  }

  if (error) {
    return (
      <PageLayout activeTab="overview">
        <div className="alert alert-danger">
          <AlertCircle size={20} />
          <div>
            <strong>Error loading dashboard</strong>
            <p style={{ marginTop: '0.25rem' }}>{error}</p>
          </div>
        </div>
      </PageLayout>
    );
  }

  if (!stats) return null;

  const statusCounts = stats.hearings_by_status || {};

  return (
    <PageLayout activeTab="overview">
      {/* Stats Grid */}
      <div className="stats-grid">
        <StatCard value={stats.total_hearings} label="Total Hearings" />
        <StatCard value={stats.total_states} label="States" />
        <StatCard value={stats.total_segments || 0} label="Segments" />
        <StatCard value={(stats.total_hours || 0).toFixed(1)} label="Audio Hours" />
      </div>

      {/* Three Column Layout */}
      <div className="grid-3">
        <PipelineStatusCard
          pending={statusCounts['pending'] || 0}
          transcribed={statusCounts['transcribed'] || 0}
          analyzed={statusCounts['analyzed'] || 0}
          failed={statusCounts['failed'] || 0}
        />
        <CostCard
          transcription={stats.total_transcription_cost || 0}
          analysis={stats.total_analysis_cost || 0}
          total={stats.total_cost || 0}
        />
        <div className="card">
          <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Recent Activity</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.9rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--gray-500)' }}>Last 24 hours</span>
              <span style={{ fontWeight: 600 }}>{stats.hearings_last_24h || 0} hearings</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--gray-500)' }}>Last 7 days</span>
              <span style={{ fontWeight: 600 }}>{stats.hearings_last_7d || 0} hearings</span>
            </div>
          </div>
        </div>
      </div>

      {/* Hearings by Status */}
      {Object.keys(statusCounts).length > 0 && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Hearings by Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '1rem' }}>
            {Object.entries(statusCounts).map(([status, count]) => (
              <div key={status} style={{ textAlign: 'center', padding: '1rem', background: 'var(--gray-50)', borderRadius: 'var(--radius)' }}>
                <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>{count}</div>
                <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', textTransform: 'capitalize' }}>{status}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Hearings */}
      <div style={{ marginTop: '1rem' }}>
        <RecentHearingsCard hearings={hearings} />
      </div>

      {/* Hearings by State */}
      {stats.hearings_by_state && Object.keys(stats.hearings_by_state).length > 0 && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Hearings by State</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(60px, 1fr))', gap: '0.75rem' }}>
            {Object.entries(stats.hearings_by_state)
              .sort(([, a], [, b]) => b - a)
              .map(([state, count]) => (
                <div key={state} style={{ textAlign: 'center', padding: '0.75rem', background: 'var(--gray-50)', borderRadius: 'var(--radius)' }}>
                  <div style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--gray-800)' }}>{count}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>{state}</div>
                </div>
              ))}
          </div>
        </div>
      )}
    </PageLayout>
  );
}
