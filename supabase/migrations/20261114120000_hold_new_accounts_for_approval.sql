-- Migration: close the self-assigned-role hole (FR-01)
-- Before this, handle_new_user() copied `role` from the sign-up metadata, so
-- anyone could register as an administrator. Now:
--   1. Every new account starts unapproved and as a crewing officer; the
--      sign-up metadata `role` is ignored.
--   2. The API refuses unapproved accounts (see app/deps.py).
-- Existing accounts are approved so current users are not locked out.
-- Until the admin user-management screen exists (FR-02), approve with:
--   UPDATE public.users SET is_approved = true, role = '<role>' WHERE id = '<uuid>';

ALTER TABLE public.users
    ADD COLUMN is_approved boolean NOT NULL DEFAULT false;

UPDATE public.users SET is_approved = true;

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
BEGIN
    INSERT INTO public.users (id, full_name, role, is_approved)
    VALUES (
        NEW.id,
        COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
        'crewing_officer',
        false
    );
    RETURN NEW;
END;
$$;
