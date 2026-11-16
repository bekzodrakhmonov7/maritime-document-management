-- Passwords cannot exist (ADR 0004): a Sign-in Code is the only way in.
--
-- Hiding the password fields is not enough: anyone holding the public key
-- could still ask Supabase Auth for a password grant, or set a password
-- through updateUser. So auth.users never keeps one. GoTrue treats an empty
-- (or NULL) encrypted_password as "no password" and refuses the password
-- grant with invalid_credentials.
--
-- The trigger blanks the hash on every insert and update, whoever writes it
-- (GoTrue as supabase_auth_admin, or a test inserting 'x'). Other columns
-- are left alone. Existing passwords are wiped below; their Accounts keep
-- working and next sign in by code to the same e-mail.

CREATE FUNCTION public.keep_password_empty()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    IF NEW.encrypted_password IS DISTINCT FROM '' THEN
        NEW.encrypted_password := '';
    END IF;
    RETURN NEW;
END;
$$;

REVOKE ALL ON FUNCTION public.keep_password_empty()
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER keep_password_empty
    BEFORE INSERT OR UPDATE ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION public.keep_password_empty();

UPDATE auth.users
   SET encrypted_password = ''
 WHERE encrypted_password IS DISTINCT FROM '';
