'use client'

import { useState, useEffect, useRef } from 'react'
import Link from 'next/link'
import { useParams } from 'next/navigation'
import {
  ArrowLeft,
  Calendar,
  Clock,
  Building2,
  ExternalLink,
  FileText,
  Users,
  AlertTriangle,
  TrendingUp,
  MessageSquare,
} from 'lucide-react'
import { getHearing, type HearingDetail, type Segment } from '@/lib/api'
import { formatDate, formatDuration } from '@/lib/utils'
import { VideoPlayer, type VideoPlayerRef } from '@/components/video-player'
import { TranscriptViewer } from '@/components/transcript-viewer'

export default function HearingDetailPage() {
  const params = useParams()
  const hearingId = params.id as string

  const videoRef = useRef<VideoPlayerRef>(null)
  const [hearing, setHearing] = useState<HearingDetail | null>(null)
  const [currentTime, setCurrentTime] = useState(0)
  const [loading, setLoading] = useState(true)

  // Active tab for analysis sections
  const [activeTab, setActiveTab] = useState<'summary' | 'transcript' | 'analysis'>('summary')

  useEffect(() => {
    async function loadHearing() {
      setLoading(true)
      try {
        const hearingData = await getHearing(hearingId)
        setHearing(hearingData)
      } catch (error) {
        console.error('Error loading hearing:', error)
      } finally {
        setLoading(false)
      }
    }

    loadHearing()
  }, [hearingId])

  const handleSegmentClick = (segment: Segment) => {
    if (segment.start_time !== null) {
      videoRef.current?.seekTo(segment.start_time)
    }
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-48" />
        <div className="aspect-video bg-gray-200 rounded-lg" />
        <div className="h-64 bg-gray-200 rounded-lg" />
      </div>
    )
  }

  if (!hearing) {
    return (
      <div className="text-center py-12">
        <h2 className="text-xl font-semibold text-gray-900">Hearing not found</h2>
        <Link href="/dashboard/hearings" className="text-blue-600 hover:underline mt-4 block">
          Back to hearings
        </Link>
      </div>
    )
  }

  const analysis = hearing.analysis
  const segments = hearing.segments || []
  const videoUrl = hearing.youtube_url || hearing.video_url

  return (
    <div className="space-y-6">
      {/* Back button and title */}
      <div className="flex items-start gap-4">
        <Link
          href="/dashboard/hearings"
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
        >
          <ArrowLeft className="h-5 w-5 text-gray-600" />
        </Link>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <span className="px-3 py-1 bg-blue-100 text-blue-700 rounded-full text-sm font-medium">
              {hearing.state_code}
            </span>
            {hearing.hearing_type && (
              <span className="px-3 py-1 bg-gray-100 text-gray-700 rounded-full text-sm font-medium">
                {hearing.hearing_type}
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold text-gray-900">{hearing.title || 'Untitled Hearing'}</h1>
          <div className="flex flex-wrap items-center gap-4 mt-2 text-sm text-gray-500">
            <span className="flex items-center gap-1">
              <Calendar className="h-4 w-4" />
              {formatDate(hearing.hearing_date)}
            </span>
            {hearing.duration_seconds && (
              <span className="flex items-center gap-1">
                <Clock className="h-4 w-4" />
                {formatDuration(hearing.duration_seconds)}
              </span>
            )}
            {(analysis?.utility_name || hearing.utility_name) && (
              <span className="flex items-center gap-1">
                <Building2 className="h-4 w-4" />
                {analysis?.utility_name || hearing.utility_name}
              </span>
            )}
            {videoUrl && (
              <a
                href={videoUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1 text-blue-600 hover:underline"
              >
                <ExternalLink className="h-4 w-4" />
                Source
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Video + Content Grid */}
      <div className="grid lg:grid-cols-2 gap-6">
        {/* Video Section */}
        <div className="space-y-4">
          {videoUrl ? (
            <VideoPlayer
              ref={videoRef}
              src={videoUrl}
              onTimeUpdate={setCurrentTime}
            />
          ) : (
            <div className="aspect-video bg-gray-100 rounded-lg flex items-center justify-center">
              <p className="text-gray-500">No video available</p>
            </div>
          )}

          {/* One-sentence summary */}
          {(analysis?.one_sentence_summary || hearing.one_sentence_summary) && (
            <div className="p-4 bg-blue-50 rounded-lg border border-blue-100">
              <p className="text-blue-900 font-medium">
                {analysis?.one_sentence_summary || hearing.one_sentence_summary}
              </p>
            </div>
          )}
        </div>

        {/* Tabs and Content */}
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden flex flex-col min-h-[500px]">
          {/* Tab Headers */}
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setActiveTab('summary')}
              className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === 'summary'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              Summary
            </button>
            <button
              onClick={() => setActiveTab('transcript')}
              className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === 'transcript'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              Transcript
            </button>
            <button
              onClick={() => setActiveTab('analysis')}
              className={`flex-1 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === 'analysis'
                  ? 'text-blue-600 border-b-2 border-blue-600 bg-blue-50'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
              }`}
            >
              Analysis
            </button>
          </div>

          {/* Tab Content */}
          <div className="flex-1 overflow-hidden">
            {activeTab === 'summary' && (
              <div className="p-4 overflow-y-auto h-full space-y-6">
                {/* Full Summary */}
                {analysis?.summary && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2">Summary</h3>
                    <p className="text-gray-700 whitespace-pre-wrap">{analysis.summary}</p>
                  </div>
                )}

                {/* Key Issues */}
                {analysis?.issues && analysis.issues.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4" />
                      Key Issues
                    </h3>
                    <div className="space-y-2">
                      {analysis.issues.map((issue, i) => (
                        <div key={i} className="p-3 bg-gray-50 rounded-lg">
                          <p className="font-medium text-gray-900">{issue.issue}</p>
                          <p className="text-sm text-gray-600 mt-1">{issue.description}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Notable Quotes */}
                {analysis?.quotes && analysis.quotes.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <MessageSquare className="h-4 w-4" />
                      Notable Quotes
                    </h3>
                    <div className="space-y-3">
                      {analysis.quotes.map((quote, i) => (
                        <div key={i} className="border-l-4 border-blue-400 pl-4 py-2">
                          <p className="text-gray-700 italic">"{quote.quote}"</p>
                          <p className="text-sm text-gray-500 mt-1">
                            — {quote.speaker}
                          </p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* No analysis yet */}
                {!analysis && (
                  <div className="text-center py-8 text-gray-500">
                    <FileText className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                    <p>Analysis not yet available for this hearing.</p>
                  </div>
                )}
              </div>
            )}

            {activeTab === 'transcript' && (
              <TranscriptViewer
                segments={segments}
                currentTime={currentTime}
                onSegmentClick={handleSegmentClick}
              />
            )}

            {activeTab === 'analysis' && (
              <div className="p-4 overflow-y-auto h-full space-y-6">
                {/* Participants */}
                {analysis?.participants && analysis.participants.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <Users className="h-4 w-4" />
                      Participants
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {analysis.participants.map((p, i) => (
                        <span
                          key={i}
                          className="px-3 py-1.5 bg-gray-100 rounded-full text-sm"
                        >
                          <span className="font-medium">{p.name}</span>
                          {p.role && (
                            <span className="text-gray-500"> - {p.role}</span>
                          )}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Commissioner Concerns */}
                {analysis?.commissioner_concerns && analysis.commissioner_concerns.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2">
                      Commissioner Concerns
                    </h3>
                    <div className="space-y-2">
                      {analysis.commissioner_concerns.map((concern, i) => (
                        <div key={i} className="p-3 bg-yellow-50 border border-yellow-100 rounded-lg">
                          <p className="font-medium text-gray-900">{concern.commissioner}</p>
                          <p className="text-sm text-gray-700 mt-1">{concern.concern}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Commissioner Mood */}
                {analysis?.commissioner_mood && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2">
                      Overall Commissioner Sentiment
                    </h3>
                    <span className={`px-3 py-1.5 rounded-full text-sm font-medium ${
                      analysis.commissioner_mood === 'supportive'
                        ? 'bg-green-100 text-green-700'
                        : analysis.commissioner_mood === 'skeptical'
                        ? 'bg-yellow-100 text-yellow-700'
                        : analysis.commissioner_mood === 'hostile'
                        ? 'bg-red-100 text-red-700'
                        : 'bg-gray-100 text-gray-700'
                    }`}>
                      {analysis.commissioner_mood}
                    </span>
                  </div>
                )}

                {/* Commitments */}
                {analysis?.commitments && analysis.commitments.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <FileText className="h-4 w-4" />
                      Commitments Made
                    </h3>
                    <div className="space-y-2">
                      {analysis.commitments.map((c, i) => (
                        <div key={i} className="p-3 bg-green-50 border border-green-100 rounded-lg">
                          <p className="font-medium text-gray-900">{c.commitment}</p>
                          <p className="text-sm text-gray-600 mt-1">{c.context}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Likely Outcome */}
                {analysis?.likely_outcome && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <TrendingUp className="h-4 w-4" />
                      Likely Outcome
                    </h3>
                    <div className="p-4 bg-blue-50 border border-blue-100 rounded-lg">
                      <p className="text-gray-700">{analysis.likely_outcome}</p>
                      {analysis.outcome_confidence && (
                        <p className="text-sm text-gray-500 mt-2">
                          Confidence: {Math.round(analysis.outcome_confidence * 100)}%
                        </p>
                      )}
                    </div>
                  </div>
                )}

                {/* Risk Factors */}
                {analysis?.risk_factors && analysis.risk_factors.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-gray-500 mb-2 flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4" />
                      Risk Factors
                    </h3>
                    <div className="space-y-2">
                      {analysis.risk_factors.map((risk, i) => (
                        <div key={i} className="p-3 bg-red-50 border border-red-100 rounded-lg">
                          <p className="font-medium text-gray-900">{risk}</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* No analysis yet */}
                {!analysis && (
                  <div className="text-center py-8 text-gray-500">
                    <FileText className="h-12 w-12 mx-auto mb-4 text-gray-300" />
                    <p>Analysis not yet available for this hearing.</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
