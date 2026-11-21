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
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-line-strong border-t-ink" />
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
      <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
        <div className="w-full max-w-md rounded-md border border-line bg-canvas p-8 text-center">
          <AlertCircle className="mx-auto mb-4 h-10 w-10 text-danger" aria-hidden="true" />
          <h1 className="text-xl font-medium text-ink">Your account can't be loaded</h1>
          <p className="mt-2 text-sm text-ink-muted">
            The server didn't recognise this sign-in. Try again later or sign out.
          </p>
          <button
            type="button"
            onClick={() => void signOut()}
            className="mt-6 h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium text-ink hover:bg-surface-active focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            Sign out
          </button>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
