import { Menu, LogOut } from 'lucide-react'
import { useAuth } from '../../context/AuthContext'
import { ROLE_LABELS } from '../../types'

interface TopBarProps {
  onMenuClick: () => void
}

export function TopBar({ onMenuClick }: TopBarProps) {
  const { user, role, signOut } = useAuth()

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-b border-line bg-canvas px-4 lg:px-8">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-md p-2 text-ink-muted transition-colors hover:bg-surface-active hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40 lg:hidden"
          aria-label="Toggle navigation menu"
        >
          <Menu className="h-4 w-4" />
        </button>

        <h1 className="text-sm font-medium text-ink">
          Maritime Crew Monitor
        </h1>
      </div>

      <div className="flex items-center gap-3 lg:gap-4">
        {role && (
          <span className="text-xs text-ink-faint">
            {ROLE_LABELS[role]}
          </span>
        )}

        <span className="hidden text-xs text-ink-faint sm:block" title={user?.email ?? ''}>
          {user?.email}
        </span>

        <button
          type="button"
          onClick={signOut}
          className="flex h-8 items-center gap-2 rounded-md px-3 text-sm text-ink-muted transition-colors hover:bg-surface-active hover:text-ink focus:outline-none focus:ring-2 focus:ring-accent/40"
          aria-label="Sign out"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Sign out</span>
        </button>
      </div>
    </header>
  )
}