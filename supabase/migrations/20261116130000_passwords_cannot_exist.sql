-- Passwords cannot exist (ADR 0004): superseded before it reached a hosted
-- project, so it does nothing.
--
-- ADR 0004 wanted a trigger that kept auth.users.encrypted_password empty and
-- a one-off wipe of every stored password. ADR 0005 replaced that decision
-- (a password, then an e-mailed code) before this migration was pushed to
-- staging or production, so the hosted Accounts keep the passwords they
-- registered with. Local databases that ran the earlier version of this file
-- lost theirs; 20261116140000 drops that trigger if it is there, and those
-- Accounts set a new password through "Forgot password?".

SELECT 1;
