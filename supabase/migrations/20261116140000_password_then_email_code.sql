-- Sign in with a password, then an e-mailed Sign-in Code (ADR 0005, which
-- supersedes ADR 0004).
--
-- 1. Passwords may exist again: the trigger that kept encrypted_password
--    empty goes, where a local database still has it (20261116130000 never
--    created it on a hosted project). An Account whose password was wiped
--    locally sets one through "Forgot password" (an e-mailed code, then a
--    new password).
--
-- 2. Supabase Auth's password grant and its e-mail code endpoints are both
--    reachable with the public key, and either alone gives a session. So the
--    API accepts only a session the sign-in proxy has seen both steps for:
--
--    sign_in_challenge  issued by the proxy once the password is right (or a
--                       Register created the Account). The browser holds the
--                       token; only its SHA-256 is stored. The code must be
--                       typed against it within 10 minutes, with at most 5
--                       wrong codes. A row with no user_id is a decoy, given
--                       for a Register with an e-mail that already has an
--                       Account, so the answer looks the same.
--
--    verified_session   the Supabase session ids (the JWT's session_id) that
--                       passed both steps. Every request's session must be
--                       here; logout and a password reset remove it.
--
-- 3. *Login succeeded* is now written by the proxy when the code is right.
--    The trigger that copied Supabase's own `login` events is dropped: a
--    password grant alone is no longer a sign-in, and it would otherwise be
--    recorded twice (once per step).

DROP TRIGGER IF EXISTS keep_password_empty ON auth.users;
DROP FUNCTION IF EXISTS public.keep_password_empty();

DROP TRIGGER on_auth_login_audit ON auth.audit_log_entries;
DROP FUNCTION public.audit_login_succeeded();


CREATE TABLE public.sign_in_challenge (
    token_hash text PRIMARY KEY CHECK (token_hash ~ '^[0-9a-f]{64}$'),
    -- Null for a decoy.
    user_id uuid REFERENCES public.users (id) ON DELETE CASCADE,
    email text NOT NULL CHECK (btrim(email) <> ''),
    -- sign_in: a confirmed Account, its code comes from /otp.
    -- register: an Account not yet confirmed, its code is the confirmation.
    purpose text NOT NULL CHECK (purpose IN ('sign_in', 'register')),
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    wrong_codes int NOT NULL DEFAULT 0 CHECK (wrong_codes BETWEEN 0 AND 5),
    used_at timestamptz,
    CHECK (expires_at > created_at)
);

CREATE INDEX idx_sign_in_challenge_expires_at ON public.sign_in_challenge (expires_at);

CREATE TABLE public.verified_session (
    session_id uuid PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES public.users (id) ON DELETE CASCADE,
    verified_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX idx_verified_session_user_id ON public.verified_session (user_id);

-- Deny-all RLS with the backend policy, as every table (ADR 0001).
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['sign_in_challenge', 'verified_session'] LOOP
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

GRANT SELECT, INSERT, DELETE, UPDATE (wrong_codes, used_at)
    ON public.sign_in_challenge TO app_backend;
GRANT SELECT, INSERT, DELETE ON public.verified_session TO app_backend;
