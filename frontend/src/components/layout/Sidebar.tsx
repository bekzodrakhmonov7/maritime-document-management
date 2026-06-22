import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  Ship,
  Users,
  FileText,
  Bell,
  BarChart3,
  Settings,
  Anchor,
} from 'lucide-react'
import { cn } from '../../lib/cn'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutDashboard
  adminOnly?: boolean
}

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/vessels', label: 'Vessels', icon: Ship },
  { to: '/seafarers', label: 'Seafarers', icon: Users },
  { to: '/documents', label: 'Documents', icon: FileText },
  { to: '/alerts', label: 'Alerts', icon: Bell },
  { to: '/reports', label: 'Reports', icon: BarChart3 },
  { to: '/admin/config', label: 'Admin Config', icon: Settings, adminOnly: true },
]

interface SidebarProps {
  role: string | null
  isOpen: boolean
  onClose: () => void
}

export function Sidebar({ role, isOpen, onClose }: SidebarProps) {
  const isAdmin = role === 'administrator'

  const visibleItems = NAV_ITEMS.filter((item) => !item.adminOnly || isAdmin)

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
          <span className="text-sm font-semibold tracking-wide text-navy-100">
            Crew Monitor
          </span>
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-4" aria-label="Main navigation">
          {visibleItems.map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
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
                {item.label}
              </NavLink>
            )
          })}
        </nav>

        <div className="border-t border-navy-800 p-4">
          <p className="text-xs text-navy-500">
            Maritime Crew Document
            <br />
            Expiry Monitoring System
          </p>
        </div>
      </aside>
    </>
  )
}