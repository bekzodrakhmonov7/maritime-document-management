-- S3: reference data - the fleet, Positions and Document Types (FR-05, FR-07, T2).
--
-- Administrators maintain these through the API. Vessels are deactivated,
-- never deleted. A Position or Document Type that is in use is retired; it
-- can be deleted only while nothing references it, so every foreign key to
-- these tables uses ON DELETE RESTRICT.

-- vessel: the fleet ----------------------------------------------------------
CREATE TABLE public.vessel (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    imo_number text NOT NULL UNIQUE CHECK (imo_number ~ '^[0-9]{7}$'),
    -- The current flag only: an ISO 3166-1 alpha-2 code. The API checks it
    -- against the list of assigned codes.
    flag text NOT NULL CHECK (flag ~ '^[A-Z]{2}$'),
    active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_vessel_flag ON public.vessel (flag);

-- No DELETE: a vessel is deactivated instead.
GRANT SELECT, INSERT, UPDATE ON public.vessel TO app_backend;

-- position: the managed list of Positions -------------------------------------
CREATE TABLE public.position (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    retired boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX uq_position_name ON public.position (lower(name));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.position TO app_backend;

-- document_type: kinds of document and their rules ----------------------------
CREATE TABLE public.document_type (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (btrim(name) <> ''),
    -- True: every Version needs an expiry date. False: it must have none.
    expires boolean NOT NULL DEFAULT true,
    -- Optional, whole months, only on a type that expires.
    max_validity_months int CHECK (max_validity_months > 0),
    -- Advisory only (renew on board rather than before joining).
    renewable_at_sea boolean NOT NULL DEFAULT false,
    -- Set: this type is an Endorsement of that certificate.
    depends_on_id bigint REFERENCES public.document_type (id) ON DELETE RESTRICT,
    retired boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT document_type_max_validity_only_when_expires
        CHECK (expires OR max_validity_months IS NULL),
    CONSTRAINT document_type_no_self_dependency
        CHECK (depends_on_id <> id)
);

CREATE UNIQUE INDEX uq_document_type_name ON public.document_type (lower(name));
CREATE INDEX idx_document_type_depends_on ON public.document_type (depends_on_id);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.document_type TO app_backend;

-- The depends-on rules a CHECK can't see because they span two rows:
-- - one level only: the certificate is not itself an Endorsement, and a type
--   that has Endorsements can't become one;
-- - the certificate must expire, and keeps expiring while it has Endorsements.
-- The certificate row is locked so a concurrent change to it waits.
CREATE FUNCTION public.document_type_check_dependency()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
DECLARE
    target record;
BEGIN
    IF NEW.depends_on_id IS NOT NULL THEN
        SELECT id, expires, depends_on_id INTO target
          FROM public.document_type
         WHERE id = NEW.depends_on_id
           FOR SHARE;
        -- A missing target is left to the foreign key.
        IF FOUND THEN
            IF target.depends_on_id IS NOT NULL THEN
                RAISE EXCEPTION 'An Endorsement can depend on a certificate only one level deep: that type is itself an Endorsement'
                    USING ERRCODE = 'check_violation';
            END IF;
            IF NOT target.expires THEN
                RAISE EXCEPTION 'The certificate an Endorsement depends on must expire'
                    USING ERRCODE = 'check_violation';
            END IF;
        END IF;
        IF TG_OP = 'UPDATE' AND EXISTS (
            SELECT 1 FROM public.document_type WHERE depends_on_id = NEW.id
        ) THEN
            RAISE EXCEPTION 'An Endorsement can depend on a certificate only one level deep: this type has Endorsements of its own'
                USING ERRCODE = 'check_violation';
        END IF;
    END IF;

    IF TG_OP = 'UPDATE' AND NOT NEW.expires AND OLD.expires AND EXISTS (
        SELECT 1 FROM public.document_type WHERE depends_on_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'The certificate an Endorsement depends on must expire: this type has Endorsements'
            USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER document_type_dependency
    BEFORE INSERT OR UPDATE OF depends_on_id, expires ON public.document_type
    FOR EACH ROW
    EXECUTE FUNCTION public.document_type_check_dependency();

-- Deny-all RLS (ADR 0001), as in the baseline ----------------------------------
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['vessel', 'position', 'document_type'] LOOP
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

REVOKE ALL ON FUNCTION public.document_type_check_dependency() FROM PUBLIC, anon, authenticated, service_role;
