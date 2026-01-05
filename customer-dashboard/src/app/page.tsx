import Link from 'next/link'
import {
  Zap,
  FileText,
  Search,
  Bell,
  ArrowRight,
  CheckCircle,
  Play,
  Building2,
  Gavel,
  TrendingUp,
  Clock
} from 'lucide-react'

const STATE_LOGOS = [
  { code: 'GA', name: 'Georgia PSC' },
  { code: 'FL', name: 'Florida PSC' },
  { code: 'TX', name: 'Texas PUC' },
  { code: 'CA', name: 'California PUC' },
  { code: 'AZ', name: 'Arizona CC' },
  { code: 'NC', name: 'North Carolina UC' },
]

const COVERAGE_MATRIX = [
  { state: 'Georgia', rateCase: true, irp: true, tariff: true, certificate: true },
  { state: 'Florida', rateCase: true, irp: true, tariff: true, certificate: true },
  { state: 'Texas', rateCase: true, irp: true, tariff: true, certificate: true },
  { state: 'California', rateCase: true, irp: true, tariff: true, certificate: true },
  { state: 'Arizona', rateCase: true, irp: true, tariff: true, certificate: true },
  { state: 'North Carolina', rateCase: true, irp: true, tariff: true, certificate: false },
]

const PRICING_TIERS = [
  {
    name: 'Starter',
    price: 150,
    description: 'For individual analysts',
    features: [
      '3 state coverage',
      'Daily email digests',
      'Transcript search',
      'AI summaries',
    ],
  },
  {
    name: 'Professional',
    price: 300,
    description: 'For teams & consultants',
    features: [
      '10 state coverage',
      'Real-time alerts',
      'Full transcript access',
      'Commissioner sentiment analysis',
      'API access',
    ],
    popular: true,
  },
  {
    name: 'Enterprise',
    price: 500,
    description: 'For utilities & large firms',
    features: [
      'All 50 states',
      'Custom alert rules',
      'Dedicated support',
      'Custom integrations',
      'Historical archive',
      'Bulk export',
    ],
  },
]

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-white">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-md border-b border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-2">
              <Zap className="h-8 w-8 text-blue-600" />
              <span className="text-xl font-bold text-gray-900">CanaryScope</span>
            </div>
            <div className="hidden md:flex items-center gap-8">
              <a href="#features" className="text-gray-600 hover:text-gray-900">Features</a>
              <a href="#coverage" className="text-gray-600 hover:text-gray-900">Coverage</a>
              <a href="#pricing" className="text-gray-600 hover:text-gray-900">Pricing</a>
            </div>
            <div className="flex items-center gap-4">
              <Link href="/login" className="text-gray-600 hover:text-gray-900">
                Sign in
              </Link>
              <Link
                href="/signup"
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition-colors"
              >
                Start free trial
              </Link>
            </div>
          </div>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto text-center">
          <div className="inline-flex items-center gap-2 bg-blue-50 text-blue-700 px-4 py-2 rounded-full text-sm font-medium mb-8">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-600"></span>
            </span>
            Monitoring 1,200+ hearings across 6 states
          </div>

          <h1 className="text-5xl md:text-6xl font-bold text-gray-900 mb-6 leading-tight">
            See regulatory decisions<br />
            <span className="text-blue-600">before they impact your portfolio</span>
          </h1>

          <p className="text-xl text-gray-600 mb-10 max-w-3xl mx-auto">
            AI-powered monitoring of public utility commission hearings. Get instant alerts on rate cases,
            IRPs, and docket updates. Search transcripts. Understand commissioner sentiment.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/signup"
              className="inline-flex items-center justify-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-blue-700 transition-colors"
            >
              Start 14-day free trial
              <ArrowRight className="h-5 w-5" />
            </Link>
            <Link
              href="/dashboard/hearings"
              className="inline-flex items-center justify-center gap-2 bg-gray-100 text-gray-900 px-8 py-4 rounded-xl text-lg font-semibold hover:bg-gray-200 transition-colors"
            >
              <Play className="h-5 w-5" />
              See demo
            </Link>
          </div>
        </div>
      </section>

      {/* State Logos */}
      <section className="py-12 bg-gray-50 border-y border-gray-100">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <p className="text-center text-sm text-gray-500 mb-8">
            MONITORING PUBLIC SERVICE COMMISSIONS IN
          </p>
          <div className="flex flex-wrap justify-center gap-8 md:gap-16">
            {STATE_LOGOS.map((state) => (
              <div key={state.code} className="flex items-center gap-2 text-gray-600">
                <Building2 className="h-5 w-5" />
                <span className="font-medium">{state.name}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* What We Monitor */}
      <section id="features" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="text-center mb-16">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              What we monitor
            </h2>
            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
              Real-time tracking of regulatory proceedings that affect utility valuations
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-8">
            <div className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-blue-200 hover:shadow-lg transition-all">
              <div className="bg-blue-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
                <TrendingUp className="h-6 w-6 text-blue-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Rate Cases</h3>
              <p className="text-gray-600 text-sm">
                Track revenue requirement requests, ROE testimony, and settlement negotiations
              </p>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-blue-200 hover:shadow-lg transition-all">
              <div className="bg-green-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
                <FileText className="h-6 w-6 text-green-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">IRPs & Resource Plans</h3>
              <p className="text-gray-600 text-sm">
                Monitor integrated resource plans, capacity additions, and generation mix decisions
              </p>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-blue-200 hover:shadow-lg transition-all">
              <div className="bg-purple-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
                <Gavel className="h-6 w-6 text-purple-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Docket Updates</h3>
              <p className="text-gray-600 text-sm">
                Get notified on new filings, orders, and schedule changes for active proceedings
              </p>
            </div>

            <div className="bg-white rounded-2xl p-6 border border-gray-200 hover:border-blue-200 hover:shadow-lg transition-all">
              <div className="bg-orange-100 w-12 h-12 rounded-xl flex items-center justify-center mb-4">
                <Bell className="h-6 w-6 text-orange-600" />
              </div>
              <h3 className="text-lg font-semibold text-gray-900 mb-2">Tariff Changes</h3>
              <p className="text-gray-600 text-sm">
                Track rate design changes, rider modifications, and special contract approvals
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Sample Alert */}
      <section className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-4xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Get alerts that matter
            </h2>
            <p className="text-lg text-gray-600">
              AI-generated summaries delivered when you need them
            </p>
          </div>

          <div className="bg-white rounded-2xl border border-gray-200 shadow-lg overflow-hidden">
            <div className="bg-gray-900 text-white px-6 py-4 flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Bell className="h-5 w-5 text-yellow-400" />
                <span className="font-medium">New CanaryScope Alert</span>
              </div>
              <span className="text-gray-400 text-sm">2 hours ago</span>
            </div>
            <div className="p-6">
              <div className="flex items-start gap-4 mb-4">
                <div className="bg-blue-100 text-blue-700 px-3 py-1 rounded-full text-sm font-medium">
                  GA PSC
                </div>
                <div className="bg-orange-100 text-orange-700 px-3 py-1 rounded-full text-sm font-medium">
                  Rate Case
                </div>
              </div>
              <h3 className="text-xl font-semibold text-gray-900 mb-3">
                Georgia Power 2024 Rate Case - Staff Testimony Filed
              </h3>
              <p className="text-gray-600 mb-4">
                PSC Staff recommends $450M revenue increase (vs. $890M requested). Key concerns raised
                about Vogtle cost recovery and grid modernization spending. Commissioner Echols questioned
                residential rate impact during hearing. <span className="text-blue-600 font-medium">Sentiment: Skeptical.</span>
              </p>
              <div className="flex items-center gap-4 text-sm text-gray-500">
                <span className="flex items-center gap-1">
                  <Clock className="h-4 w-4" />
                  Hearing: Jan 15, 2024
                </span>
                <span className="flex items-center gap-1">
                  <FileText className="h-4 w-4" />
                  Docket: 44280
                </span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Coverage Matrix */}
      <section id="coverage" className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-5xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Comprehensive coverage
            </h2>
            <p className="text-lg text-gray-600">
              Deep monitoring across proceeding types
            </p>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-4 px-4 font-semibold text-gray-900">State</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-900">Rate Cases</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-900">IRPs</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-900">Tariffs</th>
                  <th className="text-center py-4 px-4 font-semibold text-gray-900">Certificates</th>
                </tr>
              </thead>
              <tbody>
                {COVERAGE_MATRIX.map((row) => (
                  <tr key={row.state} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-4 px-4 font-medium text-gray-900">{row.state}</td>
                    <td className="text-center py-4 px-4">
                      {row.rateCase && <CheckCircle className="h-5 w-5 text-green-500 mx-auto" />}
                    </td>
                    <td className="text-center py-4 px-4">
                      {row.irp && <CheckCircle className="h-5 w-5 text-green-500 mx-auto" />}
                    </td>
                    <td className="text-center py-4 px-4">
                      {row.tariff && <CheckCircle className="h-5 w-5 text-green-500 mx-auto" />}
                    </td>
                    <td className="text-center py-4 px-4">
                      {row.certificate && <CheckCircle className="h-5 w-5 text-green-500 mx-auto" />}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className="text-center text-gray-500 mt-6 text-sm">
            More states coming soon. <Link href="/signup" className="text-blue-600 hover:underline">Request a state</Link>
          </p>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="py-20 px-4 sm:px-6 lg:px-8 bg-gray-50">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-12">
            <h2 className="text-3xl font-bold text-gray-900 mb-4">
              Simple, transparent pricing
            </h2>
            <p className="text-lg text-gray-600">
              Start with a 14-day free trial. No credit card required.
            </p>
          </div>

          <div className="grid md:grid-cols-3 gap-8">
            {PRICING_TIERS.map((tier) => (
              <div
                key={tier.name}
                className={`bg-white rounded-2xl p-8 border-2 ${
                  tier.popular ? 'border-blue-600 ring-4 ring-blue-100' : 'border-gray-200'
                } relative`}
              >
                {tier.popular && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2 bg-blue-600 text-white px-4 py-1 rounded-full text-sm font-medium">
                    Most Popular
                  </div>
                )}
                <h3 className="text-xl font-semibold text-gray-900 mb-2">{tier.name}</h3>
                <p className="text-gray-600 text-sm mb-4">{tier.description}</p>
                <div className="mb-6">
                  <span className="text-4xl font-bold text-gray-900">${tier.price}</span>
                  <span className="text-gray-600">/month</span>
                </div>
                <ul className="space-y-3 mb-8">
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-center gap-2 text-gray-600">
                      <CheckCircle className="h-5 w-5 text-green-500 flex-shrink-0" />
                      {feature}
                    </li>
                  ))}
                </ul>
                <Link
                  href="/signup"
                  className={`block text-center py-3 rounded-lg font-semibold transition-colors ${
                    tier.popular
                      ? 'bg-blue-600 text-white hover:bg-blue-700'
                      : 'bg-gray-100 text-gray-900 hover:bg-gray-200'
                  }`}
                >
                  Start free trial
                </Link>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="py-20 px-4 sm:px-6 lg:px-8">
        <div className="max-w-4xl mx-auto text-center">
          <h2 className="text-3xl font-bold text-gray-900 mb-4">
            Ready to get ahead of regulatory changes?
          </h2>
          <p className="text-lg text-gray-600 mb-8">
            Join utilities and investment firms using CanaryScope to monitor PSC proceedings.
          </p>
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 bg-blue-600 text-white px-8 py-4 rounded-xl text-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            Start your free trial
            <ArrowRight className="h-5 w-5" />
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-4 sm:px-6 lg:px-8 border-t border-gray-200">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-4">
          <div className="flex items-center gap-2">
            <Zap className="h-6 w-6 text-blue-600" />
            <span className="font-semibold text-gray-900">CanaryScope</span>
          </div>
          <p className="text-gray-500 text-sm">
            &copy; 2025 CanaryScope. All rights reserved.
          </p>
          <div className="flex gap-6 text-sm text-gray-600">
            <a href="#" className="hover:text-gray-900">Privacy</a>
            <a href="#" className="hover:text-gray-900">Terms</a>
            <a href="#" className="hover:text-gray-900">Contact</a>
          </div>
        </div>
      </footer>
    </div>
  )
}
