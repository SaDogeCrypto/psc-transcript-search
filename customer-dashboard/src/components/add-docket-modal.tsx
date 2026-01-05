'use client'

import { useState, useEffect } from 'react'
import { X, Search, Plus, Loader2, Building2 } from 'lucide-react'

interface Docket {
  id: number
  normalized_id: string
  docket_number: string
  state_code?: string
  state_name?: string
  docket_type?: string
  company?: string
  status?: string
  mention_count: number
}

interface AddDocketModalProps {
  isOpen: boolean
  onClose: () => void
  onAdd: (docketId: number) => Promise<void>
  watchedDocketIds: number[]
  apiUrl: string
}

export function AddDocketModal({ isOpen, onClose, onAdd, watchedDocketIds, apiUrl }: AddDocketModalProps) {
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<Docket[]>([])
  const [recentDockets, setRecentDockets] = useState<Docket[]>([])
  const [isSearching, setIsSearching] = useState(false)
  const [addingId, setAddingId] = useState<number | null>(null)

  // Load recent/popular dockets on mount
  useEffect(() => {
    if (isOpen) {
      fetch(`${apiUrl}/api/dockets?page_size=10&sort_by=mention_count&sort_order=desc`)
        .then(res => res.json())
        .then(data => setRecentDockets(data))
        .catch(console.error)
    }
  }, [isOpen, apiUrl])

  // Search dockets
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([])
      return
    }

    const timer = setTimeout(async () => {
      setIsSearching(true)
      try {
        const res = await fetch(`${apiUrl}/api/dockets/search?q=${encodeURIComponent(searchQuery)}`)
        const data = await res.json()
        setSearchResults(data.results || [])
      } catch (error) {
        console.error('Search failed:', error)
      } finally {
        setIsSearching(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchQuery, apiUrl])

  const handleAdd = async (docketId: number) => {
    setAddingId(docketId)
    try {
      await onAdd(docketId)
    } finally {
      setAddingId(null)
    }
  }

  if (!isOpen) return null

  const displayDockets = searchQuery.trim() ? searchResults : recentDockets
  const title = searchQuery.trim() ? 'Search Results' : 'Popular Dockets'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[80vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Add Docket to Watchlist</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 rounded"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Search input */}
        <div className="p-4 border-b">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              placeholder="Search by docket number, company, or keyword..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
              autoFocus
            />
            {isSearching && (
              <Loader2 className="absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 animate-spin" />
            )}
          </div>
        </div>

        {/* Results */}
        <div className="flex-1 overflow-y-auto p-4">
          <h3 className="text-sm font-medium text-gray-500 mb-3">{title}</h3>

          {displayDockets.length === 0 ? (
            <p className="text-sm text-gray-500 text-center py-8">
              {searchQuery.trim() ? 'No dockets found' : 'No dockets available'}
            </p>
          ) : (
            <div className="space-y-2">
              {displayDockets.map((docket) => {
                const isWatched = watchedDocketIds.includes(docket.id)
                const isAdding = addingId === docket.id

                return (
                  <div
                    key={docket.id}
                    className="flex items-center justify-between p-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-sm font-medium text-gray-900">
                          {docket.normalized_id}
                        </span>
                        {docket.docket_type && (
                          <span className="text-xs bg-white text-gray-600 px-1.5 py-0.5 rounded border">
                            {docket.docket_type}
                          </span>
                        )}
                      </div>
                      {docket.company && (
                        <div className="flex items-center gap-1 text-xs text-gray-500 mt-1">
                          <Building2 className="w-3 h-3" />
                          <span className="truncate">{docket.company}</span>
                        </div>
                      )}
                    </div>

                    <button
                      onClick={() => handleAdd(docket.id)}
                      disabled={isWatched || isAdding}
                      className={`ml-3 px-3 py-1.5 text-sm font-medium rounded-md transition-colors flex items-center gap-1.5 ${
                        isWatched
                          ? 'bg-gray-200 text-gray-500 cursor-not-allowed'
                          : 'bg-blue-600 text-white hover:bg-blue-700'
                      }`}
                    >
                      {isAdding ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : isWatched ? (
                        'Watching'
                      ) : (
                        <>
                          <Plus className="w-4 h-4" />
                          Add
                        </>
                      )}
                    </button>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
