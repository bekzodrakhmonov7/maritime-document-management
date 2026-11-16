-- O3: Retention (FR-24, FR-25 retention; T13).
--
-- Three kinds of record are removed automatically once their Retention
-- Period ends, as the last step of the scheduled daily check:
--
--   Replaced Versions        a Version older than a newer accepted Version,
--                            or a rejected one; the clock starts at that
--                            Review. The Current Version is never removed.
--   Inactive seafarers       the whole record (Documents, Versions, Reviews,
--                            Verifications, Assignments, Alerts, files) once
--                            the period from inactive_since has passed.
--   Audit Records            older than the audit period (occurred_at).
--
-- Audit Records about a removed seafarer are kept: removing a seafarer never
-- touches the Audit Log, whose records only go when their own period ends.
--
-- Versions, Reviews, Verifications and the Audit Log refuse UPDATE and
-- DELETE. The three removal functions below are the only exception: each
-- raises a bypass flag for its own transaction, removes, and lowers it again.
-- The flag is a row in private.retention_bypass keyed by the transaction id;
-- only the table owner can write it (no other role can even use the schema),
-- and a custom GUC or anything else a session can set doesn't count.
--
-- Removed rows' files go into public.file_removal in the same transaction. The
-- API deletes them from Storage after commit and retries failures on the next
-- run. A file still pointed to by a Version (details-only Versions share one)
-- or a Verification is never queued.


-- Settings: the three Retention Periods, in whole years ------------------------
ALTER TABLE public.settings
    ADD COLUMN retention_replaced_version_years int NOT NULL DEFAULT 5
        CHECK (retention_replaced_version_years BETWEEN 1 AND 10),
    ADD COLUMN retention_inactive_seafarer_years int NOT NULL DEFAULT 5
        CHECK (retention_inactive_seafarer_years BETWEEN 1 AND 10),
    ADD COLUMN retention_audit_record_years int NOT NULL DEFAULT 7
        CHECK (retention_audit_record_years BETWEEN 1 AND 10);


-- What each scheduled run's clean-up removed (shown on the Settings page) ------
ALTER TABLE public.daily_check_run
    ADD COLUMN retention_finished_at timestamptz,
    ADD COLUMN removed_versions int CHECK (removed_versions >= 0),
    ADD COLUMN removed_seafarers int CHECK (removed_seafarers >= 0),
    ADD COLUMN removed_audit_records int CHECK (removed_audit_records >= 0),
    -- Retention runs only in the scheduled check, never the manual one.
    ADD CONSTRAINT daily_check_run_retention_only_scheduled
        CHECK (NOT manual OR retention_finished_at IS NULL);

GRANT UPDATE (retention_finished_at, removed_versions, removed_seafarers, removed_audit_records)
    ON public.daily_check_run TO app_backend;


-- The file removal queue ---------------------------------------------------------
CREATE TABLE public.file_removal (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    file_path text NOT NULL UNIQUE CHECK (btrim(file_path) <> ''),
    queued_at timestamptz NOT NULL DEFAULT now(),
    attempts int NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error text
);

-- Rows are added only by the removal functions; the API deletes a row once
-- its object is gone, or records the failure for the next run.
GRANT SELECT, DELETE, UPDATE (attempts, last_error) ON public.file_removal TO app_backend;

ALTER TABLE public.file_removal ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.file_removal FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.file_removal FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.file_removal TO app_backend USING (true) WITH CHECK (true);


-- The bypass flag ----------------------------------------------------------------
CREATE SCHEMA private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;

CREATE TABLE private.retention_bypass (
    xact_id xid8 PRIMARY KEY
);

REVOKE ALL ON private.retention_bypass FROM PUBLIC;

-- True only inside a removal function's own transaction.
CREATE FUNCTION private.retention_bypass_on()
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT EXISTS (SELECT 1 FROM private.retention_bypass WHERE xact_id = pg_current_xact_id())
$$;

REVOKE ALL ON FUNCTION private.retention_bypass_on() FROM PUBLIC;


-- The immutability triggers honour the flag (TRUNCATE never does) ----------------
CREATE OR REPLACE FUNCTION public.version_is_immutable()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND private.retention_bypass_on() THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'version is immutable: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE OR REPLACE FUNCTION public.row_is_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND private.retention_bypass_on() THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION '% is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE OR REPLACE FUNCTION public.audit_log_is_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF TG_OP = 'DELETE' AND private.retention_bypass_on() THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;


-- Shared helpers (owner only) -----------------------------------------------------
CREATE FUNCTION private.retention_raise_bypass()
RETURNS void
LANGUAGE sql
SET search_path = ''
AS $$
    INSERT INTO private.retention_bypass (xact_id) VALUES (pg_current_xact_id())
    ON CONFLICT DO NOTHING
$$;

CREATE FUNCTION private.retention_lower_bypass()
RETURNS void
LANGUAGE sql
SET search_path = ''
AS $$
    DELETE FROM private.retention_bypass WHERE xact_id = pg_current_xact_id()
$$;

-- Queue the given paths unless a Version or a Verification still points to one.
CREATE FUNCTION private.retention_queue_files(paths text[])
RETURNS int
LANGUAGE sql
SET search_path = ''
AS $$
    WITH queued AS (
        INSERT INTO public.file_removal (file_path)
        SELECT DISTINCT p FROM unnest(paths) AS p
         WHERE p IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM public.version v WHERE v.file_path = p)
           AND NOT EXISTS (SELECT 1 FROM public.verification f WHERE f.proof_file_path = p)
        ON CONFLICT (file_path) DO NOTHING
        RETURNING 1
    )
    SELECT count(*)::int FROM queued
$$;

-- One system Audit Record (null actor, role `system`).
CREATE FUNCTION private.retention_record(
    p_target_type text, p_target_id text, p_seafarer_id bigint, p_after jsonb
)
RETURNS void
LANGUAGE sql
SET search_path = ''
AS $$
    INSERT INTO public.audit_log (actor_id, actor_email, actor_role, action, target_type,
                                  target_id, seafarer_id, after)
    VALUES (NULL, NULL, 'system', 'retention_removal', p_target_type, p_target_id,
            p_seafarer_id, p_after)
$$;

REVOKE ALL ON FUNCTION private.retention_raise_bypass() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.retention_lower_bypass() FROM PUBLIC;
REVOKE ALL ON FUNCTION private.retention_queue_files(text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION private.retention_record(text, text, bigint, jsonb) FROM PUBLIC;


-- 1. Replaced Versions -------------------------------------------------------------
-- A Version is replaced when its latest Review rejects it (clock: that Review)
-- or when a newer Version's latest Review accepts it (clock: the earliest such
-- accepting Review). The Current Version (the newest non-rejected one) is
-- never removed. At most p_limit (≤ 500) Versions per call, oldest clock first.
CREATE FUNCTION public.retention_remove_replaced_versions(p_limit int DEFAULT 500)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    cutoff timestamptz := now() - make_interval(
        years => (SELECT retention_replaced_version_years FROM public.settings));
    v record;
    paths text[];
    reviews int;
    verifications int;
    files int;
    removed int := 0;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 500 THEN
        RAISE EXCEPTION 'p_limit must be 1-500' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    PERFORM private.retention_raise_bypass();

    FOR v IN
        WITH latest AS (
            SELECT DISTINCT ON (r.version_id) r.version_id, r.decision, r.reviewed_at
              FROM public.review r
             ORDER BY r.version_id, r.id DESC
        ),
        versions AS (
            SELECT ver.id, ver.document_id, ver.uploaded_at, ver.file_path,
                   l.decision, l.reviewed_at
              FROM public.version ver LEFT JOIN latest l ON l.version_id = ver.id
        ),
        current AS (
            SELECT DISTINCT ON (document_id) document_id, id
              FROM versions
             WHERE decision IS DISTINCT FROM 'reject'
             ORDER BY document_id, uploaded_at DESC, id DESC
        ),
        replaced AS (
            SELECT o.id, o.document_id, o.file_path,
                   CASE WHEN o.decision = 'reject' THEN o.reviewed_at
                        ELSE (SELECT min(n.reviewed_at) FROM versions n
                               WHERE n.document_id = o.document_id
                                 AND n.decision = 'accept'
                                 AND (n.uploaded_at, n.id) > (o.uploaded_at, o.id))
                   END AS clock
              FROM versions o
             WHERE NOT EXISTS (SELECT 1 FROM current c WHERE c.id = o.id)
        )
        SELECT r.id, r.document_id, r.file_path, r.clock, d.seafarer_id
          FROM replaced r JOIN public.document d ON d.id = r.document_id
         WHERE r.clock IS NOT NULL AND r.clock <= cutoff
         ORDER BY r.clock, r.id
         LIMIT p_limit
    LOOP
        SELECT count(*) INTO reviews FROM public.review WHERE version_id = v.id;
        SELECT count(*) INTO verifications FROM public.verification WHERE version_id = v.id;
        paths := v.file_path || ARRAY(
            SELECT proof_file_path FROM public.verification
             WHERE version_id = v.id AND proof_file_path IS NOT NULL);
        DELETE FROM public.version WHERE id = v.id;  -- Reviews and Verifications cascade.
        files := private.retention_queue_files(paths);
        PERFORM private.retention_record('version', v.id::text, v.seafarer_id, jsonb_build_object(
            'kind', 'replaced_version',
            'document_id', v.document_id,
            'retention_started_at', v.clock,
            'reviews', reviews,
            'verifications', verifications,
            'files', files
        ));
        removed := removed + 1;
    END LOOP;

    PERFORM private.retention_lower_bypass();
    RETURN removed;
END;
$$;


-- 2. Inactive seafarers, whole ------------------------------------------------------
-- At most p_limit (≤ 500) seafarers per call, longest Inactive first.
CREATE FUNCTION public.retention_remove_inactive_seafarers(p_limit int DEFAULT 500)
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    cutoff timestamptz := now() - make_interval(
        years => (SELECT retention_inactive_seafarer_years FROM public.settings));
    s record;
    counts jsonb;
    paths text[];
    files int;
    removed int := 0;
BEGIN
    IF p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 500 THEN
        RAISE EXCEPTION 'p_limit must be 1-500' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    PERFORM private.retention_raise_bypass();

    FOR s IN
        SELECT id, inactive_since FROM public.seafarer
         WHERE inactive_since IS NOT NULL AND inactive_since <= cutoff
         ORDER BY inactive_since, id
         LIMIT p_limit
    LOOP
        SELECT jsonb_build_object(
                   'documents', (SELECT count(*) FROM public.document d WHERE d.seafarer_id = s.id),
                   'versions', (SELECT count(*) FROM public.version v
                                  JOIN public.document d ON d.id = v.document_id
                                 WHERE d.seafarer_id = s.id),
                   'reviews', (SELECT count(*) FROM public.review r
                                 JOIN public.version v ON v.id = r.version_id
                                 JOIN public.document d ON d.id = v.document_id
                                WHERE d.seafarer_id = s.id),
                   'verifications', (SELECT count(*) FROM public.verification f
                                       JOIN public.version v ON v.id = f.version_id
                                       JOIN public.document d ON d.id = v.document_id
                                      WHERE d.seafarer_id = s.id),
                   'assignments', (SELECT count(*) FROM public.assignment a WHERE a.seafarer_id = s.id),
                   'alerts', (SELECT count(*) FROM public.alert al
                                JOIN public.document d ON d.id = al.document_id
                               WHERE d.seafarer_id = s.id)
               )
          INTO counts;
        paths := ARRAY(
            SELECT v.file_path FROM public.version v
              JOIN public.document d ON d.id = v.document_id
             WHERE d.seafarer_id = s.id
            UNION
            SELECT f.proof_file_path FROM public.verification f
              JOIN public.version v ON v.id = f.version_id
              JOIN public.document d ON d.id = v.document_id
             WHERE d.seafarer_id = s.id AND f.proof_file_path IS NOT NULL
        );
        -- Everything hangs off the seafarer with ON DELETE CASCADE.
        DELETE FROM public.seafarer WHERE id = s.id;
        files := private.retention_queue_files(paths);
        PERFORM private.retention_record('seafarer', s.id::text, s.id,
            counts || jsonb_build_object(
                'kind', 'inactive_seafarer',
                'inactive_since', s.inactive_since,
                'files', files
            ));
        removed := removed + 1;
    END LOOP;

    PERFORM private.retention_lower_bypass();
    RETURN removed;
END;
$$;


-- 3. Old Audit Records ----------------------------------------------------------------
-- One summary record per clean-up with the cutoff date and the row count;
-- nothing when nothing was old enough.
CREATE FUNCTION public.retention_remove_old_audit_records()
RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    cutoff timestamptz := now() - make_interval(
        years => (SELECT retention_audit_record_years FROM public.settings));
    removed int;
BEGIN
    PERFORM private.retention_raise_bypass();
    DELETE FROM public.audit_log WHERE occurred_at < cutoff;
    GET DIAGNOSTICS removed = ROW_COUNT;
    PERFORM private.retention_lower_bypass();
    IF removed > 0 THEN
        PERFORM private.retention_record('audit_log', NULL, NULL, jsonb_build_object(
            'kind', 'audit_records',
            'cutoff', cutoff,
            'rows', removed
        ));
    END IF;
    RETURN removed;
END;
$$;


REVOKE ALL ON FUNCTION public.retention_remove_replaced_versions(int) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.retention_remove_inactive_seafarers(int) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.retention_remove_old_audit_records() FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION public.retention_remove_replaced_versions(int) TO app_backend;
GRANT EXECUTE ON FUNCTION public.retention_remove_inactive_seafarers(int) TO app_backend;
GRANT EXECUTE ON FUNCTION public.retention_remove_old_audit_records() TO app_backend;
