export type DocumentStatus =
  | 'valid'
  | 'expiring_soon'
  | 'expired'
  | 'pending'
  | 'verified'
  | 'rejected'

export type UserRole = 'administrator' | 'crewing_officer'

export interface Seafarer {
  seafarer_id: number
  vessel_id: number
  first_name: string
  last_name: string
  rank: string
  vessel_name: string
}

export interface DocumentRecord {
  document_id: number
  seafarer_id: number
  doc_type_id: number
  document_number: string
  issue_date: string
  expiry_date: string
  status: DocumentStatus
  file_path: string
  uploaded_by: string | null
  created_at: string | null
  signed_url: string | null
}

export interface DocType {
  doc_type_id: number
  type_name: string
  is_mandatory: boolean
}

export interface SeafarerQueryParams {
  vessel_id?: number
  rank?: string
  cursor?: number
  limit?: number
}

export interface DocumentUploadInput {
  doc_type_id: number
  seafarer_id: number
  document_number: string
  issue_date: string
  expiry_date: string
  file: File
}

export interface DocumentVerifyInput {
  status: 'verified' | 'rejected'
}

export interface Alert {
  alert_id: number
  document_id: number
  alert_threshold_days: number
  generated_at: string
  is_resolved: boolean
  document_number: string
  expiry_date: string
  document_status: DocumentStatus
  document_type: string
  seafarer_name: string
}

export interface ThresholdConfig {
  days_90: number
  days_60: number
  days_30: number
}

export interface ScanSummary {
  date: string
  transitioned: number
  alerts_generated: number
  emails_sent: number
  emails_failed: number
}

export interface Vessel {
  vessel_id: number
  vessel_name: string
  imo_number: string
}

export interface VesselCreateInput {
  vessel_name: string
  imo_number: string
}

export interface VesselUpdateInput {
  vessel_name?: string
  imo_number?: string
}

export interface SeafarerCreateInput {
  vessel_id: number
  first_name: string
  last_name: string
  rank: string
}

export interface SeafarerUpdateInput {
  vessel_id?: number
  first_name?: string
  last_name?: string
  rank?: string
}

export interface MissingMandatoryDoc {
  seafarer_id: number
  seafarer_name: string
  rank: string
  vessel_name: string
  doc_type_id: number
  doc_type_name: string
}

export interface FleetVesselSummary {
  vessel_id: number
  vessel_name: string
  total_seafarers: number
  total_documents: number
  valid: number
  expiring_soon: number
  expired: number
  missing_mandatory: number
  compliance_percentage: number
}

export interface FleetSummary {
  fleet_total_seafarers: number
  fleet_total_documents: number
  fleet_valid: number
  fleet_expiring_soon: number
  fleet_expired: number
  fleet_missing_mandatory: number
  fleet_compliance_percentage: number
  vessels: FleetVesselSummary[]
}
