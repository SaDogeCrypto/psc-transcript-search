'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Eye,
  EyeOff,
  Share2,
  Building2,
  Calendar,
  MapPin,
  Clock,
  Play,
  FileText,
  Loader2,
} from 'lucide-react'
import {
  getDocketByNormalizedId,
  addToWatchlist,
  removeFromWatchlist,
  getWatchlist,
  type DocketWithTimeline,
} from '@/lib/api'

function getStatusBadge(status?: string) {
  switch (status?.toLowerCase()) {
    case 'open':
    case 'under_review':
    case 'active':
      return { color: 'bg-red-100 text-red-700', label: 'Active' }
    case 'pending':
    case 'pending_decision':
      return { color: 'bg-yellow-100 text-yellow-700', label: 'Pending Decision' }
    case 'closed':
    case 'decided':
      return { color: 'bg-green-100 text-green-700', label: 'Closed' }
    default:
      return { color: 'bg-gray-100 text-gray-700', label: status || 'Unknown' }
  }
}

function formatDocketType(type?: string): string {
  if (!type) return 'Unknown'
  return type
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export default function DocketDetailPage() {
  const params = useParams()
  const router = useRouter()
  const normalizedId = params.id as string

  const [docket, setDocket] = useState<DocketWithTimeline | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isWatched, setIsWatched] = useState(false)
  const [watchLoading, setWatchLoading] = useState(false)

  useEffect(() => {
    async function loadDocket() {
      try {
        const [docketData, watchlistData] = await Promise.all([
          getDocketByNormalizedId(normalizedId),
          getWatchlist(),
        ])
        setDocket(docketData)
        setIsWatched(watchlistData.dockets.some((d) => d.normalized_id === normalizedId.toUpperCase()))
      } catch (err) {
        console.error('Error loading docket:', err)
        setError('Docket not found')
      } finally {
        setLoading(false)
      }
    }
    loadDocket()
  }, [normalizedId])

  const handleToggleWatch = async () => {
    if (!docket) return
    setWatchLoading(true)
    try {
      if (isWatched) {
        await removeFromWatchlist(docket.id)
        setIsWatched(false)
      } else {
        await addToWatchlist(docket.id)
        setIsWatched(true)
      }
    } catch (err) {
      console.error('Error toggling watch:', err)
    } finally {
      setWatchLoading(false)
    }
  }

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
    // Could add a toast notification here
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-32" />
        <div className="h-12 bg-gray-200 rounded w-3/4" />
        <div className="h-40 bg-gray-200 rounded-lg" />
        <div className="h-96 bg-gray-200 rounded-lg" />
      </div>
    )
  }

  if (error || !docket) {
    return (
      <div className="text-center py-12">
        <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
        <h2 className="text-lg font-medium text-gray-900 mb-2">Docket not found</h2>
        <p className="text-gray-500 mb-4">The docket "{normalizedId}" could not be found.</p>
        <button
          onClick={() => router.back()}
          className="text-blue-600 hover:text-blue-700 font-medium"
        >
          ← Go back
        </button>
      </div>
    )
  }

  const statusBadge = getStatusBadge(docket.status)

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => router.back()}
          className="flex items-center gap-2 text-gray-600 hover:text-gray-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={handleToggleWatch}
            disabled={watchLoading}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
              isWatched
                ? 'bg-blue-100 text-blue-700 hover:bg-blue-200'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            {watchLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : isWatched ? (
              <Eye className="w-4 h-4" />
            ) : (
              <EyeOff className="w-4 h-4" />
            )}
            {isWatched ? 'Watching' : 'Watch'}
          </button>
          <button
            onClick={handleShare}
            className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
          >
            <Share2 className="w-4 h-4" />
            Share
          </button>
        </div>
      </div>

      {/* Docket Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 font-mono mb-2">
              {docket.normalized_id}
            </h1>
            {docket.company && (
              <h2 className="text-lg text-gray-700">{docket.company}</h2>
            )}
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusBadge.color}`}>
            {statusBadge.label}
          </span>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-100">
          {docket.company && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Company</div>
              <div className="flex items-center gap-1.5 text-sm text-gray-900">
                <Building2 className="w-4 h-4 text-gray-400" />
                {docket.company}
              </div>
            </div>
          )}
          {docket.state_name && (
            <div>
              <div className="text-xs text-gray-500 mb-1">State</div>
              <div className="flex items-center gap-1.5 text-sm text-gray-900">
                <MapPin className="w-4 h-4 text-gray-400" />
                {docket.state_name}
              </div>
            </div>
          )}
          {docket.docket_type && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Type</div>
              <div className="text-sm text-gray-900">
                {formatDocketType(docket.docket_type)}
              </div>
            </div>
          )}
          {docket.first_seen_at && (
            <div>
              <div className="text-xs text-gray-500 mb-1">First Seen</div>
              <div className="flex items-center gap-1.5 text-sm text-gray-900">
                <Calendar className="w-4 h-4 text-gray-400" />
                {new Date(docket.first_seen_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Summary */}
      {docket.current_summary && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Summary</h3>
          <p className="text-gray-700 leading-relaxed">{docket.current_summary}</p>
        </div>
      )}

      {/* Description */}
      {docket.description && !docket.current_summary && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-3">Description</h3>
          <p className="text-gray-700 leading-relaxed">{docket.description}</p>
        </div>
      )}

      {/* Timeline */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Timeline</h3>

        {docket.timeline.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Clock className="w-8 h-8 mx-auto mb-2 text-gray-300" />
            <p>No hearing mentions yet</p>
          </div>
        ) : (
          <div className="relative">
            {/* Timeline line */}
            <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />

            <div className="space-y-6">
              {docket.timeline.map((item, index) => (
                <div key={item.hearing_id} className="relative pl-10">
                  {/* Timeline dot */}
                  <div className="absolute left-2.5 top-1.5 w-3 h-3 rounded-full bg-blue-500 border-2 border-white" />

                  <div className="bg-gray-50 rounded-lg p-4">
                    {/* Date */}
                    {item.hearing_date && (
                      <div className="text-sm font-medium text-gray-900 mb-2">
                        {new Date(item.hearing_date).toLocaleDateString('en-US', {
                          month: 'long',
                          day: 'numeric',
                          year: 'numeric',
                        })}
                      </div>
                    )}

                    {/* Summary */}
                    {item.mention_summary && (
                      <p className="text-sm text-gray-700 mb-3">{item.mention_summary}</p>
                    )}

                    {/* Hearing link */}
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-gray-500 truncate max-w-[60%]">
                        {item.hearing_title}
                      </span>
                      <Link
                        href={`/dashboard/hearings/${item.hearing_id}`}
                        className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium"
                      >
                        <Play className="w-3.5 h-3.5" />
                        Watch clip
                      </Link>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
