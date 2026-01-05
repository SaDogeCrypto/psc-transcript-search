'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { supabase } from '@/lib/supabase'
import { Shield, ArrowLeft } from 'lucide-react'
import './admin.css'

// Admin email whitelist - add admin emails here
const ADMIN_EMAILS = [
  'admin@canaryscope.com',
  'ronan@canaryscope.com',
]

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const [loading, setLoading] = useState(true)
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    async function checkAdmin() {
      const { data: { session } } = await supabase.auth.getSession()

      if (!session) {
        router.push('/login?redirect=/admin')
        return
      }

      const userEmail = session.user.email?.toLowerCase()
      if (userEmail && ADMIN_EMAILS.includes(userEmail)) {
        setIsAdmin(true)
      } else {
        // Not an admin - redirect to dashboard
        router.push('/dashboard')
        return
      }

      setLoading(false)
    }

    checkAdmin()

    const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
      if (event === 'SIGNED_OUT') {
        router.push('/login')
      }
    })

    return () => subscription.unsubscribe()
  }, [router])

  if (loading) {
    return (
      <div className="admin-loading">
        <div className="spinner" />
        <p>Verifying admin access...</p>
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="admin-denied">
        <Shield className="h-12 w-12 text-red-500" />
        <h2>Access Denied</h2>
        <p>You don't have permission to access the admin panel.</p>
        <Link href="/dashboard" className="btn btn-primary">
          <ArrowLeft className="h-4 w-4" />
          Back to Dashboard
        </Link>
      </div>
    )
  }

  return <>{children}</>
}
