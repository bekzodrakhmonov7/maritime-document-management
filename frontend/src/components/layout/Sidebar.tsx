import { NavLink } from 'react-router-dom'
import {
  Anchor,
  Briefcase,
  FileText,
  Home,
  Settings,
  Ship,
  UserCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/cn'
import { usePendingCount } from '../../hooks/useAccounts'
import type { UserRole } from '../../types'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  roles: UserRole[]
  badge?: 'pending-accounts'
}

interface NavGroup {
  label: string | null
  items: NavItem[]
}

// Built up slice by slice (see the build plan's Navigation table).
const NAV: NavGroup[] = [
  {
    label: null,
    items: [
      // Managers have no seafarer view; their Dashboard (totals only) comes in S11.
      { to: '/', label: 'Home', icon: Home, roles: ['manager'] },
      { to: '/seafarers', label: 'Seafarers', icon: Users, roles: ['administrator', 'crewing_officer'] },
      { to: '/vessels', label: 'Vessels', icon: Ship, roles: ['administrator', 'crewing_officer'] },
    ],
  },
  {
    label: 'Admin',
    items: [
      {
        to: '/admin/accounts',
        label: 'Accounts',
        icon: UserCheck,
        roles: ['administrator'],
        badge: 'pending-accounts',
      },
      { to: '/admin/document-types', label: 'Document Types', icon: FileText, roles: ['administrator'] },
      { to: '/admin/positions', label: 'Positions', icon: Briefcase, roles: ['administrator'] },
      { to: '/admin/settings', label: 'Settings', icon: Settings, roles: ['administrator'] },
    ],
  },
]

interface SidebarProps {
  role: UserRole | null
  isOpen: boolean
  onClose: () => void
}

export function Sidebar({ role, isOpen, onClose }: SidebarProps) {
  const isAdmin = role === 'administrator'
  const { data: pending } = usePendingCount(isAdmin)

  const groups = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => role !== null && item.roles.includes(role)),
  })).filter((group) => group.items.length > 0)

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-navy-950/60 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-64 flex-col border-r border-navy-800 bg-navy-900 transition-transform duration-200 lg:static lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-16 items-center gap-3 border-b border-navy-800 px-6">
          <Anchor className="h-6 w-6 text-navy-300" />
          <span className="text-sm font-semibold tracking-wide text-navy-100">Crew Monitor</span>
        </div>

        <nav className="flex-1 space-y-6 overflow-y-auto p-4" aria-label="Main navigation">
          {groups.map((group) => (
            <div key={group.label ?? 'main'} className="space-y-1">
              {group.label && (
                <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wider text-navy-500">
                  {group.label}
                </p>
              )}
              {group.items.map((item) => {
                const Icon = item.icon
                const count = item.badge === 'pending-accounts' ? (pending ?? 0) : 0
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                        isActive
                          ? 'bg-navy-700 text-navy-50'
                          : 'text-navy-300 hover:bg-navy-800 hover:text-navy-100',
                      )
                    }
                  >
                    <Icon className="h-5 w-5 shrink-0" />
                    <span className="flex-1">{item.label}</span>
                    {count > 0 && (
                      <span
                        className="rounded-full bg-status-expiring px-2 py-0.5 text-xs font-semibold text-navy-950"
                        aria-label={`${count} pending`}
                      >
                        {count}
                      </span>
                    )}
                  </NavLink>
                )
              })}
            </div>
          ))}
        </nav>

        <div className="border-t border-navy-800 p-4">
          <p className="text-xs text-navy-500">Crew Document Management</p>
        </div>
      </aside>
    </>
  )
}
