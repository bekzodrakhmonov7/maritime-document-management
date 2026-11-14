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

/** GET /api/settings: the one Settings row (S9). */
export interface Settings {
  /** Days before expiry, largest first; 0 (the expiry day) is always there. */
  alert_steps: number[]
  planning_horizon_days: number
  max_file_size_mb: number
  max_pdf_pages: number
  /** IANA time zone, e.g. Europe/Malta. */
  time_zone: string
  /** "HH:MM" in the company time zone, on a 15-minute step. */
  daily_check_time: string
  version: number
  updated_at: string
}

/** PUT /api/settings: the values plus the version the editor started from. */
export type SettingsWrite = Omit<Settings, 'updated_at'>

/** GET /api/requirements: one set cell of the Position Requirement matrix (S4). */
export interface MatrixCell {
  position_id: number
  document_type_id: number
}

export type ExceptionEffect = 'add' | 'remove'

/** An add/remove of one Document Type for one vessel or one flag (exactly one). */
export interface RequirementException {
  id: number
  vessel_id: number | null
  vessel_name: string | null
  flag: string | null
  /** null: every Position. */
  position_id: number | null
  position_name: string | null
  document_type_id: number
  document_type_name: string
  effect: ExceptionEffect
  reason: string
  created_at: string
  updated_at: string
}

export type RequirementExceptionWrite = Pick<
  RequirementException,
  'vessel_id' | 'flag' | 'position_id' | 'document_type_id' | 'effect' | 'reason'
>

/** GET /api/requirements/evaluate: the required set for (Position, Vessel or none). */
export interface RequirementEvaluation {
  position_id: number
  vessel: { id: number; name: string; flag: string } | null
  /** `exception_id` is set when an exception, not the matrix, makes it required. */
  required: { id: number; name: string; exception_id: number | null }[]
  /** The exceptions that decide a type for this pair (the most specific one wins). */
  applied_exceptions: RequirementException[]
}
