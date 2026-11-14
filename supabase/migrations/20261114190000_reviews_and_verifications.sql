-- S8: Reviews and Verifications (FR-11, FR-12; T1).
--
-- A Review is a second staff member's decision on one Version: accept or
-- reject, with a comment. The latest Review of a Version is its decision, so
-- a later Review overturns an earlier one and both are kept. The uploader can
-- never review their own Version; the API refuses it first and the trigger
-- below is the backstop.
--
-- A Verification is a check with the issuing authority of whether a Version is
-- genuine: date, source, result, reference and an optional proof file that
-- passed the Safety Checks. There is no four-eyes rule for Verifications.
--
-- The Current Version and Verified are computed by the API on read.

CREATE TABLE public.review (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Retention (O3) removes Versions, and their Reviews with them.
    version_id bigint NOT NULL REFERENCES public.version (id) ON DELETE CASCADE,
    decision text NOT NULL CHECK (decision IN ('accept', 'reject')),
    comment text NOT NULL CHECK (btrim(comment) <> ''),
    -- Accounts are never deleted.
    reviewed_by uuid NOT NULL REFERENCES public.users (id),
    reviewed_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_review_version_id ON public.review (version_id, id);
CREATE INDEX idx_review_reviewed_by ON public.review (reviewed_by);

GRANT SELECT, INSERT ON public.review TO app_backend;


CREATE TABLE public.verification (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version_id bigint NOT NULL REFERENCES public.version (id) ON DELETE CASCADE,
    -- The day the issuing authority was asked.
    checked_on date NOT NULL,
    source text NOT NULL CHECK (btrim(source) <> ''),
    result text NOT NULL CHECK (result IN ('confirmed', 'not_confirmed')),
    reference text NOT NULL CHECK (btrim(reference) <> ''),
    -- The optional proof file: a random path in the private bucket, with the
    -- cleaned name and detected type, as for a Version's file.
    proof_file_path text CHECK (btrim(proof_file_path) <> ''),
    proof_original_filename text
        CHECK (btrim(proof_original_filename) <> '' AND char_length(proof_original_filename) <= 255),
    proof_content_type text
        CHECK (proof_content_type IN ('application/pdf', 'image/jpeg', 'image/png')),
    recorded_by uuid NOT NULL REFERENCES public.users (id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT verification_proof_file_complete CHECK (
        num_nulls(proof_file_path, proof_original_filename, proof_content_type) IN (0, 3)
    )
);

CREATE INDEX idx_verification_version_id ON public.verification (version_id, id);
CREATE INDEX idx_verification_recorded_by ON public.verification (recorded_by);

GRANT SELECT, INSERT ON public.verification TO app_backend;


-- History can't be rewritten: nobody, the owner included, updates or deletes
-- a Review or a Verification. (The O3 retention functions will be the only
-- exception.)
CREATE FUNCTION public.row_is_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

REVOKE ALL ON FUNCTION public.row_is_append_only() FROM anon, authenticated, service_role;

CREATE TRIGGER review_no_update_or_delete
    BEFORE UPDATE OR DELETE ON public.review
    FOR EACH ROW
    EXECUTE FUNCTION public.row_is_append_only();

CREATE TRIGGER verification_no_update_or_delete
    BEFORE UPDATE OR DELETE ON public.verification
    FOR EACH ROW
    EXECUTE FUNCTION public.row_is_append_only();


-- The four-eyes rule: a Version's uploader never reviews it.
CREATE FUNCTION public.review_not_by_uploader()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM public.version v
         WHERE v.id = NEW.version_id AND v.uploaded_by = NEW.reviewed_by
    ) THEN
        RAISE EXCEPTION 'the uploader of version % cannot review it', NEW.version_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.review_not_by_uploader() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER review_reviewer_is_not_the_uploader
    BEFORE INSERT ON public.review
    FOR EACH ROW
    EXECUTE FUNCTION public.review_not_by_uploader();


-- Deny-all RLS (ADR 0001), as in the baseline.
ALTER TABLE public.review ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.review FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.review FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.review TO app_backend USING (true) WITH CHECK (true);

ALTER TABLE public.verification ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.verification FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.verification FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.verification TO app_backend USING (true) WITH CHECK (true);
