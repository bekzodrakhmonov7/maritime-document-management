-- Block after failed logins (SR-18).
--
-- The sign-in proxy counts *login failed* Audit Records of the last
-- 15 minutes with reason invalid_credentials (wrong password, unknown e-mail)
-- or totp_invalid (wrong authenticator code), per lower-case e-mail and per
-- client address. At 10 it writes a block here for 15 minutes; until
-- blocked_until has passed, /api/auth/login and /api/auth/verify answer 429
-- for that e-mail or address without asking Supabase Auth. Blocked attempts
-- are recorded as login_blocked and are not counted, so they never extend a
-- block.
--
--   kind  'email' (key: the lower-case e-mail) or 'ip' (key: the address).
--
-- An owner pg_cron job removes blocks that ended over a day ago, so e-mail
-- addresses and IP addresses are not kept longer than needed.

CREATE TABLE public.login_block (
    kind text NOT NULL CHECK (kind IN ('email', 'ip')),
    key text NOT NULL CHECK (key <> ''),
    blocked_until timestamptz NOT NULL,
    PRIMARY KEY (kind, key)
);

-- Deny-all RLS with the backend policy, as every table (ADR 0001).
ALTER TABLE public.login_block ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.login_block FORCE ROW LEVEL SECURITY;
REVOKE ALL ON public.login_block FROM anon, authenticated;
CREATE POLICY app_backend_access ON public.login_block
    TO app_backend USING (true) WITH CHECK (true);

GRANT SELECT, INSERT, UPDATE (blocked_until) ON public.login_block TO app_backend;

-- The counting query: action = 'login_failed' AND occurred_at > now() - 15 min.
CREATE INDEX idx_audit_log_action_occurred_at ON public.audit_log (action, occurred_at);

SELECT cron.schedule(
    'login-block-cleanup',
    '17 * * * *',
    $$DELETE FROM public.login_block WHERE blocked_until < now() - interval '1 day'$$
);
