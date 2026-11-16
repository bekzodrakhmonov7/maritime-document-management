-- The first sign-in is audited too (ADR 0004, FR-22).
--
-- GoTrue writes payload->>'action' = 'login' for a sign-in by an existing
-- Account, but 'user_signedup' when the first Sign-in Code completes
-- registration. With passwords impossible and e-mail confirmation on,
-- 'user_signedup' happens only when a code is used, so it is a sign-in and
-- is recorded as login_succeeded too. audit_login_succeeded() is unchanged;
-- only the trigger's condition widens. Every other action is still not copied.

DROP TRIGGER on_auth_login_audit ON auth.audit_log_entries;

CREATE TRIGGER on_auth_login_audit
    AFTER INSERT ON auth.audit_log_entries
    FOR EACH ROW
    WHEN ((NEW.payload->>'action') IN ('login', 'user_signedup'))
    EXECUTE FUNCTION public.audit_login_succeeded();
