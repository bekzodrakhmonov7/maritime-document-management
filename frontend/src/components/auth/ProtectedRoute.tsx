import { Navigate } from 'react-router-dom'
import { AlertCircle } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { WaitingForApprovalPage } from '../../pages/WaitingForApprovalPage'
import type { ReactNode } from 'react'

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading, status, signOut } = useAuth()

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-navy-400 border-t-navy-50" />
      </div>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace />
  }

  // FR-01: a pending account sees only the waiting page.
  if (status === 'pending') {
    return <WaitingForApprovalPage />
  }

  if (status !== 'active') {
    return (
      <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4">
        <div className="w-full max-w-md rounded-xl border border-navy-800 bg-navy-900 p-8 text-center">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-status-expired" aria-hidden="true" />
          <h1 className="text-xl font-semibold text-navy-50">Your account can't be loaded</h1>
          <p className="mt-2 text-sm text-navy-300">
            The server didn't recognise this sign-in. Try again later or sign out.
          </p>
          <button
            type="button"
            onClick={() => void signOut()}
            className="mt-6 rounded-lg bg-navy-700 px-4 py-2 text-sm font-medium text-navy-50 hover:bg-navy-600 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            Sign out
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
