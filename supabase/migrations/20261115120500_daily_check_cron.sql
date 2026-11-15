-- The database wakes the daily check (ADR 0003).
--
-- The API runs as short-lived functions, so it can't keep a timer. Instead,
-- every 5 minutes pg_cron POSTs (through pg_net) to the API's
-- /api/internal/daily-check, which runs the check if it is due: once per
-- local date, from the configured check time on.
--
-- The URL and the shared secret live in Supabase Vault, never here:
--   daily_check_url  the deployed endpoint, e.g. https://<domain>/api/internal/daily-check
--   cron_secret      the same value as CRON_SECRET in the API's environment
-- Locally seed.sql sets both. While either is missing the job does nothing
-- and doesn't fail, so a fresh database is harmless.
--
-- pg_net fires asynchronously; the 60-second timeout only decides how long
-- it waits to record the response in net._http_response. run_if_due claims
-- the day's run row first, so an overlapping or retried call is safe.

CREATE EXTENSION IF NOT EXISTS pg_cron WITH SCHEMA pg_catalog;
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;

SELECT cron.schedule(
    'daily-check',
    '*/5 * * * *',
    $job$
    DO $call$
    DECLARE
        url text := (SELECT decrypted_secret FROM vault.decrypted_secrets
                      WHERE name = 'daily_check_url' LIMIT 1);
        secret text := (SELECT decrypted_secret FROM vault.decrypted_secrets
                         WHERE name = 'cron_secret' LIMIT 1);
    BEGIN
        IF coalesce(url, '') = '' OR coalesce(secret, '') = '' THEN
            RETURN;
        END IF;
        PERFORM net.http_post(
            url := url,
            headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'X-Cron-Secret', secret
            ),
            body := '{}'::jsonb,
            timeout_milliseconds := 60000
        );
    END
    $call$;
    $job$
);
