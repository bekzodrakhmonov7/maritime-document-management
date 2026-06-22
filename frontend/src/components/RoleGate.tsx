import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../context/AuthContext'

interface RoleGateProps {
  children: ReactNode
  roles: string[]
  redirectTo?: string
}

export function RoleGate({ children, roles, redirectTo = '/dashboard' }: RoleGateProps) {
  const { role, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-navy-400 border-t-navy-50" />
      </div>
    )
  }

  if (!role || !roles.includes(role)) {
    return <Navigate to={redirectTo} replace />
  }

  return <>{children}</>
}
