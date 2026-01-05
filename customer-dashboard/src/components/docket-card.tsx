'use client'

import Link from 'next/link'
import { Clock, Building2, Calendar, ChevronRight, Eye, EyeOff } from 'lucide-react'

interface LatestMention {
  summary?: string
  hearing_date?: string
  hearing_title?: string
  hearing_id?: number
}

interface DocketCardProps {
  docket: {
    id: number
    normalized_id: string
    docket_number: string
    state_code?: string
    state_name?: string
    docket_type?: string
    company?: string
    status?: string
    mention_count: number
    first_seen_at?: string
    last_mentioned_at?: string
    hearing_count?: number
    latest_mention?: LatestMention
  }
  isWatched?: boolean
  onToggleWatch?: () => void
  showWatchButton?: boolean
}

function getStatusIndicator(status?: string) {
  switch (status?.toLowerCase()) {
    case 'open':
    case 'under_review':
    case 'active':
      return { color: 'bg-red-500', label: 'Active' }
    case 'pending':
    case 'pending_decision':
      return { color: 'bg-yellow-500', label: 'Pending' }
    case 'closed':
    case 'decided':
      return { color: 'bg-green-500', label: 'Closed' }
    default:
      return { color: 'bg-gray-400', label: 'Unknown' }
  }
}

function formatRelativeTime(dateStr?: string): string {
  if (!dateStr) return 'Unknown'

  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24))

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays} days ago`
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} months ago`
  return `${Math.floor(diffDays / 365)} years ago`
}

function formatDocketType(type?: string): string {
  if (!type) return ''
  return type
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

export function DocketCard({ docket, isWatched = false, onToggleWatch, showWatchButton = true }: DocketCardProps) {
  const statusInfo = getStatusIndicator(docket.status)

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:border-blue-300 hover:shadow-md transition-all">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`w-2.5 h-2.5 rounded-full ${statusInfo.color}`} title={statusInfo.label} />
          <span className="font-mono text-sm font-semibold text-gray-900">
            {docket.normalized_id}
          </span>
          {docket.docket_type && (
            <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
              {formatDocketType(docket.docket_type)}
            </span>
          )}
        </div>
        {showWatchButton && onToggleWatch && (
          <button
            onClick={(e) => {
              e.preventDefault()
              onToggleWatch()
            }}
            className={`p-1.5 rounded-md transition-colors ${
              isWatched
                ? 'text-blue-600 bg-blue-50 hover:bg-blue-100'
                : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'
            }`}
            title={isWatched ? 'Stop watching' : 'Watch this docket'}
          >
            {isWatched ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
          </button>
        )}
      </div>

      {/* Company */}
      {docket.company && (
        <div className="flex items-center gap-1.5 text-sm text-gray-700 mb-2">
          <Building2 className="w-4 h-4 text-gray-400" />
          <span>{docket.company}</span>
        </div>
      )}

      {/* Status line */}
      <div className="text-xs text-gray-500 mb-3">
        Status: {statusInfo.label}
        {docket.state_code && ` · ${docket.state_code}`}
      </div>

      {/* Latest mention summary */}
      {docket.latest_mention?.summary && (
        <div className="bg-gray-50 rounded-md p-3 mb-3">
          <p className="text-sm text-gray-700 line-clamp-2">
            {docket.latest_mention.summary}
          </p>
          {docket.latest_mention.hearing_date && (
            <p className="text-xs text-gray-500 mt-1">
              {new Date(docket.latest_mention.hearing_date).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric'
              })}
            </p>
          )}
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3 text-xs text-gray-500">
          <span className="flex items-center gap-1">
            <Calendar className="w-3.5 h-3.5" />
            {docket.hearing_count || docket.mention_count} hearing{(docket.hearing_count || docket.mention_count) !== 1 ? 's' : ''}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {formatRelativeTime(docket.last_mentioned_at)}
          </span>
        </div>
        <Link
          href={`/dashboard/dockets/${docket.normalized_id}`}
          className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-700 font-medium"
        >
          View
          <ChevronRight className="w-4 h-4" />
        </Link>
      </div>
    </div>
  )
}
