-- A TOTP second factor replaces the e-mailed sign-in code (SR-03, ADR 0007).
--
-- Once the password is right, the sign-in proxy holds Supabase's aal1
-- session for the TOTP step: the challenge and verify calls at Supabase Auth
-- need its access token. The browser never sees that token; the challenge
-- row keeps it, with the TOTP factor it is for, until the code is right
-- (the session then becomes aal2 and goes to the browser), five wrong codes
-- end the challenge, or the challenge expires. In each case the token is
-- removed: set to NULL on use or on the fifth wrong code, and an owner
-- pg_cron job deletes expired challenges every 5 minutes. The token is never
-- logged or returned by the API.
--
-- purpose:
--   register  the e-mailed confirmation code that finishes a Register.
--   sign_in   the TOTP code (enrolment at the first sign-in, or an enrolled
--             factor); factor_id and access_token are set.

ALTER TABLE public.sign_in_challenge
    ADD COLUMN factor_id uuid,
    ADD COLUMN access_token text CHECK (access_token IS NULL OR access_token <> '');

GRANT UPDATE (access_token) ON public.sign_in_challenge TO app_backend;

SELECT cron.schedule(
    'sign-in-challenge-cleanup',
    '*/5 * * * *',
    'DELETE FROM public.sign_in_challenge WHERE expires_at < now()'
);
