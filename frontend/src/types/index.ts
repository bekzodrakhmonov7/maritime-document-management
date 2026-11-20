/** Where a document's Current Version stands against its expiry date (S7). */
export type ExpiryStatus = 'unexpired' | 'expiring_soon' | 'expired' | 'no_expiry_date' | 'expiry_not_stated'

export const EXPIRY_STATUS_LABELS: Record<ExpiryStatus, string> = {
  unexpired: 'Unexpired',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
  no_expiry_date: 'No expiry date',
  expiry_not_stated: 'Expiry not stated — check manually',
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

/** A required Document Type the seafarer has no Current Version of (S10). */
export interface MissingDocument {
  document_type_id: number
  name: string
  /** Set when the Document exists but every Version of it is rejected. */
  document_id: number | null
}

/** GET /api/seafarers/{id}: the record with its missing documents. Missing
 * documents use the Assignment under way, or the held Position when ashore. */
export interface SeafarerRecord extends Seafarer {
  missing_documents: MissingDocument[]
}

/** How one required document stands against an Assignment's dates (T3). */
export type CoverageClass =
  | 'missing'
  | 'runs_out_before_start'
  | 'runs_out_during'
  | 'expiry_not_stated'
  | 'covers_all'

export const COVERAGE_LABELS: Record<CoverageClass, string> = {
  missing: 'Missing',
  runs_out_before_start: 'Runs out before start',
  runs_out_during: 'Runs out during',
  expiry_not_stated: EXPIRY_STATUS_LABELS.expiry_not_stated,
  covers_all: 'Covers all',
}

export interface ReadinessEntry {
  document_type_id: number
  name: string
  document_id: number | null
  /** The Current Version's own expiry date. */
  expiry_date: string | null
  /** The Effective Expiry (FR-14): the own expiry date, or for an Endorsement the
   * earlier of it and its certificate's. Null with no certificate behind it. */
  effective_expiry: string | null
  /** The certificate's Document Type when its date caps this Endorsement. */
  capped_by: string | null
  /** An Endorsement with no certificate behind it: counts as expired. */
  certificate_missing: boolean
  coverage: CoverageClass
  /** The advisory renewal suggestion; null when it covers all. */
  suggestion: string | null
  review_state: ReviewState | null
  /** A badge only: Verified has no bucket and no suggestion. */
  verified: boolean
}

export type ReadinessBucket = 'before_joining' | 'renewable_at_sea' | 'expiry_not_stated' | 'not_reviewed' | 'covers_all'

/** GET /api/assignments/{id}/readiness (T4 variant B). Advice only: it approves
 * and blocks nothing, and gives no overall verdict. */
export interface Readiness {
  assignment: Assignment & { vessel_flag: string; held_position_name: string }
  state: 'upcoming' | 'under_way'
  /** Set when the Assignment's Position differs from the held one. */
  position_notice: string | null
  /** "Before joining", or "Act now" when under way. */
  before_joining_label: string
  counters: Record<Exclude<ReadinessBucket, 'covers_all'>, number>
  buckets: Record<ReadinessBucket, ReadinessEntry[]>
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
  /** Retention Periods in whole years, 1–10 (O3). */
  retention_replaced_version_years: number
  retention_inactive_seafarer_years: number
  retention_audit_record_years: number
  version: number
  updated_at: string
  /** What the latest scheduled run's retention clean-up removed; null before the first. */
  last_cleanup: LastCleanup | null
}

/** The latest retention clean-up (the last step of the scheduled daily check). */
export interface LastCleanup {
  local_date: string
  finished_at: string
  versions: number
  seafarers: number
  audit_records: number
}

/** PUT /api/settings: the values plus the version the editor started from. */
export type SettingsWrite = Omit<Settings, 'updated_at' | 'last_cleanup'>

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
  /** The form's tick that lets an expiring type take no date; checked, never stored (ADR-0006). */
  expiry_not_stated?: boolean
}

/** A Version's latest Review decides (S8). The Current Version is never rejected. */
export type ReviewState = 'not_reviewed' | 'accepted' | 'rejected'

export type ReviewDecision = 'accept' | 'reject'

/** A second staff member's accept or reject, with a comment. Never the uploader's. */
export interface Review {
  id: number
  decision: ReviewDecision
  comment: string
  reviewed_by: string
  reviewed_by_name: string
  reviewed_at: string
}

export type VerificationResult = 'confirmed' | 'not_confirmed'

/** A check with the issuing authority: sent as form fields with an optional proof file. */
export interface VerificationDetails {
  /** ISO date (YYYY-MM-DD), not after today. */
  checked_on: string
  source: string
  result: VerificationResult
  reference: string
}

export interface Verification extends VerificationDetails {
  id: number
  recorded_by: string
  recorded_by_name: string
  recorded_at: string
  /** Both null when no proof file was attached. */
  proof_original_filename: string | null
  proof_content_type: string | null
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
  review_state: ReviewState
  /** Newest first. */
  reviews: Review[]
  verifications: Verification[]
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
  current_version: Pick<
    Version,
    'id' | 'document_number' | 'issue_date' | 'expiry_date' | 'uploaded_at' | 'review_state'
  > | null
  /** Against the Effective Expiry. */
  expiry_status: ExpiryStatus | null
  /** The Effective Expiry (FR-14): the own expiry date, or for an Endorsement the
   * earlier of it and its certificate's. Null with no certificate behind it. */
  effective_expiry: string | null
  /** The certificate's Document Type when its date caps this Endorsement. */
  capped_by: string | null
  /** An Endorsement with no certificate behind it: counts as expired. */
  certificate_missing: boolean
  /** The certificate's Document Type, set for an Endorsement. */
  certificate_type_name: string | null
  /** The Current Version's latest Verification is confirmed. Never the same as Reviewed. */
  verified: boolean
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

/** The actions an Audit Record can have (app/audit.py), with their labels. */
export const AUDIT_ACTION_LABELS = {
  login_succeeded: 'Login succeeded',
  login_failed: 'Login failed',
  logout: 'Logout',
  password_reset: 'Password reset',
  access_refused: 'Access refused',
  account_approved: 'Account approved',
  account_role_changed: 'Account role changed',
  account_deactivated: 'Account deactivated',
  account_reactivated: 'Account reactivated',
  vessel_created: 'Vessel created',
  vessel_edited: 'Vessel edited',
  vessel_deactivated: 'Vessel deactivated',
  vessel_reactivated: 'Vessel reactivated',
  position_created: 'Position created',
  position_edited: 'Position edited',
  position_retired: 'Position retired',
  position_unretired: 'Position unretired',
  position_deleted: 'Position deleted',
  document_type_created: 'Document Type created',
  document_type_edited: 'Document Type edited',
  document_type_retired: 'Document Type retired',
  document_type_unretired: 'Document Type unretired',
  document_type_deleted: 'Document Type deleted',
  requirement_added: 'Requirement added',
  requirement_removed: 'Requirement removed',
  requirement_exception_created: 'Requirement exception created',
  requirement_exception_edited: 'Requirement exception edited',
  requirement_exception_deleted: 'Requirement exception deleted',
  seafarer_created: 'Seafarer created',
  seafarer_edited: 'Seafarer edited',
  seafarer_set_inactive: 'Seafarer set Inactive',
  seafarer_reactivated: 'Seafarer reactivated',
  assignment_created: 'Assignment created',
  assignment_edited: 'Assignment edited',
  assignment_cancelled: 'Assignment cancelled',
  responsible_officer_added: 'Responsible Officer added',
  responsible_officer_removed: 'Responsible Officer removed',
  version_uploaded: 'Version uploaded',
  upload_rejected: 'Upload rejected',
  file_url_issued: 'File URL issued',
  version_reviewed: 'Version reviewed',
  verification_recorded: 'Verification recorded',
  settings_changed: 'Settings changed',
  audit_searched: 'Audit Log searched',
  audit_exported: 'Audit Log exported',
  daily_check_run_manually: 'Daily check run manually',
  report_generated: 'Status Report generated',
  retention_removal: 'Retention removal',
} as const

export type AuditAction = keyof typeof AUDIT_ACTION_LABELS

export type AuditOutcome = 'succeeded' | 'refused'

/** One Audit Record (S13). */
export interface AuditRecord {
  id: number
  occurred_at: string
  actor_id: string | null
  actor_email: string | null
  actor_role: string | null
  action: string
  outcome: AuditOutcome
  target_type: string | null
  target_id: string | null
  seafarer_id: number | null
  /** The changed fields only. */
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  reason: string | null
  ip: string | null
  request_id: string | null
}

/** The Audit Log search; every filter given must match. */
export interface AuditFilters {
  date_from: string
  date_to: string
  actor_email: string
  actions: AuditAction[]
  seafarer_id: string
  target_type: string
  target_id: string
  outcome: AuditOutcome | ''
}

/** GET /api/audit: one page, newest first. */
export interface AuditPage {
  items: AuditRecord[]
  total: number
  page: number
  page_size: number
  /** The company time zone the timestamps are shown in. */
  time_zone: string
}

// --- Alerts and the daily check (FR-16) ---------------------------------------------

/** An open Alert: a document that reached an Alert Step for its current expiry date. */
export interface Alert {
  id: number
  document_id: number
  seafarer_id: number
  seafarer_name: string
  document_type_name: string
  /** Days before expiry. */
  step: number
  expiry_date: string
  /** Against today in the company time zone; negative once expired. */
  days_left: number
  raised_at: string
  awaiting_review: boolean
}

export interface DailyCheckResult {
  run_id: number
  local_date: string
  manual: boolean
  raised: number
  skipped: number
  /** Digests, one per recipient. */
  sent: number
  failed: number
}

// --- Dashboard (S11, FR-20, T10 variant C) ---

export type DashboardQueue =
  | 'missing'
  | 'expired'
  | 'expiring_soon'
  | 'expiry_not_stated'
  | 'waiting_for_review'
  | 'starting_soon'
  | 'in_order'

export const DASHBOARD_QUEUE_LABELS: Record<DashboardQueue, string> = {
  missing: 'Missing',
  expired: 'Expired',
  expiring_soon: 'Expiring soon',
  expiry_not_stated: EXPIRY_STATUS_LABELS.expiry_not_stated,
  waiting_for_review: 'Waiting for review',
  starting_soon: 'Starting soon',
  in_order: 'In order',
}

export type ActionHint = 'upload' | 'review' | 'open'

export interface DashboardSeafarer {
  id: number
  first_name: string
  last_name: string
  position_id: number
  position_name: string
  /** null: ashore today. */
  current_vessel_id: number | null
  current_vessel_name: string | null
  inactive: boolean
}

export interface QueueEntry {
  document_type_id: number
  document_type_name: string
  /** null for a missing type with no Document; set when every Version is rejected. */
  document_id: number | null
  /** The Current Version's own expiry date. */
  expiry_date: string | null
  /** The Effective Expiry (FR-14): the own expiry date, or for an Endorsement the
   * earlier of it and its certificate's. Null with no certificate behind it. */
  effective_expiry: string | null
  /** The certificate's Document Type when its date caps this Endorsement. */
  capped_by: string | null
  /** An Endorsement with no certificate behind it: counts as expired. */
  certificate_missing: boolean
  /** null: missing (no Current Version). */
  expiry_status: ExpiryStatus | null
  review_state: ReviewState | null
  /** The Current Version's uploader (FR-11: never offered its Review). */
  uploaded_by?: string | null
  action: ActionHint
}

export interface SeafarerGroup {
  seafarer: DashboardSeafarer
  entries: QueueEntry[]
}

export interface StartingSoonEntry {
  assignment_id: number
  seafarer: DashboardSeafarer
  vessel_id: number
  vessel_name: string
  position_id: number
  position_name: string
  start_date: string
  end_date: string
  counters: Record<Exclude<ReadinessBucket, 'covers_all'>, number>
}

/** GET /api/dashboard: administrators and crewing officers, within Scope.
 * Every queue's count, and one page of one queue (NFR-07). */
export interface Dashboard {
  today: string
  planning_horizon_days: number
  /** Entries per queue after the filters, for every queue whichever page is read. */
  counts: Record<DashboardQueue, number>
  queue: DashboardQueue
  offset: number
  limit: number
  /** Items in the whole queue: seafarer groups, or Assignments for starting soon. */
  total: number
  /** The page of a document queue, seafarers by name (empty for starting soon). */
  groups: SeafarerGroup[]
  /** The page of starting soon, by start date (empty otherwise). */
  assignments: StartingSoonEntry[]
}

export type TotalsColumn =
  | 'missing'
  | 'expired'
  | 'expiring_soon'
  | 'unexpired'
  | 'expiry_not_stated'
  | 'no_expiry_date'
export type Breakdown = 'vessel' | 'position' | 'document_type'

/** GET /api/dashboard/totals: counts only, no names. */
export interface FleetTotals {
  today: string
  totals: Record<TotalsColumn, number>
  breakdown: Breakdown
  rows: { id: number | null; name: string; counts: Record<TotalsColumn, number> }[]
}
