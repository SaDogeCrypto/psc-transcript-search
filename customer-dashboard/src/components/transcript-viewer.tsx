'use client'

import { useRef, useEffect, useState } from 'react'
import { User, Clock, ChevronDown, ChevronUp } from 'lucide-react'
import { formatTimestamp } from '@/lib/utils'
import type { Segment } from '@/lib/api'

interface TranscriptViewerProps {
  segments: Segment[]
  currentTime?: number
  onSegmentClick?: (segment: Segment) => void
  loading?: boolean
  hasMore?: boolean
  onLoadMore?: () => void
}

export function TranscriptViewer({
  segments,
  currentTime = 0,
  onSegmentClick,
  loading,
  hasMore,
  onLoadMore,
}: TranscriptViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [activeSegmentId, setActiveSegmentId] = useState<number | null>(null)

  // Find and highlight the current segment based on video time
  useEffect(() => {
    const currentSegment = segments.find(
      (s) => currentTime >= s.start_time && currentTime < s.end_time
    )

    if (currentSegment && currentSegment.id !== activeSegmentId) {
      setActiveSegmentId(currentSegment.id)

      // Auto-scroll to current segment
      if (autoScroll && containerRef.current) {
        const element = document.getElementById(`segment-${currentSegment.id}`)
        if (element) {
          element.scrollIntoView({
            behavior: 'smooth',
            block: 'center',
          })
        }
      }
    }
  }, [currentTime, segments, activeSegmentId, autoScroll])

  // Detect manual scroll to disable auto-scroll
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    let scrollTimeout: NodeJS.Timeout

    const handleScroll = () => {
      setAutoScroll(false)
      clearTimeout(scrollTimeout)
      scrollTimeout = setTimeout(() => {
        // Re-enable auto-scroll after 5 seconds of no scrolling
        setAutoScroll(true)
      }, 5000)
    }

    container.addEventListener('scroll', handleScroll)
    return () => {
      container.removeEventListener('scroll', handleScroll)
      clearTimeout(scrollTimeout)
    }
  }, [])

  if (loading && segments.length === 0) {
    return (
      <div className="space-y-4 p-4">
        {[1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="animate-pulse">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-4 w-4 bg-gray-200 rounded-full" />
              <div className="h-4 w-24 bg-gray-200 rounded" />
            </div>
            <div className="h-16 bg-gray-200 rounded" />
          </div>
        ))}
      </div>
    )
  }

  if (segments.length === 0) {
    return (
      <div className="flex items-center justify-center h-64 text-gray-500">
        No transcript available
      </div>
    )
  }

  // Group segments by speaker for cleaner display
  const groupedSegments = groupBySpeaker(segments)

  return (
    <div className="flex flex-col h-full">
      {/* Auto-scroll indicator */}
      {!autoScroll && (
        <button
          onClick={() => setAutoScroll(true)}
          className="sticky top-0 z-10 w-full py-2 bg-blue-50 text-blue-600 text-sm font-medium flex items-center justify-center gap-2 hover:bg-blue-100"
        >
          <ChevronDown className="h-4 w-4" />
          Resume auto-scroll
        </button>
      )}

      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto p-4 space-y-4"
      >
        {groupedSegments.map((group, groupIndex) => (
          <div key={groupIndex} className="space-y-2">
            {/* Speaker header */}
            {group.speaker && (
              <div className="flex items-center gap-2 text-sm text-gray-500 sticky top-0 bg-white py-1">
                <User className="h-4 w-4" />
                <span className="font-medium">{group.speaker}</span>
                {group.role && (
                  <span className="px-2 py-0.5 bg-gray-100 rounded text-xs">
                    {group.role}
                  </span>
                )}
              </div>
            )}

            {/* Segments */}
            {group.segments.map((segment) => (
              <button
                key={segment.id}
                id={`segment-${segment.id}`}
                onClick={() => onSegmentClick?.(segment)}
                className={`w-full text-left p-3 rounded-lg transition-colors ${
                  activeSegmentId === segment.id
                    ? 'bg-blue-50 border-l-4 border-blue-500'
                    : 'hover:bg-gray-50 border-l-4 border-transparent'
                }`}
              >
                <div className="flex items-center gap-2 mb-1 text-xs text-gray-400">
                  <Clock className="h-3 w-3" />
                  <span>{formatTimestamp(segment.start_time)}</span>
                </div>
                <p className={`text-sm leading-relaxed ${
                  activeSegmentId === segment.id ? 'text-gray-900' : 'text-gray-700'
                }`}>
                  {segment.text}
                </p>
              </button>
            ))}
          </div>
        ))}

        {/* Load more button */}
        {hasMore && (
          <button
            onClick={onLoadMore}
            disabled={loading}
            className="w-full py-3 text-center text-sm text-blue-600 hover:text-blue-700 disabled:text-gray-400"
          >
            {loading ? 'Loading...' : 'Load more segments'}
          </button>
        )}
      </div>
    </div>
  )
}

// Group consecutive segments by the same speaker
function groupBySpeaker(segments: Segment[]): Array<{
  speaker: string | null
  role: string | null
  segments: Segment[]
}> {
  const groups: Array<{
    speaker: string | null
    role: string | null
    segments: Segment[]
  }> = []

  let currentGroup: typeof groups[0] | null = null

  for (const segment of segments) {
    if (!currentGroup || currentGroup.speaker !== segment.speaker) {
      currentGroup = {
        speaker: segment.speaker,
        role: segment.speaker_role,
        segments: [],
      }
      groups.push(currentGroup)
    }
    currentGroup.segments.push(segment)
  }

  return groups
}
