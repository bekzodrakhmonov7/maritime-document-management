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

/** A ship in the fleet (S3). Vessels are deactivated, never deleted. */
export interface Vessel {
  id: number
  name: string
  imo_number: string
  /** ISO 3166-1 alpha-2 country code. */
  flag: string
  active: boolean
  created_at: string
  updated_at: string
}

export type VesselWrite = Pick<Vessel, 'name' | 'imo_number' | 'flag'>

/** A managed Position. A retired one disappears from pickers. */
export interface Position {
  id: number
  name: string
  retired: boolean
  created_at: string
  updated_at: string
}

export type PositionWrite = Pick<Position, 'name'>

/** A Document Type and its rules. `depends_on_id` set makes it an Endorsement. */
export interface DocumentType {
  id: number
  name: string
  expires: boolean
  max_validity_months: number | null
  renewable_at_sea: boolean
  depends_on_id: number | null
  retired: boolean
  created_at: string
  updated_at: string
}

export type DocumentTypeWrite = Pick<
  DocumentType,
  'name' | 'expires' | 'max_validity_months' | 'renewable_at_sea' | 'depends_on_id'
>

/** A Seafarer's record (S5). Set Inactive instead of being deleted. */
export interface Seafarer {
  id: number
  first_name: string
  last_name: string
  /** ISO date (YYYY-MM-DD). */
  date_of_birth: string | null
  /** ISO 3166-1 alpha-2 country code. */
  nationality: string | null
  /** The held Position, from the managed list. */
  position_id: number
  position_name: string
  position_retired: boolean
  /** Set while the seafarer is Inactive. */
  inactive_since: string | null
  inactive_reason: string | null
  created_at: string
  updated_at: string
}

export type SeafarerWrite = Pick<
  Seafarer,
  'first_name' | 'last_name' | 'date_of_birth' | 'nationality' | 'position_id'
>
