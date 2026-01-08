'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Search, FileText, BarChart3, Clock, Calendar } from 'lucide-react'
import { getStats, getHearings, type Stats, type HearingListItem } from '@/lib/api'
import { formatDate, formatDuration } from '@/lib/utils'

export default function DashboardHome() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [recentHearings, setRecentHearings] = useState<HearingListItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const [statsData, hearingsData] = await Promise.all([
          getStats(),
          getHearings({ limit: 5, has_analysis: true }),
        ])
        setStats(statsData)
        setRecentHearings(hearingsData.items)
      } catch (error) {
        console.error('Error loading dashboard data:', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="grid gap-4 md:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-gray-200 rounded-xl" />
          ))}
        </div>
        <div className="h-96 bg-gray-200 rounded-xl" />
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Hearings"
          value={stats?.total_hearings || 0}
          icon={<FileText className="h-5 w-5" />}
          color="blue"
        />
        <StatCard
          title="Hours Transcribed"
          value={Math.round(stats?.total_hours || 0)}
          icon={<Clock className="h-5 w-5" />}
          color="green"
        />
        <StatCard
          title="States Covered"
          value={stats?.total_states || 0}
          icon={<BarChart3 className="h-5 w-5" />}
          color="purple"
        />
        <StatCard
          title="Last 7 Days"
          value={stats?.hearings_last_7d || 0}
          subtitle="new hearings"
          icon={<Calendar className="h-5 w-5" />}
          color="orange"
        />
      </div>

      {/* Quick Search */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Search</h2>
        <Link
          href="/dashboard/search"
          className="flex items-center gap-3 px-4 py-3 bg-gray-50 rounded-lg hover:bg-gray-100 transition-colors group"
        >
          <Search className="h-5 w-5 text-gray-400 group-hover:text-blue-600" />
          <span className="text-gray-500 group-hover:text-gray-700">
            Search transcripts, hearings, and dockets...
          </span>
        </Link>
      </div>

      {/* Status Overview */}
      {stats && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Processing Status</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {Object.entries(stats.hearings_by_status).map(([status, count]) => (
              <div
                key={status}
                className="flex items-center justify-between p-3 bg-gray-50 rounded-lg"
              >
                <span className="text-sm text-gray-600 capitalize">{status}</span>
                <span className="font-semibold text-gray-900">{count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Analyzed Hearings */}
      <div className="bg-white rounded-xl border border-gray-200">
        <div className="p-6 border-b border-gray-100">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">Recent Analyzed Hearings</h2>
            <Link
              href="/dashboard/hearings"
              className="text-sm text-blue-600 hover:text-blue-700 font-medium"
            >
              View all →
            </Link>
          </div>
        </div>

        {recentHearings.length === 0 ? (
          <div className="p-12 text-center">
            <FileText className="h-12 w-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No analyzed hearings yet</h3>
            <p className="text-gray-500">
              Hearings will appear here once they've been transcribed and analyzed.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {recentHearings.map((hearing) => (
              <Link
                key={hearing.id}
                href={`/dashboard/hearings/${hearing.id}`}
                className="block p-4 hover:bg-gray-50 transition-colors"
              >
                <div className="flex items-start gap-4">
                  <div className="h-12 w-12 rounded-lg bg-gradient-to-br from-blue-500 to-blue-600 flex items-center justify-center flex-shrink-0">
                    <span className="text-sm font-bold text-white">{hearing.state_code}</span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-gray-900 line-clamp-1">
                      {hearing.title || 'Untitled Hearing'}
                    </h3>
                    <div className="flex items-center gap-3 mt-1 text-sm text-gray-500">
                      <span>{formatDate(hearing.hearing_date)}</span>
                      {hearing.duration_seconds && (
                        <span>{formatDuration(hearing.duration_seconds)}</span>
                      )}
                      {hearing.utility_name && <span>{hearing.utility_name}</span>}
                    </div>
                    {hearing.one_sentence_summary && (
                      <p className="mt-2 text-sm text-gray-600 line-clamp-2">
                        {hearing.one_sentence_summary}
                      </p>
                    )}
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function StatCard({
  title,
  value,
  subtitle,
  icon,
  color,
}: {
  title: string
  value: number
  subtitle?: string
  icon: React.ReactNode
  color: 'blue' | 'green' | 'purple' | 'orange'
}) {
  const colorStyles = {
    blue: 'bg-blue-50 text-blue-600',
    green: 'bg-green-50 text-green-600',
    purple: 'bg-purple-50 text-purple-600',
    orange: 'bg-orange-50 text-orange-600',
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${colorStyles[color]}`}>{icon}</div>
        <span className="text-sm font-medium text-gray-500">{title}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-2xl font-bold text-gray-900">{value.toLocaleString()}</span>
        {subtitle && <span className="text-sm text-gray-500">{subtitle}</span>}
      </div>
    </div>
  )
}
