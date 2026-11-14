-- Baseline 2/4: accounts, settings and the Audit Log.

-- users: one Account per Supabase Auth user ---------------------------------
-- An Account is pending (no role) until an administrator approves it with a
-- role; it is then active, and can be deactivated and reactivated. Accounts
-- are never deleted, so the auth.users reference has no ON DELETE action.
CREATE TABLE public.users (
    id uuid PRIMARY KEY REFERENCES auth.users (id),
    email text NOT NULL,
    full_name text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'active', 'deactivated')),
    role text
        CHECK (role IN ('administrator', 'crewing_officer', 'manager')),
    -- The reason given for the last status or role change.
    status_reason text,
    status_changed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_role_required_when_active
        CHECK (status <> 'active' OR role IS NOT NULL),
    CONSTRAINT users_no_role_while_pending
        CHECK (status <> 'pending' OR role IS NULL)
);

CREATE INDEX idx_users_status ON public.users (status);
CREATE INDEX idx_users_email ON public.users (lower(email));

GRANT SELECT, UPDATE ON public.users TO app_backend;

-- Sign-up: every new auth user becomes a pending Account with no role. The
-- sign-up metadata `role` is ignored, so nobody can choose their own role.
-- SECURITY DEFINER runs as the owner (postgres, BYPASSRLS on Supabase), so
-- the insert passes the deny-all RLS on public.users.
CREATE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (id, email, full_name)
    VALUES (
        NEW.id,
        COALESCE(NEW.email, ''),
        COALESCE(NULLIF(btrim(NEW.raw_user_meta_data->>'full_name'), ''), NEW.email, '')
    );
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.handle_new_user();

-- settings: one typed row (T9) ----------------------------------------------
CREATE FUNCTION public.valid_alert_steps(steps int[])
RETURNS boolean
LANGUAGE sql
IMMUTABLE
SET search_path = ''
AS $$
    SELECT cardinality(steps) BETWEEN 1 AND 6
       AND 0 = ANY (steps)
       AND NOT EXISTS (SELECT 1 FROM unnest(steps) AS s WHERE s IS NULL OR s < 0)
       AND (SELECT count(DISTINCT s) FROM unnest(steps) AS s) = cardinality(steps)
$$;

CREATE TABLE public.settings (
    -- Single-row guard: the key can only ever be true.
    id boolean PRIMARY KEY DEFAULT true CHECK (id),
    alert_steps int[] NOT NULL DEFAULT '{90,60,30,0}'
        CHECK (public.valid_alert_steps(alert_steps)),
    planning_horizon_days int NOT NULL DEFAULT 90
        CHECK (planning_horizon_days BETWEEN 7 AND 365),
    max_file_size_mb int NOT NULL DEFAULT 10
        CHECK (max_file_size_mb BETWEEN 1 AND 25),
    max_pdf_pages int NOT NULL DEFAULT 50
        CHECK (max_pdf_pages BETWEEN 1 AND 500),
    -- An IANA zone name; the API checks it against zoneinfo.
    time_zone text NOT NULL DEFAULT 'UTC'
        CHECK (btrim(time_zone) <> ''),
    daily_check_time time NOT NULL DEFAULT '07:00'
        CHECK (extract(minute FROM daily_check_time)::int % 15 = 0
               AND extract(second FROM daily_check_time) = 0),
    -- Bumped on every save; a stale version is refused (409).
    version int NOT NULL DEFAULT 1,
    updated_at timestamptz NOT NULL DEFAULT now(),
    updated_by uuid REFERENCES public.users (id)
);

INSERT INTO public.settings DEFAULT VALUES;

GRANT SELECT, UPDATE ON public.settings TO app_backend;

-- audit_log: the append-only Audit Log (T7, ADR 0002) ------------------------
CREATE TABLE public.audit_log (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    -- Null for an unknown-e-mail login failure and for system actions.
    actor_id uuid,
    -- Copies as they were at that moment; `system` for automatic actions.
    actor_email text,
    actor_role text,
    -- From the fixed list in app/audit.py.
    action text NOT NULL,
    outcome text NOT NULL DEFAULT 'succeeded'
        CHECK (outcome IN ('succeeded', 'refused')),
    target_type text,
    target_id text,
    seafarer_id bigint,
    -- The changed fields only.
    before jsonb,
    after jsonb,
    reason text,
    ip inet,
    request_id text
);

CREATE INDEX idx_audit_log_occurred_at ON public.audit_log (occurred_at DESC);
CREATE INDEX idx_audit_log_actor_id ON public.audit_log (actor_id);
CREATE INDEX idx_audit_log_target ON public.audit_log (target_type, target_id);
CREATE INDEX idx_audit_log_seafarer_id ON public.audit_log (seafarer_id);
CREATE INDEX idx_audit_log_action ON public.audit_log (action);

-- The backend may only add and read Audit Records.
GRANT SELECT, INSERT ON public.audit_log TO app_backend;

-- Second safeguard: nobody, the owner included, changes or removes records.
CREATE FUNCTION public.audit_log_is_append_only()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION 'audit_log is append-only: % is not allowed', TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

CREATE TRIGGER audit_log_no_update_or_delete
    BEFORE UPDATE OR DELETE ON public.audit_log
    FOR EACH ROW
    EXECUTE FUNCTION public.audit_log_is_append_only();

CREATE TRIGGER audit_log_no_truncate
    BEFORE TRUNCATE ON public.audit_log
    FOR EACH STATEMENT
    EXECUTE FUNCTION public.audit_log_is_append_only();
