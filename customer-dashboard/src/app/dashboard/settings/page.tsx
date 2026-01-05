'use client'

import { useState, useEffect } from 'react'
import { useSession } from 'next-auth/react'
import {
  Bell,
  Mail,
  MapPin,
  Save,
  Check,
  AlertCircle,
} from 'lucide-react'
import { getStates, type State } from '@/lib/api'

export default function SettingsPage() {
  const { data: session } = useSession()
  const [states, setStates] = useState<State[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // User preferences (stored in localStorage for MVP)
  const [followedStates, setFollowedStates] = useState<string[]>([])
  const [alertFrequency, setAlertFrequency] = useState<'daily' | 'weekly' | 'off'>('daily')
  const [emailAlerts, setEmailAlerts] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        // Load states
        const statesData = await getStates()
        setStates(statesData)

        // Load preferences from localStorage
        const savedPrefs = localStorage.getItem('userPreferences')
        if (savedPrefs) {
          const prefs = JSON.parse(savedPrefs)
          setFollowedStates(prefs.followed_states || ['GA', 'FL', 'TX'])
          setAlertFrequency(prefs.alert_frequency || 'daily')
          setEmailAlerts(prefs.email_alerts ?? true)
        } else {
          // Demo defaults
          setFollowedStates(['GA', 'FL', 'TX'])
        }
      } catch (error) {
        console.error('Error loading settings:', error)
      } finally {
        setLoading(false)
      }
    }

    loadData()
  }, [])

  const toggleState = (code: string) => {
    setFollowedStates((prev) =>
      prev.includes(code) ? prev.filter((s) => s !== code) : [...prev, code]
    )
    setSaved(false)
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)

    try {
      // Save to localStorage for MVP
      const prefs = {
        followed_states: followedStates,
        alert_frequency: alertFrequency,
        email_alerts: emailAlerts,
      }
      localStorage.setItem('userPreferences', JSON.stringify(prefs))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (err) {
      setError('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="animate-pulse space-y-6">
        <div className="h-8 bg-gray-200 rounded w-48" />
        <div className="h-64 bg-gray-200 rounded-lg" />
        <div className="h-48 bg-gray-200 rounded-lg" />
      </div>
    )
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-500 mt-1">Manage your alert preferences and followed states</p>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
          <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
          <p className="text-sm text-red-700">{error}</p>
        </div>
      )}

      {/* States Selection */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="h-10 w-10 rounded-lg bg-blue-100 flex items-center justify-center">
            <MapPin className="h-5 w-5 text-blue-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Followed States</h2>
            <p className="text-sm text-gray-500">Select which states you want to monitor</p>
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {states.map((state) => (
            <button
              key={state.code}
              onClick={() => toggleState(state.code)}
              className={`p-4 rounded-lg border-2 text-left transition-colors ${
                followedStates.includes(state.code)
                  ? 'border-blue-600 bg-blue-50'
                  : 'border-gray-200 hover:border-gray-300'
              }`}
            >
              <div className="flex items-center justify-between">
                <span className="font-bold text-lg text-gray-900">{state.code}</span>
                {followedStates.includes(state.code) && (
                  <Check className="h-5 w-5 text-blue-600" />
                )}
              </div>
              <div className="text-sm text-gray-500 mt-1">{state.name}</div>
              <div className="text-xs text-gray-400 mt-1">{state.hearing_count} hearings</div>
            </button>
          ))}
        </div>

        {followedStates.length > 0 && (
          <p className="text-sm text-gray-500 mt-4">
            Monitoring {followedStates.length} state{followedStates.length !== 1 ? 's' : ''}: {followedStates.join(', ')}
          </p>
        )}
      </div>

      {/* Email Alerts */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="h-10 w-10 rounded-lg bg-orange-100 flex items-center justify-center">
            <Bell className="h-5 w-5 text-orange-600" />
          </div>
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Email Alerts</h2>
            <p className="text-sm text-gray-500">Configure how you receive updates</p>
          </div>
        </div>

        {/* Enable/Disable */}
        <div className="flex items-center justify-between py-4 border-b border-gray-100">
          <div className="flex items-center gap-3">
            <Mail className="h-5 w-5 text-gray-400" />
            <div>
              <div className="font-medium text-gray-900">Email notifications</div>
              <div className="text-sm text-gray-500">Receive email alerts for new hearings</div>
            </div>
          </div>
          <label className="relative inline-flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={emailAlerts}
              onChange={(e) => {
                setEmailAlerts(e.target.checked)
                setSaved(false)
              }}
              className="sr-only peer"
            />
            <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
          </label>
        </div>

        {/* Frequency */}
        <div className="py-4">
          <div className="font-medium text-gray-900 mb-3">Alert frequency</div>
          <div className="flex gap-3">
            {[
              { value: 'daily', label: 'Daily digest' },
              { value: 'weekly', label: 'Weekly summary' },
              { value: 'off', label: 'Off' },
            ].map((option) => (
              <button
                key={option.value}
                onClick={() => {
                  setAlertFrequency(option.value as any)
                  setSaved(false)
                }}
                disabled={!emailAlerts && option.value !== 'off'}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  alertFrequency === option.value
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200 disabled:opacity-50'
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Account Info */}
      {session?.user && (
        <div className="bg-white rounded-xl border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Account</h2>
          <div className="space-y-3 text-sm">
            <div className="flex justify-between py-2 border-b border-gray-100">
              <span className="text-gray-500">Email</span>
              <span className="text-gray-900">{session.user.email}</span>
            </div>
            <div className="flex justify-between py-2 border-b border-gray-100">
              <span className="text-gray-500">Name</span>
              <span className="text-gray-900">{session.user.name || '-'}</span>
            </div>
            <div className="flex justify-between py-2">
              <span className="text-gray-500">Role</span>
              <span className="px-2 py-0.5 bg-blue-100 text-blue-700 rounded text-xs font-medium">
                {(session.user as any).role === 'admin' ? 'Admin' : 'User'}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Save Button */}
      <div className="flex justify-end">
        <button
          onClick={handleSave}
          disabled={saving}
          className={`flex items-center gap-2 px-6 py-3 rounded-lg font-semibold transition-all ${
            saved
              ? 'bg-green-600 text-white'
              : 'bg-blue-600 text-white hover:bg-blue-700'
          } disabled:opacity-50`}
        >
          {saving ? (
            'Saving...'
          ) : saved ? (
            <>
              <Check className="h-5 w-5" />
              Saved
            </>
          ) : (
            <>
              <Save className="h-5 w-5" />
              Save Changes
            </>
          )}
        </button>
      </div>
    </div>
  )
}
