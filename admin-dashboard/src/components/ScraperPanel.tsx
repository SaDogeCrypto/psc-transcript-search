'use client';

import { useState, useEffect } from 'react';
import { RefreshCw, Play, CheckCircle, AlertCircle } from 'lucide-react';
import { getScrapers, runScraper, getStates, type State, type ScraperRunResult } from '@/lib/api';

export default function ScraperPanel() {
  const [scrapersByState, setScrapersByState] = useState<Record<string, string[]>>({});
  const [states, setStates] = useState<State[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<ScraperRunResult | null>(null);

  // Selected options
  const [selectedState, setSelectedState] = useState<string>('');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    try {
      setLoading(true);
      const [scrapersData, statesData] = await Promise.all([
        getScrapers(),
        getStates(),
      ]);
      setScrapersByState(scrapersData);
      setStates(statesData);
      setError(null);
    } catch (err) {
      setError('Failed to load scraper data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }

  async function handleRunScraper(stateCode: string, scraper: string) {
    setRunning(`${stateCode}-${scraper}`);
    setLastResult(null);
    try {
      const result = await runScraper(stateCode, scraper);
      setLastResult(result);
    } catch (err) {
      console.error('Failed to run scraper:', err);
    } finally {
      setRunning(null);
    }
  }

  const availableScrapers = selectedState
    ? scrapersByState[selectedState] || []
    : Object.entries(scrapersByState).flatMap(([state, scrapers]) =>
        scrapers.map(s => ({ state, scraper: s }))
      );

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-center py-8">
          <RefreshCw className="animate-spin h-6 w-6 text-gray-400" />
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900">Quick Scraper Run</h2>
        <button
          onClick={loadData}
          className="p-2 text-gray-500 hover:text-gray-700 transition-colors"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-sm">
          {error}
        </div>
      )}

      {/* State selector */}
      <div className="mb-4">
        <label className="block text-sm font-medium text-gray-700 mb-2">
          Filter by State
        </label>
        <select
          value={selectedState}
          onChange={(e) => setSelectedState(e.target.value)}
          className="block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm"
        >
          <option value="">All States</option>
          {Object.keys(scrapersByState).sort().map((state) => (
            <option key={state} value={state}>
              {state} ({scrapersByState[state].length} scrapers)
            </option>
          ))}
        </select>
      </div>

      {/* Scrapers list */}
      <div className="space-y-2 mb-4 max-h-60 overflow-y-auto">
        {selectedState ? (
          (scrapersByState[selectedState] || []).map((scraper) => (
            <div
              key={scraper}
              className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
            >
              <div>
                <span className="font-medium text-sm">{selectedState}</span>
                <span className="text-gray-400 mx-2">/</span>
                <span className="text-sm text-gray-600">{scraper}</span>
              </div>
              <button
                onClick={() => handleRunScraper(selectedState, scraper)}
                disabled={running !== null}
                className="px-3 py-1 bg-blue-600 text-white text-sm rounded hover:bg-blue-700 disabled:opacity-50 flex items-center gap-1"
              >
                {running === `${selectedState}-${scraper}` ? (
                  <RefreshCw className="h-3 w-3 animate-spin" />
                ) : (
                  <Play className="h-3 w-3" />
                )}
                Run
              </button>
            </div>
          ))
        ) : (
          <p className="text-sm text-gray-500 text-center py-4">
            Select a state to see available scrapers
          </p>
        )}
      </div>

      {/* Last result */}
      {lastResult && (
        <div className={`p-3 rounded-lg ${lastResult.status === 'completed' ? 'bg-green-50' : 'bg-red-50'}`}>
          <div className="flex items-center gap-2 mb-1">
            {lastResult.status === 'completed' ? (
              <CheckCircle className="h-4 w-4 text-green-600" />
            ) : (
              <AlertCircle className="h-4 w-4 text-red-600" />
            )}
            <span className="font-medium text-sm">
              {lastResult.state_code} / {lastResult.scraper}: {lastResult.status}
            </span>
          </div>
          {lastResult.items_found !== undefined && (
            <p className="text-sm text-gray-600">
              Found {lastResult.items_found} items, created {lastResult.hearings_created || 0} hearings
            </p>
          )}
          {lastResult.errors && lastResult.errors.length > 0 && (
            <p className="text-sm text-red-600 mt-1">
              {lastResult.errors.join(', ')}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
