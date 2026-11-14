import { Link } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { ROLE_LABELS } from '../types'

/** Landing page until the Seafarers list (S5) and the dashboard (S11) land. */
export function HomePage() {
  const { user, role } = useAuth()

  return (
    <div className="max-w-2xl space-y-3">
      <h2 className="text-2xl font-semibold text-navy-50">Welcome</h2>
      <p className="text-sm text-navy-300">
        You are signed in as <strong>{user?.email}</strong>
        {role ? ` (${ROLE_LABELS[role]})` : ''}.
      </p>
      {role === 'administrator' && (
        <p className="text-sm text-navy-300">
          New sign-ups wait for you on the{' '}
          <Link to="/admin/accounts" className="font-medium text-navy-100 underline">
            Accounts
          </Link>{' '}
          page.
        </p>
      )}
    </div>
  )
}
