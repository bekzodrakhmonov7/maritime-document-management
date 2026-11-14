-- S7: Documents and Versions (FR-09, FR-10, FR-13, FR-15; T1, T2, T8).
--
-- A Document is one seafarer's instance of a Document Type: at most one per
-- seafarer and type, and it holds nothing else. Its content lives in its
-- Versions. A Version is an immutable snapshot of a file and its key details;
-- a change to either (a renewal, a corrected typo) is a new Version, and a
-- details-only Version points at the same stored file instead of copying it.
--
-- Current Version and Expiry Status are computed by the API on read; nothing
-- here stores them. The Document Type's rules (expires, maximum validity) are
-- checked by the API when a Version is created, never again afterwards.

CREATE TABLE public.document (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Retention (O3) removes an Inactive seafarer whole.
    seafarer_id bigint NOT NULL REFERENCES public.seafarer (id) ON DELETE CASCADE,
    -- A used Document Type is retired, not deleted.
    document_type_id bigint NOT NULL REFERENCES public.document_type (id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_document_seafarer_type UNIQUE (seafarer_id, document_type_id)
);

CREATE INDEX idx_document_document_type_id ON public.document (document_type_id);

-- Documents are created with their first Version and never changed or removed
-- by the API.
GRANT SELECT, INSERT ON public.document TO app_backend;


CREATE TABLE public.version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES public.document (id) ON DELETE CASCADE,
    -- A random path in the private bucket; shared by details-only Versions.
    file_path text NOT NULL CHECK (btrim(file_path) <> ''),
    -- For display and downloads only: control characters and separators
    -- stripped, at most 255 characters. Never part of the storage path.
    original_filename text NOT NULL
        CHECK (btrim(original_filename) <> '' AND char_length(original_filename) <= 255),
    -- Detected from the file's content, never taken from the client.
    content_type text NOT NULL
        CHECK (content_type IN ('application/pdf', 'image/jpeg', 'image/png')),
    document_number text NOT NULL CHECK (btrim(document_number) <> ''),
    issuing_authority text NOT NULL CHECK (btrim(issuing_authority) <> ''),
    issue_date date NOT NULL,
    -- NULL = no expiry date (a Document Type that doesn't expire).
    expiry_date date,
    -- Accounts are never deleted.
    uploaded_by uuid NOT NULL REFERENCES public.users (id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT version_expiry_after_issue CHECK (expiry_date IS NULL OR expiry_date > issue_date)
);

CREATE INDEX idx_version_document_id ON public.version (document_id, uploaded_at DESC, id DESC);
CREATE INDEX idx_version_file_path ON public.version (file_path);
CREATE INDEX idx_version_uploaded_by ON public.version (uploaded_by);

GRANT SELECT, INSERT ON public.version TO app_backend;


-- History can't be rewritten: nobody, the owner included, updates or deletes
-- a Version. (The O3 retention functions will be the only exception.)
CREATE FUNCTION public.version_is_immutable()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'version is immutable: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER version_no_update_or_delete
    BEFORE UPDATE OR DELETE ON public.version
    FOR EACH ROW
    EXECUTE FUNCTION public.version_is_immutable();

REVOKE ALL ON FUNCTION public.version_is_immutable() FROM anon, authenticated, service_role;


-- The private bucket (baseline) only takes what the Safety Checks pass. The
-- API also enforces the configurable limit, which is at most this ceiling.
UPDATE storage.buckets
   SET public = false,
       file_size_limit = 25 * 1024 * 1024,
       allowed_mime_types = ARRAY['application/pdf', 'image/jpeg', 'image/png']
 WHERE id = 'crew-documents';


-- Deny-all RLS (ADR 0001), as in the baseline.
ALTER TABLE public.document ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.document FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.document TO app_backend USING (true) WITH CHECK (true);

ALTER TABLE public.version ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.version FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.version FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.version TO app_backend USING (true) WITH CHECK (true);
