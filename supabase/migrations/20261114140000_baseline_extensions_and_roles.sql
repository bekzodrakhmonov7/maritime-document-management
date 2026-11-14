-- Baseline 1/4: extensions and the backend's database role.
--
-- The API and the worker connect as `app_backend`, never as the owner
-- (ADR 0002). It may log in but holds no password here: locally seed.sql
-- sets a dev password, on hosted an administrator runs
--   ALTER ROLE app_backend PASSWORD '<generated secret>';
-- once and puts it in DATABASE_URL. It inherits nothing, cannot bypass RLS
-- and owns nothing; each table grants it what it needs, table by table.

CREATE EXTENSION IF NOT EXISTS pgcrypto WITH SCHEMA extensions;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_backend') THEN
        CREATE ROLE app_backend LOGIN NOINHERIT NOBYPASSRLS
            NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO app_backend;
