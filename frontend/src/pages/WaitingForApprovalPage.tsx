import { Clock, RefreshCw } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

/** All a pending Account sees until an administrator approves it (FR-01). */
export function WaitingForApprovalPage() {
  const { user, signOut, refreshAccount } = useAuth()

  return (
    <div className="flex min-h-screen items-center justify-center bg-canvas px-4">
      <main
        id="main-content"
        className="w-full max-w-md rounded-md border border-line bg-canvas p-8 text-center"
      >
        <Clock className="mx-auto mb-4 h-10 w-10 text-ink-muted" aria-hidden="true" />
        <h1 className="text-xl font-medium text-ink">Waiting for approval</h1>
        <p className="mt-2 text-sm text-ink-muted">
          Your account {user?.email ? <strong>{user.email}</strong> : null} has been created. An
          administrator must approve it and give it a role before you can use the system.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => void refreshAccount()}
            className="flex items-center gap-2 rounded-md bg-accent px-4 py-2 text-sm font-medium text-on-accent hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Check again
          </button>
          <button
            type="button"
            onClick={() => void signOut()}
            className="h-8 shrink-0 whitespace-nowrap rounded-md border border-line-strong bg-canvas px-3 text-sm font-medium text-ink hover:bg-surface-active focus:outline-none focus:ring-2 focus:ring-accent/40"
          >
            Sign out
          </button>
        </div>
      </main>
    </div>
  )
}
