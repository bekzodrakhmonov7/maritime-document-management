# Implementation Plan: Maritime Crew Document Expiry Monitoring System

## Phase 1: Database Setup & Schema Relations (PostgreSQL / Supabase)

- [x] Initialize the Supabase project and PostgreSQL database instance.
- [x] Create the USER table with a foreign key linking to Supabase's native auth.users table (UserID UUID primary key).
- [x] Include the FullName and Role (Administrator vs Crewing Officer) columns in the USER table.
- [x] Implement the VESSEL table (VesselID, VesselName, IMONumber).
- [x] Implement the SEAFARER table linked to a VesselID with fields for FirstName, LastName, and Rank.
- [x] Create the DOCUMENT_TYPE lookup table (DocTypeID, TypeName, IsMandatory).
- [x] Create the primary DOCUMENT table (DocumentID, SeafarerID, DocTypeID, DocumentNumber, IssueDate, ExpiryDate, Status, FilePath).
- [x] Create the ALERT table tracking AlertThreshold (e.g., 90, 60, 30 days), GeneratedAt, and IsResolved.

## Phase 2: Authentication & Role-Based Access Control (Supabase Auth + FastAPI)

- [x] Create the core FastAPI application infrastructure with secure CORS configurations.
- [x] Implement a FastAPI dependency wrapper that decodes and validates incoming Supabase JWTs using the Supabase JWT Secret.
- [x] Build database trigger functions in Supabase to automatically insert a row into the public USER table whenever a new account is created in auth.users.
- [x] Enforce Role-Based Access Control (RBAC) layers restricting configuration panels to Administrators while granting crewing operations to Crewing Officers.

## Phase 3: Crew & Vessel Management Modules

- [x] Build API endpoints to Create, Read, Update, and Delete (CRUD) VESSEL entities.
- [x] Build API endpoints for SEAFARER profile creation and rank matching.
- [x] Build search and query filters allowing users to isolate crew groups by assigned vessel or current rank.

## Phase 4: Document Registry & Verification Workflow

- [x] Implement a multipart file upload endpoint accepting PDF, JPEG, and PNG certificate uploads.
- [x] Add strict data validation logic ensuring a certificate's IssueDate structurally precedes the ExpiryDate.
- [x] Implement workflow state mutation endpoints changing document validation flags (Pending to Verified or Rejected).
- [x] Integrate Supabase Storage to securely house uploaded certificate files and map them to unique database paths.

## Phase 5: Automated Expiry Tracking & Notification Engine (SMTP)

- [x] Code the automated calculation pipeline executing: Days Remaining = Expiration Date - Current System Date.
- [x] Build a daily background service worker that queries all Verified records and checks remaining days against configuration thresholds.
- [x] Build state-transition logic that automatically flips valid document statuses to Expiring Soon or Expired.
- [x] Integrate an asynchronous SMTP mail handler to automatically generate and email alert templates to crew managers when thresholds break.

## Phase 6: Reporting & Filtering Analytics

- [x] Create complex SQL aggregation routines that detect missing mandatory document rules for active ranks.
- [x] Build data aggregation endpoints summarizing fleet-wide compliance risk profiles.
- [x] Implement CSV/PDF export generation tools allowing managers to securely download active compliance logs for external vessel audits.

## Phase 7: Dynamic UI Construction (React + Tailwind CSS)

- [x] Build responsive user authentication views and login panels.
- [x] Construct the core Crew Manager Dashboard displaying fleet-wide records with color-coded warning row components (Green for Valid, Yellow for Expiring Soon, Red for Expired).
- [x] Build file management drag-and-drop screens permitting document metadata entry.
- [x] Build the Admin Configuration layout allowing custom alert day thresholds (e.g., 90, 60, 30 days) to be updated via sliders.

## Phase 8: Comprehensive Verification & System Evaluation

- [x] Test chronological metadata verification layers by attempting to force invalid dates.
- [x] Assert that the background scheduling cron updates expirations accurately when the system clock advances.
- [x] Validate that SMTP services dispatch the correct threshold details to mocked client dropboxes without structural failures.
