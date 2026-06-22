import { Menu, LogOut } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'

interface TopBarProps {
  onMenuClick: () => void
}

export function TopBar({ onMenuClick }: TopBarProps) {
  const { user, role, signOut } = useAuth()

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-navy-800 bg-navy-900 px-4 lg:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-lg p-2 text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40 lg:hidden"
          aria-label="Toggle navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <h1 className="text-base font-semibold tracking-wide text-navy-50 lg:text-lg">
          Maritime Crew Monitor
        </h1>
      </div>

      <div className="flex items-center gap-3 lg:gap-4">
        {role && (
          <span className="rounded-full bg-navy-700 px-3 py-1 text-xs font-medium capitalize text-navy-100">
            {role.replace('_', ' ')}
          </span>
        )}

        <span className="hidden text-sm text-navy-300 sm:block" title={user?.email ?? ''}>
          {user?.email}
        </span>

        <button
          type="button"
          onClick={signOut}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-navy-300 transition-colors hover:bg-navy-800 hover:text-navy-100 focus:outline-none focus:ring-2 focus:ring-navy-400/40"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign Out</span>
        </button>
      </div>
    </header>
  )
}