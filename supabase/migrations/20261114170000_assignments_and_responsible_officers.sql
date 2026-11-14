-- S6: Assignments and Responsible Officers (FR-03, FR-04, FR-06; T3, T5).
--
-- An Assignment plans a seafarer on a vessel in a Position between two
-- calendar dates (company time zone), both included. Only "cancelled" is
-- stored; upcoming / under way / finished are derived from the dates by the
-- API. Cancelled Assignments are kept, never deleted.
--
-- One seafarer's non-cancelled Assignments never overlap: an exclusion on
-- seafarer + the inclusive date range. Back-to-back means the next one starts
-- the day after the previous one ends, so no day has two Assignments under way.
--
-- A Responsible Officer links a crewing-officer Account to a vessel (many to
-- many). Links are only for crewing officers; the API drops them when the
-- role changes away, and the trigger below refuses a role change that would
-- leave any behind.

CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA extensions;

CREATE TABLE public.assignment (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Never changed after creation. Retention (O3) removes a seafarer whole.
    seafarer_id bigint NOT NULL REFERENCES public.seafarer (id) ON DELETE CASCADE,
    vessel_id bigint NOT NULL REFERENCES public.vessel (id) ON DELETE RESTRICT,
    position_id bigint NOT NULL REFERENCES public.position (id) ON DELETE RESTRICT,
    start_date date NOT NULL,
    end_date date NOT NULL,
    cancelled_at timestamptz,
    cancel_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT assignment_end_not_before_start CHECK (end_date >= start_date),
    CONSTRAINT assignment_cancelled_has_a_reason CHECK (
        (cancelled_at IS NULL AND cancel_reason IS NULL)
        OR (cancelled_at IS NOT NULL AND coalesce(btrim(cancel_reason), '') <> '')
    ),
    CONSTRAINT assignment_no_overlap EXCLUDE USING gist (
        seafarer_id extensions.gist_int8_ops WITH OPERATOR(pg_catalog.=),
        daterange(start_date, end_date, '[]') WITH OPERATOR(pg_catalog.&&)
    ) WHERE (cancelled_at IS NULL)
);

CREATE INDEX idx_assignment_seafarer_id ON public.assignment (seafarer_id);
CREATE INDEX idx_assignment_vessel_id ON public.assignment (vessel_id, end_date);
CREATE INDEX idx_assignment_position_id ON public.assignment (position_id);

-- No DELETE: a cancelled Assignment is kept.
GRANT SELECT, INSERT, UPDATE ON public.assignment TO app_backend;


CREATE TABLE public.responsible_officer (
    -- Accounts are never deleted; CASCADE only matters to test fixtures.
    user_id uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    vessel_id bigint NOT NULL REFERENCES public.vessel (id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, vessel_id)
);

CREATE INDEX idx_responsible_officer_vessel_id ON public.responsible_officer (vessel_id);

GRANT SELECT, INSERT, DELETE ON public.responsible_officer TO app_backend;


-- Only crewing officers can be Responsible Officers. The Account row is
-- locked so its role can't change until the link commits.
CREATE FUNCTION public.responsible_officer_check_role()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    account_role text;
BEGIN
    SELECT role INTO account_role FROM public.users WHERE id = NEW.user_id FOR SHARE;
    IF account_role IS DISTINCT FROM 'crewing_officer' THEN
        RAISE EXCEPTION 'Only a crewing officer can be a Responsible Officer.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER responsible_officer_check_role
    BEFORE INSERT OR UPDATE ON public.responsible_officer
    FOR EACH ROW EXECUTE FUNCTION public.responsible_officer_check_role();


-- A role change away from crewing officer must drop the links first (the API
-- does, with an Audit Record per link).
CREATE FUNCTION public.users_role_change_keeps_no_links()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM public.responsible_officer WHERE user_id = NEW.id) THEN
        RAISE EXCEPTION 'Remove the vessel links before changing a crewing officer''s role.'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER users_role_change_keeps_no_links
    AFTER UPDATE OF role ON public.users
    FOR EACH ROW
    WHEN (OLD.role = 'crewing_officer' AND NEW.role IS DISTINCT FROM 'crewing_officer')
    EXECUTE FUNCTION public.users_role_change_keeps_no_links();


-- Deny-all RLS (ADR 0001), as in the baseline.
ALTER TABLE public.assignment ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.assignment FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.assignment FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.assignment TO app_backend USING (true) WITH CHECK (true);

ALTER TABLE public.responsible_officer ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.responsible_officer FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.responsible_officer FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.responsible_officer TO app_backend USING (true) WITH CHECK (true);
