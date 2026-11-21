import { NavLink } from 'react-router-dom'
import {
  Anchor,
  Bell,
  Briefcase,
  FileText,
  History,
  LayoutDashboard,
  ListChecks,
  Settings,
  Ship,
  UserCheck,
  Users,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '../../lib/cn'
import { usePendingCount } from '../../hooks/useAccounts'
import { useAlertCount } from '../../hooks/useAlerts'
import type { UserRole } from '../../types'

interface NavItem {
  to: string
  label: string
  icon: LucideIcon
  roles: UserRole[]
  badge?: 'pending-accounts' | 'open-alerts'
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
      // Managers see the Dashboard only, as fleet totals.
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, roles: ['administrator', 'crewing_officer', 'manager'] },
      { to: '/seafarers', label: 'Seafarers', icon: Users, roles: ['administrator', 'crewing_officer'] },
      {
        to: '/alerts',
        label: 'Alerts',
        icon: Bell,
        roles: ['administrator', 'crewing_officer'],
        badge: 'open-alerts',
      },
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
      { to: '/admin/requirements', label: 'Requirements', icon: ListChecks, roles: ['administrator'] },
      { to: '/admin/settings', label: 'Settings', icon: Settings, roles: ['administrator'] },
      { to: '/admin/audit', label: 'Audit Log', icon: History, roles: ['administrator'] },
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
  const { data: openAlerts } = useAlertCount(isAdmin || role === 'crewing_officer')
  const badges = { 'pending-accounts': pending ?? 0, 'open-alerts': openAlerts ?? 0 }

  const groups = NAV.map((group) => ({
    ...group,
    items: group.items.filter((item) => role !== null && item.roles.includes(role)),
  })).filter((group) => group.items.length > 0)

  return (
    <>
      {isOpen && (
        <div
          className="fixed inset-0 z-30 bg-ink/20 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-40 flex w-58 flex-col border-r border-line bg-surface max-lg:transition-transform max-lg:duration-200 lg:static lg:translate-x-0',
          isOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="flex h-14 items-center gap-2 border-b border-line px-4">
          <Anchor className="h-4 w-4 text-ink-muted" />
          <span className="text-sm font-medium text-ink">Crew Monitor</span>
        </div>

        <nav className="flex-1 space-y-4 overflow-y-auto px-2 py-4" aria-label="Main navigation">
          {groups.map((group) => (
            <div key={group.label ?? 'main'} className="space-y-0.5">
              {group.label && (
                <p className="px-3 pb-1 text-xs text-ink-faint">
                  {group.label}
                </p>
              )}
              {group.items.map((item) => {
                const Icon = item.icon
                const count = item.badge ? badges[item.badge] : 0
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.to === '/'}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        'group flex h-8 items-center gap-2 rounded-md px-3 text-sm transition-colors',
                        isActive
                          ? 'bg-accent-soft font-medium text-ink'
                          : 'text-ink-muted hover:bg-surface-active hover:text-ink',
                      )
                    }
                  >
                    <Icon className="h-4 w-4 shrink-0 text-ink-faint group-aria-[current=page]:text-accent" />
                    <span className="flex-1">{item.label}</span>
                    {count > 0 && (
                      <span
                        className="text-xs font-medium text-warning"
                        aria-label={item.badge === 'open-alerts' ? `${count} open` : `${count} pending`}
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

        <div className="p-4">
          <p className="text-xs text-ink-faint">Crew Document Management</p>
        </div>
      </aside>
    </>
  )
}
