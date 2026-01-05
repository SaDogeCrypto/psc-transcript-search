'use client'

import { useState, useEffect } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { Zap, Mail, Lock, User, Building2, ArrowRight, AlertCircle, CheckCircle } from 'lucide-react'
import { supabase } from '@/lib/supabase'
import { getStates, type State } from '@/lib/api'

export default function SignupPage() {
  const router = useRouter()
  const [step, setStep] = useState(1)
  const [states, setStates] = useState<State[]>([])

  // Step 1: Account info
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [company, setCompany] = useState('')

  // Step 2: Select states
  const [selectedStates, setSelectedStates] = useState<string[]>([])

  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    getStates().then(setStates).catch(console.error)
  }, [])

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault()

    if (step === 1) {
      // Validate and move to step 2
      if (!email || !password || !name) {
        setError('Please fill in all required fields')
        return
      }
      if (password.length < 8) {
        setError('Password must be at least 8 characters')
        return
      }
      setError(null)
      setStep(2)
      return
    }

    // Step 2: Create account
    setLoading(true)
    setError(null)

    try {
      const { data: authData, error: authError } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: {
            name,
            company,
          },
        },
      })

      if (authError) throw authError

      // Create user preferences with selected states
      if (authData.user) {
        await supabase.from('user_preferences').insert({
          id: authData.user.id,
          followed_states: selectedStates,
          alert_frequency: 'daily',
          email_alerts: true,
        })
      }

      router.push('/dashboard')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create account')
    } finally {
      setLoading(false)
    }
  }

  const toggleState = (code: string) => {
    setSelectedStates((prev) =>
      prev.includes(code) ? prev.filter((s) => s !== code) : [...prev, code]
    )
  }

  return (
    <div className="min-h-screen flex">
      {/* Left side - Form */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full">
          <div className="text-center mb-8">
            <Link href="/" className="inline-flex items-center gap-2 mb-8">
              <Zap className="h-8 w-8 text-blue-600" />
              <span className="text-xl font-bold text-gray-900">CanaryScope</span>
            </Link>
            <h1 className="text-2xl font-bold text-gray-900">Start your free trial</h1>
            <p className="text-gray-600 mt-2">14 days free. No credit card required.</p>
          </div>

          {/* Progress Steps */}
          <div className="flex items-center justify-center gap-4 mb-8">
            <div className={`flex items-center gap-2 ${step >= 1 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step >= 1 ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}>
                {step > 1 ? <CheckCircle className="h-5 w-5" /> : '1'}
              </div>
              <span className="text-sm font-medium">Account</span>
            </div>
            <div className="w-12 h-0.5 bg-gray-200" />
            <div className={`flex items-center gap-2 ${step >= 2 ? 'text-blue-600' : 'text-gray-400'}`}>
              <div className={`w-8 h-8 rounded-full flex items-center justify-center ${step >= 2 ? 'bg-blue-600 text-white' : 'bg-gray-200'}`}>
                2
              </div>
              <span className="text-sm font-medium">States</span>
            </div>
          </div>

          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3">
              <AlertCircle className="h-5 w-5 text-red-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-700">{error}</p>
            </div>
          )}

          <form onSubmit={handleSignup}>
            {step === 1 && (
              <div className="space-y-5">
                <div>
                  <label htmlFor="name" className="block text-sm font-medium text-gray-700 mb-2">
                    Full name
                  </label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                      id="name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      required
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder="John Smith"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="company" className="block text-sm font-medium text-gray-700 mb-2">
                    Company <span className="text-gray-400">(optional)</span>
                  </label>
                  <div className="relative">
                    <Building2 className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                      id="company"
                      type="text"
                      value={company}
                      onChange={(e) => setCompany(e.target.value)}
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder="NextEra Energy"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                    Work email
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder="john@company.com"
                    />
                  </div>
                </div>

                <div>
                  <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-2">
                    Password
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
                    <input
                      id="password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      required
                      minLength={8}
                      className="w-full pl-10 pr-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none"
                      placeholder="At least 8 characters"
                    />
                  </div>
                </div>

                <button
                  type="submit"
                  className="w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors flex items-center justify-center gap-2"
                >
                  Continue
                  <ArrowRight className="h-5 w-5" />
                </button>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-5">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-3">
                    Select states to monitor
                  </label>
                  <p className="text-sm text-gray-500 mb-4">
                    Choose the states you want to track. You can change this later.
                  </p>
                  <div className="grid grid-cols-2 gap-3">
                    {states.map((state) => (
                      <button
                        key={state.code}
                        type="button"
                        onClick={() => toggleState(state.code)}
                        className={`p-4 rounded-lg border-2 text-left transition-colors ${
                          selectedStates.includes(state.code)
                            ? 'border-blue-600 bg-blue-50'
                            : 'border-gray-200 hover:border-gray-300'
                        }`}
                      >
                        <div className="font-medium text-gray-900">{state.code}</div>
                        <div className="text-sm text-gray-500">{state.name}</div>
                        <div className="text-xs text-gray-400 mt-1">
                          {state.hearing_count} hearings
                        </div>
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex gap-3">
                  <button
                    type="button"
                    onClick={() => setStep(1)}
                    className="flex-1 bg-gray-100 text-gray-900 py-3 rounded-lg font-semibold hover:bg-gray-200 transition-colors"
                  >
                    Back
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="flex-1 bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
                  >
                    {loading ? 'Creating account...' : 'Create account'}
                  </button>
                </div>
              </div>
            )}
          </form>

          <p className="text-center mt-8 text-gray-600">
            Already have an account?{' '}
            <Link href="/login" className="text-blue-600 font-medium hover:underline">
              Sign in
            </Link>
          </p>

          <p className="text-center mt-6 text-xs text-gray-400">
            By creating an account, you agree to our{' '}
            <a href="#" className="underline">Terms of Service</a> and{' '}
            <a href="#" className="underline">Privacy Policy</a>.
          </p>
        </div>
      </div>

      {/* Right side - Decorative */}
      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-blue-600 to-blue-800 items-center justify-center p-12">
        <div className="max-w-md text-white">
          <h2 className="text-3xl font-bold mb-6">
            What you get with your trial
          </h2>
          <div className="space-y-4">
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Full access to all features</div>
                <div className="text-blue-200 text-sm">Search, alerts, transcripts, and analysis</div>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Coverage across 6 states</div>
                <div className="text-blue-200 text-sm">GA, FL, TX, CA, AZ, NC and growing</div>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Historical archive</div>
                <div className="text-blue-200 text-sm">Access 1,200+ past hearings and transcripts</div>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">No credit card required</div>
                <div className="text-blue-200 text-sm">Start exploring immediately</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
