'use client';

import { useEffect, useState } from 'react';
import {
  AlertCircle,
  CheckCircle,
  Play,
  RefreshCw,
  Radio,
} from 'lucide-react';
import { PageLayout } from '@/components/Layout';
import { getScrapers, getStates, runScraper, type State, type ScraperRunResult } from '@/lib/api';

function ScraperCard({
  stateCode,
  scrapers,
  onRun,
}: {
  stateCode: string;
  scrapers: string[];
  onRun: (stateCode: string, scraper: string) => void;
}) {
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ScraperRunResult | null>(null);

  const handleRun = async (scraper: string) => {
    setRunning(scraper);
    setLastResult(null);
    try {
      const result = await runScraper(stateCode, scraper);
      setLastResult(result);
      onRun(stateCode, scraper);
    } catch (err) {
      console.error('Failed to run scraper:', err);
    } finally {
      setRunning(null);
    }
  };

  return (
    <div className="card">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{
            width: '40px',
            height: '40px',
            borderRadius: '50%',
            background: '#dbeafe',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Radio size={20} color="#2563eb" />
          </div>
          <div>
            <h4 style={{ fontWeight: 600, color: 'var(--gray-800)' }}>{stateCode}</h4>
            <p style={{ fontSize: '0.85rem', color: 'var(--gray-500)' }}>
              {scrapers.length} scraper{scrapers.length !== 1 ? 's' : ''} available
            </p>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1rem' }}>
        {scrapers.map((scraper) => (
          <div key={scraper} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem', background: 'var(--gray-50)', borderRadius: 'var(--radius)' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 500 }}>{scraper}</span>
            <button
              onClick={() => handleRun(scraper)}
              disabled={running !== null}
              className="btn btn-primary"
              style={{ fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
            >
              {running === scraper ? (
                <>
                  <RefreshCw size={12} className="animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play size={12} />
                  Run
                </>
              )}
            </button>
          </div>
        ))}
      </div>

      {lastResult && (
        <div style={{
          padding: '0.75rem',
          background: lastResult.status === 'completed' ? '#dcfce7' : '#fef2f2',
          borderRadius: 'var(--radius)',
          fontSize: '0.85rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
            {lastResult.status === 'completed' ? (
              <CheckCircle size={16} color="#16a34a" />
            ) : (
              <AlertCircle size={16} color="#dc2626" />
            )}
            <span style={{ fontWeight: 500 }}>
              {lastResult.scraper}: {lastResult.status}
            </span>
          </div>
          {lastResult.items_found !== undefined && (
            <div style={{ color: 'var(--gray-600)' }}>
              Found {lastResult.items_found} items, created {lastResult.hearings_created || 0} hearings
            </div>
          )}
          {lastResult.errors && lastResult.errors.length > 0 && (
            <div style={{ color: '#dc2626', marginTop: '0.5rem' }}>
              {lastResult.errors.join(', ')}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SourcesPage() {
  const [scrapersByState, setScrapersByState] = useState<Record<string, string[]>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadScrapers();
  }, []);

  async function loadScrapers() {
    try {
      setLoading(true);
      const data = await getScrapers();
      setScrapersByState(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load scrapers');
    } finally {
      setLoading(false);
    }
  }

  const handleScraperRun = async (stateCode: string, scraper: string) => {
    // Refresh after scraper completes
    await loadScrapers();
  };

  const totalScrapers = Object.values(scrapersByState).reduce((sum, s) => sum + s.length, 0);

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
            <strong>Error loading scrapers</strong>
            <p style={{ marginTop: '0.25rem' }}>{error}</p>
          </div>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout activeTab="sources">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-800)' }}>Scrapers</h2>
          <p style={{ color: 'var(--gray-500)', marginTop: '0.25rem' }}>
            {Object.keys(scrapersByState).length} states, {totalScrapers} scrapers available
          </p>
        </div>
        <button onClick={loadScrapers} className="btn btn-secondary">
          <RefreshCw size={16} />
          Refresh
        </button>
      </div>

      {Object.keys(scrapersByState).length === 0 ? (
        <div className="empty-state">
          <Radio size={48} color="var(--gray-400)" />
          <h3 style={{ marginTop: '1rem', fontWeight: 600, color: 'var(--gray-700)' }}>No scrapers configured</h3>
          <p className="hint">
            Configure scrapers in the state registry to start discovering hearings.
          </p>
        </div>
      ) : (
        <div className="grid-2">
          {Object.entries(scrapersByState)
            .sort(([a], [b]) => a.localeCompare(b))
            .map(([stateCode, scrapers]) => (
              <ScraperCard
                key={stateCode}
                stateCode={stateCode}
                scrapers={scrapers}
                onRun={handleScraperRun}
              />
            ))}
        </div>
      )}
    </PageLayout>
  );
}
