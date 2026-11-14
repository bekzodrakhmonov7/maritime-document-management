-- Baseline 4/4: deny-all row-level security (ADR 0001).
--
-- Permissions are enforced in the API. Every public table has RLS enabled
-- and forced with no policy for anon or authenticated, so a leaked token
-- can't read or write anything through PostgREST. The only policy lets the
-- backend role (which has no BYPASSRLS) use the rows its grants allow.
-- Every later table must do the same: enable + force RLS, add the
-- app_backend policy, and grant app_backend table by table.

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['users', 'settings', 'audit_log'] LOOP
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

-- service_role bypasses RLS, so it is kept out of the Audit Log by grants.
REVOKE ALL ON public.audit_log FROM service_role;

-- Helper functions are not part of the public API.
REVOKE ALL ON FUNCTION public.valid_alert_steps(int[]) FROM anon, authenticated;
REVOKE ALL ON FUNCTION public.audit_log_is_append_only() FROM anon, authenticated, service_role;
