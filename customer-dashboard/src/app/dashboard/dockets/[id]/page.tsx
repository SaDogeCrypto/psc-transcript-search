'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useParams, useRouter } from 'next/navigation'
import {
  ArrowLeft,
  Share2,
  Building2,
  Calendar,
  Clock,
  Play,
  FileText,
} from 'lucide-react'
import { getDocket } from '@/lib/api'
import { formatDate } from '@/lib/utils'

function getStatusBadge(status?: string | null) {
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

function formatDocketType(type?: string | null): string {
  if (!type) return 'Unknown'
  return type
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ')
}

interface DocketDetail {
  id: string
  docket_number: string
  state_code: string
  title: string | null
  status: string | null
  docket_type: string | null
  filed_date: string | null
  closed_date: string | null
  documents: any[]
  hearings: any[]
}

export default function DocketDetailPage() {
  const params = useParams()
  const router = useRouter()
  const docketId = params.id as string

  const [docket, setDocket] = useState<DocketDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function loadDocket() {
      try {
        const docketData = await getDocket(docketId)
        setDocket(docketData)
      } catch (err) {
        console.error('Error loading docket:', err)
        setError('Docket not found')
      } finally {
        setLoading(false)
      }
    }
    loadDocket()
  }, [docketId])

  const handleShare = () => {
    navigator.clipboard.writeText(window.location.href)
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
        <p className="text-gray-500 mb-4">The docket could not be found.</p>
        <button
          onClick={() => router.back()}
          className="text-blue-600 hover:text-blue-700 font-medium"
        >
          Go back
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
        <button
          onClick={handleShare}
          className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
        >
          <Share2 className="w-4 h-4" />
          Share
        </button>
      </div>

      {/* Docket Header */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 font-mono mb-2">
              {docket.docket_number}
            </h1>
            {docket.title && (
              <h2 className="text-lg text-gray-700">{docket.title}</h2>
            )}
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusBadge.color}`}>
            {statusBadge.label}
          </span>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 pt-4 border-t border-gray-100">
          <div>
            <div className="text-xs text-gray-500 mb-1">State</div>
            <div className="flex items-center gap-1.5 text-sm text-gray-900">
              <Building2 className="w-4 h-4 text-gray-400" />
              {docket.state_code}
            </div>
          </div>
          {docket.docket_type && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Type</div>
              <div className="text-sm text-gray-900">
                {formatDocketType(docket.docket_type)}
              </div>
            </div>
          )}
          {docket.filed_date && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Filed Date</div>
              <div className="flex items-center gap-1.5 text-sm text-gray-900">
                <Calendar className="w-4 h-4 text-gray-400" />
                {formatDate(docket.filed_date)}
              </div>
            </div>
          )}
          {docket.closed_date && (
            <div>
              <div className="text-xs text-gray-500 mb-1">Closed Date</div>
              <div className="flex items-center gap-1.5 text-sm text-gray-900">
                <Calendar className="w-4 h-4 text-gray-400" />
                {formatDate(docket.closed_date)}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Related Hearings */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h3 className="text-lg font-semibold text-gray-900 mb-4">Related Hearings</h3>

        {!docket.hearings || docket.hearings.length === 0 ? (
          <div className="text-center py-8 text-gray-500">
            <Clock className="w-8 h-8 mx-auto mb-2 text-gray-300" />
            <p>No hearings associated with this docket</p>
          </div>
        ) : (
          <div className="space-y-4">
            {docket.hearings.map((hearing: any) => (
              <div key={hearing.id} className="bg-gray-50 rounded-lg p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-gray-900 mb-1">
                      {hearing.title || 'Untitled Hearing'}
                    </div>
                    <div className="flex items-center gap-3 text-xs text-gray-500">
                      {hearing.hearing_date && (
                        <span className="flex items-center gap-1">
                          <Calendar className="w-3.5 h-3.5" />
                          {formatDate(hearing.hearing_date)}
                        </span>
                      )}
                      {hearing.hearing_type && (
                        <span className="px-2 py-0.5 bg-gray-200 rounded">
                          {hearing.hearing_type}
                        </span>
                      )}
                    </div>
                  </div>
                  <Link
                    href={`/dashboard/hearings/${hearing.id}`}
                    className="flex items-center gap-1.5 text-sm text-blue-600 hover:text-blue-700 font-medium ml-4"
                  >
                    <Play className="w-3.5 h-3.5" />
                    View
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Related Documents */}
      {docket.documents && docket.documents.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h3 className="text-lg font-semibold text-gray-900 mb-4">Documents</h3>
          <div className="space-y-2">
            {docket.documents.map((doc: any) => (
              <div key={doc.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                <div className="flex items-center gap-3">
                  <FileText className="w-4 h-4 text-gray-400" />
                  <span className="text-sm text-gray-700">{doc.title || doc.filename || 'Document'}</span>
                </div>
                {doc.url && (
                  <a
                    href={doc.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    View
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
