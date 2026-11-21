import { Navigate } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useAuth } from '../context/AuthContext'
import type { UserRole } from '../types'

interface RoleGateProps {
  children: ReactNode
  roles: UserRole[]
  redirectTo?: string
}

export function RoleGate({ children, roles, redirectTo = '/' }: RoleGateProps) {
  const { role, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-line-strong border-t-ink" />
      </div>
    )
  }

  if (!role || !roles.includes(role)) {
    return <Navigate to={redirectTo} replace />
  }

  return <>{children}</>
}
