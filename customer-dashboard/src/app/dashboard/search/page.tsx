'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import {
  Search,
  Filter,
  Calendar,
  FileText,
  X,
  ExternalLink,
} from 'lucide-react'
import { search, getStates, type SearchResult, type State } from '@/lib/api'
import { formatDate } from '@/lib/utils'

const PAGE_SIZE = 20

export default function SearchPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [results, setResults] = useState<SearchResult[]>([])
  const [states, setStates] = useState<State[]>([])
  const [loading, setLoading] = useState(false)
  const [totalCount, setTotalCount] = useState(0)
  const [showFilters, setShowFilters] = useState(false)

  // Search params
  const query = searchParams.get('q') || ''
  const selectedState = searchParams.get('state_code') || ''
  const docketNumber = searchParams.get('docket_number') || ''
  const dateFrom = searchParams.get('date_from') || ''
  const dateTo = searchParams.get('date_to') || ''
  const page = parseInt(searchParams.get('page') || '1')

  const [searchInput, setSearchInput] = useState(query)

  const updateParams = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString())
      Object.entries(updates).forEach(([key, value]) => {
        if (value) {
          params.set(key, value)
        } else {
          params.delete(key)
        }
      })
      if (!updates.page) {
        params.delete('page')
      }
      router.push(`/dashboard/search?${params.toString()}`)
    },
    [searchParams, router]
  )

  useEffect(() => {
    getStates().then(setStates).catch(console.error)
  }, [])

  useEffect(() => {
    if (!query) {
      setResults([])
      return
    }

    async function doSearch() {
      setLoading(true)
      try {
        const offset = (page - 1) * PAGE_SIZE
        const data = await search({
          query,
          state_code: selectedState || undefined,
          docket_number: docketNumber || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          limit: PAGE_SIZE,
          offset,
        })
        setResults(data.results)
        setTotalCount(data.total)
      } catch (error) {
        console.error('Search error:', error)
      } finally {
        setLoading(false)
      }
    }

    doSearch()
  }, [query, selectedState, docketNumber, dateFrom, dateTo, page])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    if (searchInput.trim()) {
      updateParams({ q: searchInput.trim() })
    }
  }

  const selectState = (code: string) => {
    updateParams({ state_code: code || null })
  }

  const clearFilters = () => {
    router.push(`/dashboard/search?q=${encodeURIComponent(query)}`)
  }

  const hasActiveFilters = selectedState || docketNumber || dateFrom || dateTo
  const totalPages = Math.ceil(totalCount / PAGE_SIZE)

  return (
    <div className="space-y-6">
      {/* Header with search */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900 mb-4">Search Transcripts</h1>

        <form onSubmit={handleSearch} className="flex gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
            <input
              type="text"
              placeholder="Search across all hearing transcripts..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              className="w-full pl-12 pr-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-lg"
            />
          </div>
          <button
            type="submit"
            className="px-6 py-3 bg-blue-600 text-white rounded-xl font-semibold hover:bg-blue-700 transition-colors"
          >
            Search
          </button>
          <button
            type="button"
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-3 border rounded-xl transition-colors ${
              showFilters || hasActiveFilters
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <Filter className="h-5 w-5" />
          </button>
        </form>
      </div>

      {/* Filters Panel */}
      {showFilters && (
        <div className="bg-white rounded-xl border border-gray-200 p-4 sm:p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="font-medium text-gray-900">Filters</h3>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-sm text-gray-500 hover:text-gray-700"
              >
                Clear all
              </button>
            )}
          </div>

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {/* States */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Filter by State
              </label>
              <div className="flex flex-wrap gap-2">
                {states.map((state) => (
                  <button
                    key={state.code}
                    onClick={() => selectState(selectedState === state.code ? '' : state.code)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      selectedState === state.code
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {state.code}
                  </button>
                ))}
              </div>
            </div>

            {/* Docket Number */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Docket Number
              </label>
              <input
                type="text"
                value={docketNumber}
                placeholder="e.g. 2024-0001-EI"
                onChange={(e) => updateParams({ docket_number: e.target.value || null })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>

            {/* Date Range */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Date From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => updateParams({ date_from: e.target.value || null })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Date To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => updateParams({ date_to: e.target.value || null })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              />
            </div>
          </div>
        </div>
      )}

      {/* Active filters badges */}
      {hasActiveFilters && !showFilters && (
        <div className="flex flex-wrap gap-2">
          {selectedState && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm">
              {selectedState}
              <button onClick={() => selectState('')}>
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
          {docketNumber && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              Docket: {docketNumber}
              <button onClick={() => updateParams({ docket_number: null })}>
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
          {dateFrom && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              From: {dateFrom}
              <button onClick={() => updateParams({ date_from: null })}>
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
          {dateTo && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              To: {dateTo}
              <button onClick={() => updateParams({ date_to: null })}>
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>
      )}

      {/* Results */}
      {!query ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <Search className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">Search transcripts</h3>
          <p className="text-gray-500 max-w-md mx-auto">
            Enter a search term to find mentions across all hearing transcripts.
            Try searching for utility names, rate cases, or specific topics.
          </p>
        </div>
      ) : loading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="bg-white rounded-xl border border-gray-200 p-4 animate-pulse">
              <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
              <div className="h-3 bg-gray-200 rounded w-1/4 mb-4" />
              <div className="h-20 bg-gray-200 rounded" />
            </div>
          ))}
        </div>
      ) : results.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No results found</h3>
          <p className="text-gray-500">
            No transcripts match "{query}". Try different keywords or adjust filters.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {/* Results count */}
          <p className="text-sm text-gray-500">
            Found {totalCount} result{totalCount !== 1 ? 's' : ''} for "{query}"
          </p>

          {/* Result cards */}
          {results.map((result, index) => (
            <SearchResultCard key={`${result.hearing_id}-${index}`} result={result} query={query} />
          ))}

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex justify-center gap-4">
              <button
                onClick={() => updateParams({ page: String(page - 1) })}
                disabled={page === 1}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Previous
              </button>
              <span className="px-4 py-2 text-gray-500">
                Page {page} of {totalPages}
              </span>
              <button
                onClick={() => updateParams({ page: String(page + 1) })}
                disabled={page >= totalPages}
                className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50"
              >
                Next
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function SearchResultCard({ result, query }: { result: SearchResult; query: string }) {
  // Highlight matching text
  const highlightText = (text: string) => {
    if (!query) return text

    const regex = new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi')
    const parts = text.split(regex)

    return parts.map((part, i) =>
      regex.test(part) ? (
        <mark key={i} className="bg-yellow-200 text-yellow-900 rounded px-0.5">
          {part}
        </mark>
      ) : (
        part
      )
    )
  }

  return (
    <Link
      href={`/dashboard/hearings/${result.hearing_id}`}
      className="block bg-white rounded-xl border border-gray-200 p-4 hover:border-blue-200 hover:shadow-md transition-all"
    >
      <div className="flex items-start gap-4">
        <div className="h-12 w-12 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0">
          <span className="text-sm font-bold text-white">{result.state_code}</span>
        </div>

        <div className="flex-1 min-w-0">
          {/* Hearing title */}
          <h3 className="font-medium text-gray-900 line-clamp-1">
            {result.hearing_title || 'Untitled Hearing'}
          </h3>

          {/* Meta info */}
          <div className="flex flex-wrap items-center gap-3 mt-1 text-sm text-gray-500">
            <span className="flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5" />
              {formatDate(result.hearing_date)}
            </span>
            {result.docket_number && (
              <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                {result.docket_number}
              </span>
            )}
            {result.hearing_type && (
              <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                {result.hearing_type}
              </span>
            )}
          </div>

          {/* Snippet */}
          <div className="mt-3 p-3 bg-gray-50 rounded-lg">
            <p className="text-sm text-gray-700 line-clamp-3">
              {result.snippet ? highlightText(result.snippet) : highlightText(result.text)}
            </p>
          </div>
        </div>

        <div className="flex-shrink-0">
          <div className="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
            <ExternalLink className="h-4 w-4 text-blue-600" />
          </div>
        </div>
      </div>
    </Link>
  )
}
