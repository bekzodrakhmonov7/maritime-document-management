import { Navigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ROLE_LABELS } from '../types'

/** The landing page. Administrators and crewing officers land on the Seafarers
 * list; managers see this page until their Dashboard (S11) lands. */
export function HomePage() {
  const { user, role } = useAuth()

  if (role === 'administrator' || role === 'crewing_officer') {
    return <Navigate to="/seafarers" replace />
  }

  return (
    <div className="max-w-2xl space-y-3">
      <h2 className="text-2xl font-semibold text-navy-50">Welcome</h2>
      <p className="text-sm text-navy-300">
        You are signed in as <strong>{user?.email}</strong>
        {role ? ` (${ROLE_LABELS[role]})` : ''}.
      </p>
      <p className="text-sm text-navy-300">Fleet totals arrive with the Dashboard.</p>
    </div>
  )
}
