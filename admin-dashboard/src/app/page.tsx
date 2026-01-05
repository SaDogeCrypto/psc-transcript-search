'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  AlertCircle,
  CheckCircle,
  Clock,
  DollarSign,
  Download,
  FileAudio,
  History,
  Mic,
  Radio,
  RefreshCw,
  Sparkles,
} from 'lucide-react';
import { getAdminStats, getHearings, AdminStats, Hearing } from '@/lib/api';

function Header() {
  return (
    <header className="header">
      <div className="header-content">
        <div className="logo-title">
          <div>
            <h1>PSC Admin</h1>
            <p className="subtitle">Pipeline Monitor Dashboard</p>
          </div>
        </div>
      </div>
    </header>
  );
}

function Tabs({ active }: { active: string }) {
  const tabs = [
    { id: 'overview', label: 'Overview', href: '/' },
    { id: 'sources', label: 'Sources', href: '/sources' },
    { id: 'hearings', label: 'Hearings', href: '/hearings' },
    { id: 'runs', label: 'Pipeline Runs', href: '/runs' },
  ];

  return (
    <div className="tabs-container">
      <div className="tabs">
        {tabs.map((tab) => (
          <Link
            key={tab.id}
            href={tab.href}
            className={`tab ${active === tab.id ? 'active' : ''}`}
          >
            {tab.label}
          </Link>
        ))}
      </div>
    </div>
  );
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
          <div
            className="progress-bar-fill success"
            style={{ width: `${healthyPercent}%` }}
          />
        </div>
      </div>
      <p style={{ textAlign: 'center', color: 'var(--gray-500)', fontSize: '0.85rem' }}>
        {healthyPercent.toFixed(0)}% sources operational
      </p>
    </div>
  );
}

function RecentHearingsCard({ hearings }: { hearings: Hearing[] }) {
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

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
        <h3 style={{ color: 'var(--gray-700)' }}>Recent Hearings</h3>
        <Link href="/hearings" style={{ color: 'var(--primary)', fontSize: '0.85rem', textDecoration: 'none' }}>
          View all →
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
                  {h.title}
                </div>
                <div style={{ fontSize: '0.8rem', color: 'var(--gray-500)' }}>
                  {h.state_code} · {h.hearing_date || 'No date'}
                </div>
              </div>
              <span className={`badge ${getStatusBadge(h.pipeline_status)}`}>
                {h.pipeline_status}
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
          getHearings({ page_size: 5 }),
        ]);
        setStats(statsData);
        setHearings(hearingsData);
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
      <>
        <Header />
        <main className="main-content">
          <Tabs active="overview" />
          <div className="loading">
            <div className="spinner" />
          </div>
        </main>
      </>
    );
  }

  if (error) {
    return (
      <>
        <Header />
        <main className="main-content">
          <Tabs active="overview" />
          <div className="alert alert-danger">
            <AlertCircle size={20} />
            <div>
              <strong>Error loading dashboard</strong>
              <p style={{ marginTop: '0.25rem' }}>{error}</p>
            </div>
          </div>
        </main>
      </>
    );
  }

  if (!stats) return null;

  return (
    <>
      <Header />
      <main className="main-content">
        <Tabs active="overview" />

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

        {/* Hearings by Status */}
        {Object.keys(stats.hearings_by_status).length > 0 && (
          <div className="card" style={{ marginTop: '1rem' }}>
            <h3 style={{ marginBottom: '1rem', color: 'var(--gray-700)' }}>Hearings by Status</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(100px, 1fr))', gap: '1rem' }}>
              {Object.entries(stats.hearings_by_status).map(([status, count]) => (
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
      </main>
    </>
  );
}
