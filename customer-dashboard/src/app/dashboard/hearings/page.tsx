'use client'

import { useState, useEffect, useCallback } from 'react'
import Link from 'next/link'
import { useSearchParams, useRouter } from 'next/navigation'
import {
  Search,
  Filter,
  Calendar,
  Clock,
  Play,
  ChevronLeft,
  ChevronRight,
  X,
  FileText,
} from 'lucide-react'
import { getHearings, getStates, type HearingListItem, type State } from '@/lib/api'
import { formatDate, formatDuration } from '@/lib/utils'

export default function HearingsPage() {
  const router = useRouter()
  const searchParams = useSearchParams()

  const [hearings, setHearings] = useState<HearingListItem[]>([])
  const [states, setStates] = useState<State[]>([])
  const [loading, setLoading] = useState(true)
  const [showFilters, setShowFilters] = useState(false)

  // Filters from URL
  const selectedStates = searchParams.get('states')?.split(',').filter(Boolean) || []
  const dateFrom = searchParams.get('date_from') || ''
  const dateTo = searchParams.get('date_to') || ''
  const searchQuery = searchParams.get('q') || ''
  const page = parseInt(searchParams.get('page') || '1')

  const updateFilters = useCallback(
    (updates: Record<string, string | null>) => {
      const params = new URLSearchParams(searchParams.toString())
      Object.entries(updates).forEach(([key, value]) => {
        if (value) {
          params.set(key, value)
        } else {
          params.delete(key)
        }
      })
      // Reset to page 1 when filters change
      if (!updates.page) {
        params.delete('page')
      }
      router.push(`/dashboard/hearings?${params.toString()}`)
    },
    [searchParams, router]
  )

  useEffect(() => {
    getStates().then(setStates).catch(console.error)
  }, [])

  useEffect(() => {
    async function loadHearings() {
      setLoading(true)
      try {
        const data = await getHearings({
          states: selectedStates.join(',') || undefined,
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined,
          search_query: searchQuery || undefined,
          page,
          page_size: 20,
          sort_by: 'hearing_date',
          sort_order: 'desc',
        })
        setHearings(data)
      } catch (error) {
        console.error('Error loading hearings:', error)
      } finally {
        setLoading(false)
      }
    }
    loadHearings()
  }, [selectedStates.join(','), dateFrom, dateTo, searchQuery, page])

  const toggleState = (code: string) => {
    const newStates = selectedStates.includes(code)
      ? selectedStates.filter((s) => s !== code)
      : [...selectedStates, code]
    updateFilters({ states: newStates.join(',') || null })
  }

  const clearFilters = () => {
    router.push('/dashboard/hearings')
  }

  const hasActiveFilters = selectedStates.length > 0 || dateFrom || dateTo || searchQuery

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Hearings</h1>
          <p className="text-gray-500 mt-1">Browse all PSC hearings and transcripts</p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative flex-1 sm:w-64">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search hearings..."
              value={searchQuery}
              onChange={(e) => updateFilters({ q: e.target.value || null })}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`flex items-center gap-2 px-4 py-2 border rounded-lg transition-colors ${
              showFilters || hasActiveFilters
                ? 'border-blue-600 bg-blue-50 text-blue-700'
                : 'border-gray-300 text-gray-700 hover:bg-gray-50'
            }`}
          >
            <Filter className="h-4 w-4" />
            Filters
            {hasActiveFilters && (
              <span className="h-5 w-5 bg-blue-600 text-white text-xs rounded-full flex items-center justify-center">
                {selectedStates.length + (dateFrom ? 1 : 0) + (dateTo ? 1 : 0)}
              </span>
            )}
          </button>
        </div>
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

          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            {/* States */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                States
              </label>
              <div className="flex flex-wrap gap-2">
                {states.map((state) => (
                  <button
                    key={state.code}
                    onClick={() => toggleState(state.code)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      selectedStates.includes(state.code)
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                    }`}
                  >
                    {state.code}
                  </button>
                ))}
              </div>
            </div>

            {/* Date Range */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Date From
              </label>
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => updateFilters({ date_from: e.target.value || null })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Date To
              </label>
              <input
                type="date"
                value={dateTo}
                onChange={(e) => updateFilters({ date_to: e.target.value || null })}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-sm"
              />
            </div>
          </div>
        </div>
      )}

      {/* Active Filters */}
      {hasActiveFilters && !showFilters && (
        <div className="flex flex-wrap gap-2">
          {selectedStates.map((state) => (
            <span
              key={state}
              className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm"
            >
              {state}
              <button
                onClick={() => toggleState(state)}
                className="hover:text-blue-900"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
          {dateFrom && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              From: {dateFrom}
              <button
                onClick={() => updateFilters({ date_from: null })}
                className="hover:text-gray-900"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
          {dateTo && (
            <span className="inline-flex items-center gap-1 px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm">
              To: {dateTo}
              <button
                onClick={() => updateFilters({ date_to: null })}
                className="hover:text-gray-900"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          )}
        </div>
      )}

      {/* Hearings List */}
      {loading ? (
        <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="p-4 animate-pulse">
              <div className="flex items-center gap-4">
                <div className="h-12 w-12 bg-gray-200 rounded-lg" />
                <div className="flex-1">
                  <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
                  <div className="h-3 bg-gray-200 rounded w-1/2" />
                </div>
              </div>
            </div>
          ))}
        </div>
      ) : hearings.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
          <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 mb-2">No hearings found</h3>
          <p className="text-gray-500">
            {hasActiveFilters
              ? 'Try adjusting your filters to see more results.'
              : 'No hearings are available at this time.'}
          </p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 divide-y divide-gray-100">
          {hearings.map((hearing) => (
            <HearingCard key={hearing.id} hearing={hearing} />
          ))}
        </div>
      )}

      {/* Pagination */}
      {hearings.length > 0 && (
        <div className="flex items-center justify-between">
          <button
            onClick={() => updateFilters({ page: String(page - 1) })}
            disabled={page === 1}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <ChevronLeft className="h-4 w-4" />
            Previous
          </button>
          <span className="text-sm text-gray-500">Page {page}</span>
          <button
            onClick={() => updateFilters({ page: String(page + 1) })}
            disabled={hearings.length < 20}
            className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Next
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      )}
    </div>
  )
}

function HearingCard({ hearing }: { hearing: HearingListItem }) {
  return (
    <Link
      href={`/dashboard/hearings/${hearing.id}`}
      className="flex items-center gap-4 p-4 hover:bg-gray-50 transition-colors"
    >
      <div className="h-14 w-14 rounded-xl bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0">
        <span className="text-lg font-bold text-white">{hearing.state_code}</span>
      </div>

      <div className="flex-1 min-w-0">
        <h3 className="font-medium text-gray-900 line-clamp-1">{hearing.title}</h3>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1.5 text-sm text-gray-500">
          <span className="flex items-center gap-1">
            <Calendar className="h-3.5 w-3.5" />
            {formatDate(hearing.hearing_date)}
          </span>
          {hearing.duration_seconds && (
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {formatDuration(hearing.duration_seconds)}
            </span>
          )}
          {hearing.hearing_type && (
            <span className="px-2 py-0.5 bg-gray-100 rounded text-xs font-medium">
              {hearing.hearing_type}
            </span>
          )}
          {hearing.utility_name && (
            <span className="text-gray-400">{hearing.utility_name}</span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 flex-shrink-0">
        {hearing.pipeline_status === 'complete' ? (
          <span className="hidden sm:inline-flex px-2.5 py-1 bg-green-100 text-green-700 text-xs font-medium rounded-full">
            Analyzed
          </span>
        ) : (
          <span className="hidden sm:inline-flex px-2.5 py-1 bg-gray-100 text-gray-600 text-xs font-medium rounded-full">
            {hearing.pipeline_status}
          </span>
        )}
        <div className="h-10 w-10 rounded-full bg-gray-100 flex items-center justify-center group-hover:bg-blue-100 transition-colors">
          <Play className="h-4 w-4 text-gray-500" />
        </div>
      </div>
    </Link>
  )
}
