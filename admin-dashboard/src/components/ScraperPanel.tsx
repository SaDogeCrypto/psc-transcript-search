'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ScraperProgress,
  getScraperStatus,
  startScraper,
  stopScraper,
  getStates,
  State,
} from '@/lib/api';

const SCRAPER_TYPES = [
  { value: 'admin_monitor', label: 'AdminMonitor' },
  { value: 'youtube_channel', label: 'YouTube' },
  { value: 'rss_feed', label: 'RSS Feeds' },
];

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  return `${mins}m ${secs}s`;
}

function formatTimestamp(isoString: string | null): string {
  if (!isoString) return '-';
  const date = new Date(isoString);
  return date.toLocaleTimeString();
}

export default function ScraperPanel() {
  const [progress, setProgress] = useState<ScraperProgress | null>(null);
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Config options
  const [selectedTypes, setSelectedTypes] = useState<string[]>([
    'admin_monitor',
    'youtube_channel',
    'rss_feed',
  ]);
  const [selectedState, setSelectedState] = useState<string>('');
  const [dryRun, setDryRun] = useState(false);

  // Fetch scraper status
  const fetchStatus = useCallback(async () => {
    try {
      const status = await getScraperStatus();
      setProgress(status);
      setError(null);
    } catch (err) {
      setError('Failed to fetch scraper status');
      console.error(err);
    }
  }, []);

  // Fetch states for dropdown
  useEffect(() => {
    getStates().then(setStates).catch(console.error);
    fetchStatus();
  }, [fetchStatus]);

  // Poll for status when running
  useEffect(() => {
    if (progress?.status === 'running' || progress?.status === 'stopping') {
      const interval = setInterval(fetchStatus, 2000);
      return () => clearInterval(interval);
    }
  }, [progress?.status, fetchStatus]);

  const handleStart = async () => {
    setLoading(true);
    setError(null);
    try {
      await startScraper({
        scraper_types: selectedTypes.join(','),
        state: selectedState || undefined,
        dry_run: dryRun,
      });
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start scraper');
    } finally {
      setLoading(false);
    }
  };

  const handleStop = async () => {
    setLoading(true);
    try {
      await stopScraper();
      await fetchStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to stop scraper');
    } finally {
      setLoading(false);
    }
  };

  const toggleType = (type: string) => {
    setSelectedTypes((prev) =>
      prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
    );
  };

  const isRunning = progress?.status === 'running' || progress?.status === 'stopping';
  const progressPercent =
    progress?.total_sources > 0
      ? Math.round((progress.sources_completed / progress.total_sources) * 100)
      : 0;

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">Scraper Control</h2>
        <StatusBadge status={progress?.status || 'idle'} />
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* Configuration Section */}
      {!isRunning && (
        <div className="space-y-4 mb-6">
          {/* Scraper Types */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Scraper Types
            </label>
            <div className="flex flex-wrap gap-2">
              {SCRAPER_TYPES.map((type) => (
                <button
                  key={type.value}
                  onClick={() => toggleType(type.value)}
                  className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                    selectedTypes.includes(type.value)
                      ? 'bg-blue-100 text-blue-700 border border-blue-300'
                      : 'bg-gray-100 text-gray-600 border border-gray-200 hover:bg-gray-200'
                  }`}
                >
                  {type.label}
                </button>
              ))}
            </div>
          </div>

          {/* State Filter */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              State Filter (optional)
            </label>
            <select
              value={selectedState}
              onChange={(e) => setSelectedState(e.target.value)}
              className="block w-full max-w-xs rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
            >
              <option value="">All States</option>
              {states.map((state) => (
                <option key={state.code} value={state.code}>
                  {state.code} - {state.name}
                </option>
              ))}
            </select>
          </div>

          {/* Dry Run Toggle */}
          <div className="flex items-center">
            <input
              type="checkbox"
              id="dryRun"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="dryRun" className="ml-2 text-sm text-gray-600">
              Dry run (preview only, no database changes)
            </label>
          </div>
        </div>
      )}

      {/* Progress Section */}
      {isRunning && progress && (
        <div className="mb-6 space-y-4">
          {/* Progress Bar */}
          <div>
            <div className="flex justify-between text-sm text-gray-600 mb-1">
              <span>
                {progress.current_scraper_type?.replace('_', ' ') || 'Starting...'}
              </span>
              <span>
                {progress.sources_completed} / {progress.total_sources} sources
              </span>
            </div>
            <div className="w-full bg-gray-200 rounded-full h-2.5">
              <div
                className="bg-blue-600 h-2.5 rounded-full transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>

          {/* Current Source */}
          {progress.current_source_name && (
            <div className="text-sm text-gray-600">
              <span className="font-medium">Current:</span> {progress.current_source_name}
            </div>
          )}

          {/* Live Stats */}
          <div className="grid grid-cols-3 gap-4">
            <StatBox label="Items Found" value={progress.items_found} />
            <StatBox label="New Hearings" value={progress.new_hearings} color="green" />
            <StatBox label="Existing" value={progress.existing_hearings} color="gray" />
          </div>
        </div>
      )}

      {/* Results Section (when completed) */}
      {progress?.status === 'completed' && progress.scraper_results && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-3">Results</h3>
          <div className="space-y-3">
            {Object.entries(progress.scraper_results).map(([type, results]) => (
              <div
                key={type}
                className="bg-gray-50 rounded-md p-3 text-sm"
              >
                <div className="font-medium text-gray-800 mb-1">
                  {type.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                </div>
                <div className="grid grid-cols-4 gap-2 text-gray-600">
                  <span>Sources: {results.sources_scraped}</span>
                  <span>Items: {results.items_found}</span>
                  <span className="text-green-600">New: {results.new_hearings}</span>
                  <span className="text-gray-500">Errors: {results.errors}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Timing */}
          {progress.started_at && progress.finished_at && (
            <div className="mt-3 text-xs text-gray-500">
              Completed in{' '}
              {formatDuration(
                Math.round(
                  (new Date(progress.finished_at).getTime() -
                    new Date(progress.started_at).getTime()) /
                    1000
                )
              )}
            </div>
          )}
        </div>
      )}

      {/* Errors Section */}
      {progress && progress.error_count > 0 && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-red-700 mb-2">
            Errors ({progress.error_count})
          </h3>
          <div className="max-h-40 overflow-y-auto space-y-2">
            {progress.errors.slice(-5).map((err, idx) => (
              <div
                key={idx}
                className="bg-red-50 border border-red-100 rounded p-2 text-xs"
              >
                <div className="font-medium text-red-800">{err.source}</div>
                <div className="text-red-600 truncate">{err.error}</div>
                <div className="text-red-400 text-[10px]">
                  {formatTimestamp(err.timestamp)}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Action Buttons */}
      <div className="flex gap-3">
        {!isRunning ? (
          <button
            onClick={handleStart}
            disabled={loading || selectedTypes.length === 0}
            className="flex-1 bg-blue-600 text-white px-4 py-2 rounded-md font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? 'Starting...' : 'Start Scraper'}
          </button>
        ) : (
          <button
            onClick={handleStop}
            disabled={loading || progress?.status === 'stopping'}
            className="flex-1 bg-red-600 text-white px-4 py-2 rounded-md font-medium hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {progress?.status === 'stopping' ? 'Stopping...' : 'Stop Scraper'}
          </button>
        )}
        <button
          onClick={fetchStatus}
          disabled={loading}
          className="px-4 py-2 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50 transition-colors"
        >
          Refresh
        </button>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    idle: 'bg-gray-100 text-gray-700',
    running: 'bg-blue-100 text-blue-700 animate-pulse',
    stopping: 'bg-yellow-100 text-yellow-700',
    completed: 'bg-green-100 text-green-700',
    error: 'bg-red-100 text-red-700',
  };

  return (
    <span
      className={`px-2.5 py-1 rounded-full text-xs font-medium ${
        styles[status] || styles.idle
      }`}
    >
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  );
}

function StatBox({
  label,
  value,
  color = 'blue',
}: {
  label: string;
  value: number;
  color?: 'blue' | 'green' | 'gray';
}) {
  const colors = {
    blue: 'text-blue-600',
    green: 'text-green-600',
    gray: 'text-gray-500',
  };

  return (
    <div className="bg-gray-50 rounded-md p-3 text-center">
      <div className={`text-xl font-semibold ${colors[color]}`}>{value}</div>
      <div className="text-xs text-gray-500">{label}</div>
    </div>
  );
}
