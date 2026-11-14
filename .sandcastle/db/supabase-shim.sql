-- Stand-in for the parts of a local Supabase database that this repo's
-- migrations and tests rely on. Applied by `sandbox-db reset` (as the
-- superuser supabase_admin) to a fresh cluster, before supabase/migrations.
--
-- It mirrors Supabase's role model: `postgres` is NOT a superuser but has
-- BYPASSRLS, owns the database and runs the migrations. It is not the real
-- thing: GoTrue (Auth API) and the Storage API are not running, only their
-- tables exist. Code that calls those HTTP APIs must be tested on the host.

-- Roles ---------------------------------------------------------------------
CREATE ROLE postgres LOGIN CREATEROLE CREATEDB REPLICATION BYPASSRLS PASSWORD 'postgres';
CREATE ROLE anon NOLOGIN NOINHERIT;
CREATE ROLE authenticated NOLOGIN NOINHERIT;
CREATE ROLE service_role NOLOGIN NOINHERIT BYPASSRLS;
CREATE ROLE authenticator LOGIN NOINHERIT PASSWORD 'postgres';
GRANT anon, authenticated, service_role TO authenticator;
CREATE ROLE supabase_auth_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'postgres';
CREATE ROLE supabase_storage_admin LOGIN NOINHERIT CREATEROLE PASSWORD 'postgres';
GRANT anon, authenticated, service_role TO postgres WITH ADMIN OPTION;
-- As on Supabase, postgres can add policies and triggers to auth/storage
-- tables (CREATE POLICY needs ownership, which membership provides).
GRANT supabase_auth_admin, supabase_storage_admin TO postgres;

ALTER DATABASE postgres OWNER TO postgres;
ALTER SCHEMA public OWNER TO postgres;

-- Extensions live in their own schema, as on Supabase ------------------------
CREATE SCHEMA extensions;
GRANT USAGE ON SCHEMA extensions TO postgres, anon, authenticated, service_role;
CREATE EXTENSION pgcrypto WITH SCHEMA extensions;
CREATE EXTENSION "uuid-ossp" WITH SCHEMA extensions;
ALTER DATABASE postgres SET search_path TO "$user", public, extensions;
ALTER ROLE postgres SET search_path TO "$user", public, extensions;

-- Default grants Supabase applies to objects postgres creates in public.
-- RLS, not grants, is what keeps anon/authenticated out.
GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON TABLES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON SEQUENCES TO anon, authenticated, service_role;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA public GRANT ALL ON FUNCTIONS TO anon, authenticated, service_role;

-- auth ----------------------------------------------------------------------
CREATE SCHEMA auth AUTHORIZATION supabase_auth_admin;
GRANT USAGE ON SCHEMA auth TO postgres, anon, authenticated, service_role;

CREATE TABLE auth.users (
    instance_id uuid,
    id uuid PRIMARY KEY,
    aud varchar(255),
    role varchar(255),
    email varchar(255),
    encrypted_password varchar(255),
    email_confirmed_at timestamptz,
    invited_at timestamptz,
    confirmation_token varchar(255),
    confirmation_sent_at timestamptz,
    recovery_token varchar(255),
    recovery_sent_at timestamptz,
    email_change_token_new varchar(255),
    email_change varchar(255),
    email_change_sent_at timestamptz,
    last_sign_in_at timestamptz,
    raw_app_meta_data jsonb,
    raw_user_meta_data jsonb,
    is_super_admin boolean,
    created_at timestamptz,
    updated_at timestamptz,
    phone text UNIQUE DEFAULT NULL,
    phone_confirmed_at timestamptz,
    phone_change text DEFAULT '',
    phone_change_token varchar(255) DEFAULT '',
    phone_change_sent_at timestamptz,
    confirmed_at timestamptz GENERATED ALWAYS AS (LEAST(email_confirmed_at, phone_confirmed_at)) STORED,
    email_change_token_current varchar(255) DEFAULT '',
    email_change_confirm_status smallint DEFAULT 0,
    banned_until timestamptz,
    reauthentication_token varchar(255) DEFAULT '',
    reauthentication_sent_at timestamptz,
    is_sso_user boolean NOT NULL DEFAULT false,
    deleted_at timestamptz,
    is_anonymous boolean NOT NULL DEFAULT false
);
CREATE INDEX users_instance_id_email_idx ON auth.users (instance_id, lower(email));

CREATE TABLE auth.audit_log_entries (
    instance_id uuid,
    id uuid PRIMARY KEY,
    payload json,
    created_at timestamptz,
    ip_address varchar(64) NOT NULL DEFAULT ''
);
CREATE INDEX audit_logs_instance_id_idx ON auth.audit_log_entries (instance_id);

ALTER TABLE auth.users OWNER TO supabase_auth_admin;
ALTER TABLE auth.audit_log_entries OWNER TO supabase_auth_admin;
-- postgres may add triggers to auth tables (e.g. on_auth_user_created).
GRANT ALL ON ALL TABLES IN SCHEMA auth TO postgres, service_role;

-- JWT helpers, reading the claims PostgREST sets per request.
CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim', true), ''),
    nullif(current_setting('request.jwt.claims', true), '')
  )::jsonb
$$;
CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim.sub', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
  )::uuid
$$;
CREATE FUNCTION auth.role() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim.role', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role')
  )::text
$$;
CREATE FUNCTION auth.email() RETURNS text LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    nullif(current_setting('request.jwt.claim.email', true), ''),
    (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'email')
  )::text
$$;
ALTER FUNCTION auth.jwt() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.uid() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.role() OWNER TO supabase_auth_admin;
ALTER FUNCTION auth.email() OWNER TO supabase_auth_admin;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA auth TO postgres, anon, authenticated, service_role;

-- storage -------------------------------------------------------------------
CREATE SCHEMA storage AUTHORIZATION supabase_storage_admin;
GRANT USAGE ON SCHEMA storage TO postgres, anon, authenticated, service_role;

CREATE TABLE storage.buckets (
    id text PRIMARY KEY,
    name text NOT NULL UNIQUE,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    public boolean DEFAULT false,
    avif_autodetection boolean DEFAULT false,
    file_size_limit bigint,
    allowed_mime_types text[],
    owner_id text
);

CREATE TABLE storage.objects (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    bucket_id text REFERENCES storage.buckets (id),
    name text,
    owner uuid,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    last_accessed_at timestamptz DEFAULT now(),
    metadata jsonb,
    path_tokens text[] GENERATED ALWAYS AS (string_to_array(name, '/')) STORED,
    version text,
    owner_id text,
    user_metadata jsonb
);
CREATE UNIQUE INDEX bucketid_objname ON storage.objects (bucket_id, name);
ALTER TABLE storage.objects ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION storage.foldername(name text) RETURNS text[] LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE _parts text[];
BEGIN
  SELECT string_to_array(name, '/') INTO _parts;
  RETURN _parts[1:array_length(_parts, 1) - 1];
END $$;
CREATE FUNCTION storage.filename(name text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE _parts text[];
BEGIN
  SELECT string_to_array(name, '/') INTO _parts;
  RETURN _parts[array_length(_parts, 1)];
END $$;
CREATE FUNCTION storage.extension(name text) RETURNS text LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE _parts text[]; _filename text;
BEGIN
  SELECT string_to_array(name, '/') INTO _parts;
  SELECT _parts[array_length(_parts, 1)] INTO _filename;
  RETURN reverse(split_part(reverse(_filename), '.', 1));
END $$;

ALTER TABLE storage.buckets OWNER TO supabase_storage_admin;
ALTER TABLE storage.objects OWNER TO supabase_storage_admin;
ALTER FUNCTION storage.foldername(text) OWNER TO supabase_storage_admin;
ALTER FUNCTION storage.filename(text) OWNER TO supabase_storage_admin;
ALTER FUNCTION storage.extension(text) OWNER TO supabase_storage_admin;
GRANT ALL ON ALL TABLES IN SCHEMA storage TO postgres, service_role;
GRANT ALL ON ALL TABLES IN SCHEMA storage TO anon, authenticated;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA storage TO postgres, anon, authenticated, service_role;
