'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
  DollarSign,
  FileAudio,
  Radio,
} from 'lucide-react';
import { PageLayout } from './components/Layout';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

interface AdminStats {
  total_states: number;
  total_sources: number;
  total_hearings: number;
  total_hours: number;
  hearings_by_status: Record<string, number>;
  hearings_by_state: Record<string, number>;
  total_cost: number;
  sources_healthy: number;
  sources_error: number;
  pipeline_jobs_pending: number;
  pipeline_jobs_running: number;
  pipeline_jobs_error: number;
  cost_today: number;
  cost_this_week: number;
  cost_this_month: number;
}

async function getAdminStats(): Promise<AdminStats> {
  const res = await fetch(`${API_URL}/admin/stats`);
  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

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
  running,
  error,
}: {
  pending: number;
  running: number;
  error: number;
}) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Pipeline Status</h3>
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
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Running</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600 }}>{running}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertCircle size={18} color="#dc2626" />
            <span style={{ color: 'var(--gray-600)', fontSize: '0.9rem' }}>Errors</span>
          </div>
          <span style={{ fontSize: '1.25rem', fontWeight: 600, color: error > 0 ? '#dc2626' : 'inherit' }}>{error}</span>
        </div>
      </div>
    </div>
  );
}

function CostCard({
  today,
  week,
  month,
  total,
}: {
  today: number;
  week: number;
  month: number;
  total: number;
}) {
  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Cost Breakdown</h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', fontSize: '0.9rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--gray-500)' }}>Today</span>
          <span style={{ fontWeight: 600 }}>${today.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--gray-500)' }}>This Week</span>
          <span style={{ fontWeight: 600 }}>${week.toFixed(2)}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ color: 'var(--gray-500)' }}>This Month</span>
          <span style={{ fontWeight: 600 }}>${month.toFixed(2)}</span>
        </div>
        <div style={{ borderTop: '1px solid var(--gray-200)', paddingTop: '0.5rem', marginTop: '0.25rem', display: 'flex', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 600 }}>Total</span>
          <span style={{ fontWeight: 700, fontSize: '1.1rem' }}>${total.toFixed(2)}</span>
        </div>
      </div>
    </div>
  );
}

function SourceHealthCard({ healthy, error }: { healthy: number; error: number }) {
  const total = healthy + error;
  const healthyPercent = total > 0 ? (healthy / total) * 100 : 100;

  return (
    <div className="card">
      <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Source Health</h3>
      <div style={{ marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
          <span style={{ color: '#065f46', fontWeight: 600 }}>{healthy} Healthy</span>
          <span style={{ color: '#991b1b', fontWeight: 600 }}>{error} Errors</span>
        </div>
        <div className="progress-bar">
          <div className="progress-bar-fill success" style={{ width: `${healthyPercent}%` }} />
        </div>
      </div>
      <p style={{ textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.85rem' }}>
        {healthyPercent.toFixed(0)}% sources operational
      </p>
    </div>
  );
}

export default function AdminDashboardPage() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadData() {
      try {
        const statsData = await getAdminStats();
        setStats(statsData);
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

  return (
    <PageLayout activeTab="overview">
      {/* Stats Grid */}
      <div className="stats-grid">
        <StatCard value={stats.total_hearings} label="Total Hearings" />
        <StatCard value={stats.total_states} label="States" />
        <StatCard value={stats.total_sources} label="Sources" />
        <StatCard value={stats.total_hours.toFixed(1)} label="Audio Hours" />
      </div>

      {/* Three Column Layout */}
      <div className="grid-3">
        <PipelineStatusCard
          pending={stats.pipeline_jobs_pending}
          running={stats.pipeline_jobs_running}
          error={stats.pipeline_jobs_error}
        />
        <CostCard
          today={stats.cost_today}
          week={stats.cost_this_week}
          month={stats.cost_this_month}
          total={stats.total_cost}
        />
        <SourceHealthCard
          healthy={stats.sources_healthy}
          error={stats.sources_error}
        />
      </div>

      {/* Hearings by Status - ordered by pipeline progression */}
      {Object.keys(stats.hearings_by_status).length > 0 && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Hearings by Status</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '1rem' }}>
            {(() => {
              const pipelineOrder = [
                'discovered', 'downloading', 'downloaded',
                'transcribing', 'transcribed',
                'analyzing', 'analyzed',
                'extracting', 'extracted',
                'complete', 'error', 'failed', 'skipped'
              ];
              return Object.entries(stats.hearings_by_status)
                .sort(([a], [b]) => {
                  const aIdx = pipelineOrder.indexOf(a);
                  const bIdx = pipelineOrder.indexOf(b);
                  return (aIdx === -1 ? 999 : aIdx) - (bIdx === -1 ? 999 : bIdx);
                })
                .map(([status, count]) => (
                  <div key={status} style={{ textAlign: 'center', padding: '1rem', background: 'var(--gray-50)', borderRadius: 'var(--radius)' }}>
                    <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>{count}</div>
                    <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)', textTransform: 'capitalize' }}>{status}</div>
                  </div>
                ));
            })()}
          </div>
        </div>
      )}

      {/* Hearings by State */}
      {Object.keys(stats.hearings_by_state).length > 0 && (
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
