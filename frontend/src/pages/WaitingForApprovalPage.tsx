import { Clock, RefreshCw } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

/** All a pending Account sees until an administrator approves it (FR-01). */
export function WaitingForApprovalPage() {
  const { user, signOut, refreshAccount } = useAuth()

  return (
    <div className="flex min-h-screen items-center justify-center bg-navy-950 px-4">
      <main
        id="main-content"
        className="w-full max-w-md rounded-xl border border-navy-800 bg-navy-900 p-8 text-center shadow-2xl"
      >
        <Clock className="mx-auto mb-4 h-10 w-10 text-navy-300" aria-hidden="true" />
        <h1 className="text-xl font-semibold text-navy-50">Waiting for approval</h1>
        <p className="mt-2 text-sm text-navy-300">
          Your account {user?.email ? <strong>{user.email}</strong> : null} has been created. An
          administrator must approve it and give it a role before you can use the system.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <button
            type="button"
            onClick={() => void refreshAccount()}
            className="flex items-center gap-2 rounded-lg bg-navy-600 px-4 py-2 text-sm font-medium text-navy-50 hover:bg-navy-500 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Check again
          </button>
          <button
            type="button"
            onClick={() => void signOut()}
            className="rounded-lg bg-navy-800 px-4 py-2 text-sm font-medium text-navy-100 hover:bg-navy-700 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          >
            Sign out
          </button>
        </div>
      </main>
    </div>
  )
}
