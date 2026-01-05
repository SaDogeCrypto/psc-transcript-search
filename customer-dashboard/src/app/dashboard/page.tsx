'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { Plus, Filter, FileText, RefreshCw } from 'lucide-react'
import {
  getWatchlist,
  getActivityFeed,
  addToWatchlist,
  removeFromWatchlist,
  type WatchlistDocket,
  type ActivityItem,
} from '@/lib/api'
import { DocketCard } from '@/components/docket-card'
import { ActivityFeedItem } from '@/components/activity-feed-item'
import { AddDocketModal } from '@/components/add-docket-modal'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

export default function DashboardHome() {
  const [watchlist, setWatchlist] = useState<WatchlistDocket[]>([])
  const [activity, setActivity] = useState<ActivityItem[]>([])
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [refreshing, setRefreshing] = useState(false)

  const loadData = async () => {
    try {
      const [watchlistData, activityData] = await Promise.all([
        getWatchlist(),
        getActivityFeed({ limit: 10 }),
      ])
      setWatchlist(watchlistData.dockets)
      setActivity(activityData.items)
    } catch (error) {
      console.error('Error loading dashboard data:', error)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [])

  const handleRefresh = () => {
    setRefreshing(true)
    loadData()
  }

  const handleAddDocket = async (docketId: number) => {
    await addToWatchlist(docketId)
    // Reload watchlist
    const watchlistData = await getWatchlist()
    setWatchlist(watchlistData.dockets)
  }

  const handleRemoveDocket = async (docketId: number) => {
    await removeFromWatchlist(docketId)
    setWatchlist((prev) => prev.filter((d) => d.id !== docketId))
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-48" />
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-40 bg-gray-200 rounded-lg" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Watchlist Section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="text-xl font-semibold text-gray-900">
              Your Watchlist
            </h2>
            <span className="text-sm text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full">
              {watchlist.length}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleRefresh}
              disabled={refreshing}
              className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
              title="Refresh"
            >
              <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
            </button>
            <button
              onClick={() => setIsModalOpen(true)}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Add Docket
            </button>
          </div>
        </div>

        {watchlist.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              No dockets in your watchlist
            </h3>
            <p className="text-gray-500 mb-4">
              Add dockets to track regulatory proceedings across states
            </p>
            <button
              onClick={() => setIsModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              <Plus className="w-4 h-4" />
              Add Your First Docket
            </button>
          </div>
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {watchlist.map((docket) => (
              <DocketCard
                key={docket.id}
                docket={docket}
                isWatched={true}
                onToggleWatch={() => handleRemoveDocket(docket.id)}
              />
            ))}
          </div>
        )}
      </section>

      {/* Activity Feed Section */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl font-semibold text-gray-900">Recent Activity</h2>
          <button className="flex items-center gap-2 px-3 py-2 text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors text-sm">
            <Filter className="w-4 h-4" />
            Filter
          </button>
        </div>

        {activity.length === 0 ? (
          <div className="bg-white rounded-xl border border-gray-200 p-12 text-center">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">
              No recent activity
            </h3>
            <p className="text-gray-500">
              New hearings and transcripts will appear here
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {activity.map((item, index) => (
              <ActivityFeedItem key={`${item.hearing_id}-${index}`} activity={item} />
            ))}

            {activity.length >= 10 && (
              <div className="text-center pt-4">
                <Link
                  href="/dashboard/hearings"
                  className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                >
                  View all hearings →
                </Link>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Add Docket Modal */}
      <AddDocketModal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        onAdd={handleAddDocket}
        watchedDocketIds={watchlist.map((d) => d.id)}
        apiUrl={API_URL}
      />
    </div>
  )
}
