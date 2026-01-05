'use client'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useSession } from 'next-auth/react'
import Link from 'next/link'
import { Shield, ArrowLeft } from 'lucide-react'
import './admin.css'

export default function AdminLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const router = useRouter()
  const { data: session, status } = useSession()
  const [authorized, setAuthorized] = useState(false)

  useEffect(() => {
    if (status === 'loading') return

    if (status === 'unauthenticated') {
      router.push('/login?callbackUrl=/admin')
      return
    }

    // Check if user has admin role
    const role = (session?.user as any)?.role
    if (role === 'admin') {
      setAuthorized(true)
    } else {
      // Not an admin - redirect to dashboard
      router.push('/dashboard')
    }
  }, [status, session, router])

  if (status === 'loading') {
    return (
      <div className="admin-loading">
        <div className="spinner" />
        <p>Loading...</p>
      </div>
    )
  }

  if (!authorized) {
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
