-- S4: requirements - which documents each Position needs (FR-08, T2).
--
-- position_requirement is the Position Requirement matrix; it replaces the
-- old global is_mandatory flag. requirement_exception adds or removes one
-- Document Type for one vessel or one flag, for one Position or (NULL) all
-- of them, with a reason. The required set is computed in the API
-- (app/domain.py: required_set), never in SQL. Foreign keys use RESTRICT, so
-- a Position or Document Type in use is retired instead of deleted.

CREATE TABLE public.position_requirement (
    position_id bigint NOT NULL REFERENCES public.position (id) ON DELETE RESTRICT,
    document_type_id bigint NOT NULL REFERENCES public.document_type (id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (position_id, document_type_id)
);

CREATE INDEX idx_position_requirement_document_type ON public.position_requirement (document_type_id);

-- A cell is set or cleared; there is nothing to update.
GRANT SELECT, INSERT, DELETE ON public.position_requirement TO app_backend;

CREATE TABLE public.requirement_exception (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- The scope: exactly one of a vessel or a flag (ISO 3166-1 alpha-2).
    vessel_id bigint REFERENCES public.vessel (id) ON DELETE RESTRICT,
    flag text CHECK (flag ~ '^[A-Z]{2}$'),
    -- NULL: every Position.
    position_id bigint REFERENCES public.position (id) ON DELETE RESTRICT,
    document_type_id bigint NOT NULL REFERENCES public.document_type (id) ON DELETE RESTRICT,
    effect text NOT NULL CHECK (effect IN ('add', 'remove')),
    reason text NOT NULL CHECK (btrim(reason) <> ''),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT requirement_exception_one_scope CHECK (num_nonnulls(vessel_id, flag) = 1)
);

-- One exception per (scope, Position-or-all, type). NULLS NOT DISTINCT makes
-- the unused scope column and "all positions" compare equal.
CREATE UNIQUE INDEX uq_requirement_exception
    ON public.requirement_exception (vessel_id, flag, position_id, document_type_id)
    NULLS NOT DISTINCT;
CREATE INDEX idx_requirement_exception_position ON public.requirement_exception (position_id);
CREATE INDEX idx_requirement_exception_document_type ON public.requirement_exception (document_type_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.requirement_exception TO app_backend;

-- Deny-all RLS (ADR 0001), as in the baseline.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['position_requirement', 'requirement_exception'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
        EXECUTE format(
            'CREATE POLICY app_backend_access ON public.%I TO app_backend USING (true) WITH CHECK (true)',
            t
        );
    END LOOP;
END
$$;
