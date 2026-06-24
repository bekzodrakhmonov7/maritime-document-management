-- Migration: guardrail for handle_new_user BYPASSRLS dependency
-- The AFTER INSERT trigger on auth.users -> public.handle_new_user() runs as
-- SECURITY DEFINER under the function owner (postgres). It relies on the
-- owner role having BYPASSRLS so the insert into FORCE ROW LEVEL SECURITY
-- public.users succeeds. If that attribute is ever removed, every signup
-- would roll back silently. This migration:
--   1. Documents the dependency.
--   2. Fails fast (in this migration) if the prerequisite is violated.
--   3. Recreates the function with explicit search_path and stricter inputs
--      so the trigger is self-contained and reviewable.
--
-- It does NOT change the function owner: postgres cannot SET ROLE to
-- supabase_admin (the only guaranteed BYPASSRLS superuser), so the owner
-- must remain a role whose BYPASSRLS is part of the platform contract.

DO $$
DECLARE
    owner_bypassrls boolean;
    owner_name text;
BEGIN
    SELECT rolname, rolbypassrls
      INTO owner_name, owner_bypassrls
      FROM pg_roles
     WHERE oid = (
         SELECT p.proowner FROM pg_proc p
         JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE p.proname = 'handle_new_user' AND n.nspname = 'public'
     );

    IF owner_name IS NULL THEN
        RAISE EXCEPTION 'public.handle_new_user() does not exist';
    END IF;

    IF NOT owner_bypassrls THEN
        RAISE EXCEPTION
            'public.handle_new_user() is owned by % which lacks BYPASSRLS; '
            'signup-trigger inserts into public.users will fail under FORCE RLS',
            owner_name;
    END IF;
END
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (id, full_name, role)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
        COALESCE(NEW.raw_user_meta_data->>'role', 'crewing_officer')
    );
    RETURN NEW;
END;
$$;
