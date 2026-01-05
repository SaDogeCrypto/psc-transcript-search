'use client'

import Link from 'next/link'
import { Zap, Mail, CheckCircle } from 'lucide-react'

export default function SignupPage() {
  return (
    <div className="min-h-screen flex">
      {/* Left side - Content */}
      <div className="flex-1 flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div className="max-w-md w-full text-center">
          <Link href="/" className="inline-flex items-center gap-2 mb-8">
            <Zap className="h-8 w-8 text-blue-600" />
            <span className="text-xl font-bold text-gray-900">CanaryScope</span>
          </Link>

          <h1 className="text-2xl font-bold text-gray-900 mb-4">
            Get Started with CanaryScope
          </h1>

          <p className="text-gray-600 mb-8">
            We're currently in private beta. Contact us to get access to the platform.
          </p>

          <div className="bg-blue-50 rounded-xl p-6 mb-8 text-left">
            <h3 className="font-semibold text-gray-900 mb-4">What you'll get:</h3>
            <div className="space-y-3">
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <span className="text-gray-700">Full access to all features during pilot</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <span className="text-gray-700">Coverage across 6+ states</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <span className="text-gray-700">AI-powered hearing summaries</span>
              </div>
              <div className="flex items-start gap-3">
                <CheckCircle className="h-5 w-5 text-blue-600 flex-shrink-0 mt-0.5" />
                <span className="text-gray-700">Real-time email alerts</span>
              </div>
            </div>
          </div>

          <a
            href="mailto:hello@canaryscope.com?subject=CanaryScope Access Request"
            className="inline-flex items-center justify-center gap-2 w-full bg-blue-600 text-white py-3 rounded-lg font-semibold hover:bg-blue-700 transition-colors"
          >
            <Mail className="h-5 w-5" />
            Contact Us for Access
          </a>

          <p className="text-center mt-8 text-gray-600">
            Already have an account?{' '}
            <Link href="/login" className="text-blue-600 font-medium hover:underline">
              Sign in
            </Link>
          </p>
        </div>
      </div>

      {/* Right side - Decorative */}
      <div className="hidden lg:flex flex-1 bg-gradient-to-br from-blue-600 to-blue-800 items-center justify-center p-12">
        <div className="max-w-md text-white">
          <h2 className="text-3xl font-bold mb-6">
            Join the private beta
          </h2>
          <p className="text-blue-100 text-lg mb-8">
            We're working with a select group of utility professionals to refine CanaryScope before our public launch.
          </p>
          <div className="space-y-4">
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Early access pricing</div>
                <div className="text-blue-200 text-sm">Lock in founder rates</div>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Direct feedback channel</div>
                <div className="text-blue-200 text-sm">Shape the product roadmap</div>
              </div>
            </div>
            <div className="flex items-start gap-4">
              <CheckCircle className="h-6 w-6 flex-shrink-0 mt-0.5" />
              <div>
                <div className="font-medium">Priority support</div>
                <div className="text-blue-200 text-sm">White-glove onboarding</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
