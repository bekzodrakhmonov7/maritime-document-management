-- Audit retention runs as an owner job (SR-14, ADR 0008).
--
-- The application role (app_backend) holds only INSERT and SELECT on the
-- Audit Log; it can no longer start the removal of old Audit Records either.
-- A pg_cron job scheduled here runs as the role applying the migrations, the
-- function's owner, every night at 03:17 UTC. The daily check still removes
-- Replaced Versions and Inactive seafarers.

REVOKE EXECUTE ON FUNCTION public.retention_remove_old_audit_records() FROM app_backend;

SELECT cron.schedule(
    'audit-retention',
    '17 3 * * *',
    'SELECT public.retention_remove_old_audit_records()'
);
