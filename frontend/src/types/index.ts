/** Where a document's Current Version stands against its expiry date (S7). */
export type ExpiryStatus = 'unexpired' | 'expiring_soon' | 'expired' | 'no_expiry_date'

export const EXPIRY_STATUS_LABELS: Record<ExpiryStatus, string> = {
  unexpired: 'Unexpired',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
  no_expiry_date: 'No expiry date',
}

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
  /** The vessel of the Assignment under way today; null means ashore. */
  current_vessel_id: number | null
  current_vessel_name: string | null
  created_at: string
  updated_at: string
}

export type SeafarerWrite = Pick<
  Seafarer,
  'first_name' | 'last_name' | 'date_of_birth' | 'nationality' | 'position_id'
>

/** Upcoming / under way / finished come from the dates; cancelled is stored. */
export type AssignmentState = 'upcoming' | 'under_way' | 'finished' | 'cancelled'

export const ASSIGNMENT_STATE_LABELS: Record<AssignmentState, string> = {
  upcoming: 'Upcoming',
  under_way: 'Under way',
  finished: 'Finished',
  cancelled: 'Cancelled',
}

/** A plan for a seafarer to serve on a vessel in a Position (S6). */
export interface Assignment {
  id: number
  seafarer_id: number
  seafarer_first_name: string
  seafarer_last_name: string
  vessel_id: number
  vessel_name: string
  position_id: number
  position_name: string
  /** Advisory: the Assignment's Position isn't the seafarer's held one. */
  position_differs: boolean
  /** ISO dates (YYYY-MM-DD), both days included. */
  start_date: string
  end_date: string
  state: AssignmentState
  cancelled_at: string | null
  cancel_reason: string | null
  created_at: string
  updated_at: string
}

/** PUT /api/assignments/{id}: the seafarer can't be changed. */
export type AssignmentEdit = Pick<Assignment, 'vessel_id' | 'position_id' | 'start_date' | 'end_date'>

export type AssignmentCreate = AssignmentEdit & Pick<Assignment, 'seafarer_id'>

/** A crewing officer linked to a vessel. A deactivated one's link is kept but ignored. */
export interface ResponsibleOfficer {
  id: string
  email: string
  full_name: string
  status: AccountStatus
}

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

/** A Version's key details: sent with an upload, or alone for a details-only Version. */
export interface VersionDetails {
  document_number: string
  issuing_authority: string
  /** ISO dates (YYYY-MM-DD); no expiry date for a type that doesn't expire. */
  issue_date: string
  expiry_date: string | null
}

/** One immutable snapshot of a document's file and key details. */
export interface Version extends VersionDetails {
  id: number
  /** 1 for the first upload, counting up. */
  number: number
  original_filename: string
  content_type: string
  uploaded_by: string
  uploaded_by_name: string
  uploaded_at: string
  is_current: boolean
  /** Set on a details-only Version: the earlier Version whose file it reuses. */
  file_from_version_number: number | null
}

/** One row of a seafarer's documents table. */
export interface DocumentSummary {
  id: number
  seafarer_id: number
  document_type_id: number
  document_type_name: string
  document_type_retired: boolean
  expires: boolean
  max_validity_months: number | null
  created_at: string
  version_count: number
  /** Null when every Version is rejected: the document counts as missing. */
  current_version: Pick<Version, 'id' | 'document_number' | 'issue_date' | 'expiry_date' | 'uploaded_at'> | null
  expiry_status: ExpiryStatus | null
}

/** GET /api/documents/{id}: the document with its full history, newest first. */
export interface DocumentDetail extends DocumentSummary {
  seafarer_first_name: string
  seafarer_last_name: string
  seafarer_inactive: boolean
  versions: Version[]
}

/** POST /api/versions/{id}/file-url */
export interface FileUrl {
  url: string
  expires_in: number
  filename: string
  content_type: string
}
