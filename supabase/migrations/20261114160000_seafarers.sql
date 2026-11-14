-- S5: seafarer records (FR-04, T3).
--
-- One record per Seafarer with personal details and the held Position.
-- There is no vessel_id (the Current Vessel is derived from Assignments, S6)
-- and no rank (Positions replace it). A seafarer is set Inactive with a
-- reason instead of being deleted; reactivation clears inactive_since, which
-- is the retention clock (O3). Records are removed only by retention, so the
-- backend role gets no DELETE.

CREATE TABLE public.seafarer (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    first_name text NOT NULL CHECK (btrim(first_name) <> ''),
    last_name text NOT NULL CHECK (btrim(last_name) <> ''),
    date_of_birth date,
    -- ISO 3166-1 alpha-2; the API checks it against the assigned codes.
    nationality text CHECK (nationality ~ '^[A-Z]{2}$'),
    -- The held Position, changed by hand only. The API lets only a
    -- non-retired Position be picked.
    position_id bigint NOT NULL REFERENCES public.position (id) ON DELETE RESTRICT,
    inactive_since timestamptz,
    inactive_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT seafarer_inactive_has_a_reason CHECK (
        (inactive_since IS NULL AND inactive_reason IS NULL)
        OR (inactive_since IS NOT NULL AND btrim(inactive_reason) <> '')
    )
);

CREATE INDEX idx_seafarer_position_id ON public.seafarer (position_id);
CREATE INDEX idx_seafarer_name ON public.seafarer (lower(last_name), lower(first_name));

-- No DELETE: only retention (O3) removes a seafarer.
GRANT SELECT, INSERT, UPDATE ON public.seafarer TO app_backend;

-- Deny-all RLS (ADR 0001), as in the baseline.
ALTER TABLE public.seafarer ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seafarer FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.seafarer FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.seafarer TO app_backend USING (true) WITH CHECK (true);
