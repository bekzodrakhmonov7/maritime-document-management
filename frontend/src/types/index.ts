export type DocumentStatus =
  | 'valid'
  | 'expiring_soon'
  | 'expired'
  | 'pending'
  | 'verified'
  | 'rejected'

export type AccountStatus = 'pending' | 'active' | 'deactivated'

export type UserRole = 'administrator' | 'crewing_officer' | 'manager'

export const ROLE_LABELS: Record<UserRole, string> = {
  administrator: 'Administrator',
  crewing_officer: 'Crewing Officer',
  manager: 'Manager',
}

/** GET /api/me */
export interface Me {
  id: string
  email: string
  full_name: string
  status: AccountStatus
  role: UserRole | null
}

/** An Account as administrators see it on the Accounts page. */
export interface Account extends Me {
  status_reason: string | null
  status_changed_at: string | null
  created_at: string
}
