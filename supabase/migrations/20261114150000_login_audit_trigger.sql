-- S2: login succeeded is copied from Supabase's own auth audit table (R1, T7,
-- ADR 0002).
--
-- GoTrue writes one auth.audit_log_entries row (payload->>'action' = 'login')
-- per sign-in, whichever client made it, so sign-ins that skip our UI are
-- recorded too. This is the only trigger that writes Audit Records.
--
-- SECURITY DEFINER: it runs as the owner (postgres, BYPASSRLS on Supabase),
-- so the insert passes the Audit Log's deny-all RLS whoever fires it
-- (GoTrue connects as supabase_auth_admin). It catches every error and only
-- warns, so it can never break sign-in.

CREATE FUNCTION public.audit_login_succeeded()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_actor uuid;
    v_ip inet;
BEGIN
    BEGIN
        v_ip := NULLIF(btrim(NEW.ip_address), '')::inet;
    EXCEPTION WHEN OTHERS THEN
        v_ip := NULL;
    END;

    BEGIN
        v_actor := (NEW.payload->>'actor_id')::uuid;

        INSERT INTO public.audit_log
            (actor_id, actor_email, actor_role, action, outcome, target_type, target_id, ip)
        SELECT v_actor,
               COALESCE(u.email, NEW.payload->>'actor_username'),
               u.role,
               'login_succeeded',
               'succeeded',
               'account',
               v_actor::text,
               v_ip
          FROM (SELECT 1) AS one
          LEFT JOIN public.users AS u ON u.id = v_actor;
    EXCEPTION WHEN OTHERS THEN
        RAISE WARNING 'audit_login_succeeded: login not recorded (%: %)', SQLSTATE, SQLERRM;
    END;

    RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION public.audit_login_succeeded()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER on_auth_login_audit
    AFTER INSERT ON auth.audit_log_entries
    FOR EACH ROW
    WHEN ((NEW.payload->>'action') = 'login')
    EXECUTE FUNCTION public.audit_login_succeeded();
