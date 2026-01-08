'use client'

import Link from 'next/link'
import { Calendar, FileText, Video, BarChart3, TrendingUp } from 'lucide-react'

interface DocketMention {
  normalized_id: string
  title?: string
  docket_type?: string
}

interface ActivityFeedItemProps {
  activity: {
    date: string
    state_code: string
    state_name: string
    activity_type: 'new_hearing' | 'transcript_ready' | 'analysis_complete'
    hearing_title: string
    hearing_id: number
    dockets_mentioned: DocketMention[]
    // Analysis data
    one_sentence_summary?: string
    commissioner_mood?: string
    likely_outcome?: string
  }
}

function getActivityIcon(type: string) {
  switch (type) {
    case 'new_hearing':
      return <Video className="w-4 h-4" />
    case 'transcript_ready':
      return <FileText className="w-4 h-4" />
    case 'analysis_complete':
      return <BarChart3 className="w-4 h-4" />
    default:
      return <Calendar className="w-4 h-4" />
  }
}

function getActivityLabel(type: string) {
  switch (type) {
    case 'new_hearing':
      return 'New hearing posted'
    case 'transcript_ready':
      return 'Transcript available'
    case 'analysis_complete':
      return 'Analysis complete'
    default:
      return 'Activity'
  }
}

function getActivityAction(type: string) {
  switch (type) {
    case 'new_hearing':
      return 'Watch'
    case 'transcript_ready':
      return 'Read'
    case 'analysis_complete':
      return 'View'
    default:
      return 'View'
  }
}

function getMoodColor(mood?: string) {
  switch (mood) {
    case 'supportive':
      return 'bg-green-100 text-green-700'
    case 'skeptical':
      return 'bg-yellow-100 text-yellow-700'
    case 'hostile':
      return 'bg-red-100 text-red-700'
    case 'mixed':
      return 'bg-orange-100 text-orange-700'
    default:
      return 'bg-gray-100 text-gray-700'
  }
}

export function ActivityFeedItem({ activity }: ActivityFeedItemProps) {
  const formattedDate = new Date(activity.date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric'
  })

  const hasAnalysis = activity.one_sentence_summary || activity.commissioner_mood

  return (
    <div className="bg-white rounded-lg border border-gray-200 p-4 hover:border-gray-300 transition-colors">
      {/* Header with date and state */}
      <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
        <Calendar className="w-4 h-4" />
        <span>{formattedDate}</span>
        <span className="text-gray-300">·</span>
        <span className="font-medium text-gray-700">{activity.state_code} {activity.state_name.split(' ')[0]}</span>
      </div>

      {/* Activity type badge and mood */}
      <div className="flex items-center gap-2 mb-2 flex-wrap">
        <span className="inline-flex items-center gap-1.5 text-xs bg-blue-50 text-blue-700 px-2 py-1 rounded">
          {getActivityIcon(activity.activity_type)}
          {getActivityLabel(activity.activity_type)}
        </span>
        {activity.commissioner_mood && (
          <span className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded capitalize ${getMoodColor(activity.commissioner_mood)}`}>
            {activity.commissioner_mood}
          </span>
        )}
      </div>

      {/* Hearing title */}
      <h4 className="text-sm font-medium text-gray-900 mb-2 line-clamp-2">
        {activity.hearing_title}
      </h4>

      {/* Analysis summary */}
      {activity.one_sentence_summary && (
        <div className="mb-3 p-2 bg-blue-50 rounded-md border-l-2 border-blue-400">
          <p className="text-sm text-blue-900">{activity.one_sentence_summary}</p>
        </div>
      )}

      {/* Likely outcome */}
      {activity.likely_outcome && (
        <div className="mb-3 flex items-start gap-2">
          <TrendingUp className="w-4 h-4 text-gray-400 mt-0.5 flex-shrink-0" />
          <p className="text-xs text-gray-600">{activity.likely_outcome}</p>
        </div>
      )}

      {/* Dockets mentioned */}
      {activity.dockets_mentioned.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap mb-3">
          <span className="text-xs text-gray-500">Mentions:</span>
          {activity.dockets_mentioned.map((docket) => (
            <Link
              key={docket.normalized_id}
              href={`/dashboard/dockets/${docket.normalized_id}`}
              className="text-xs bg-gray-100 text-gray-700 px-2 py-0.5 rounded hover:bg-gray-200 transition-colors"
            >
              {docket.normalized_id}
            </Link>
          ))}
        </div>
      )}

      {/* Action link */}
      <div className="flex justify-end">
        <Link
          href={`/dashboard/hearings/${activity.hearing_id}`}
          className="text-sm text-blue-600 hover:text-blue-700 font-medium"
        >
          {hasAnalysis ? 'View Analysis' : getActivityAction(activity.activity_type)} →
        </Link>
      </div>
    </div>
  )
}
