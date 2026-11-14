-- Local demo data only; runs on a local `supabase db reset`, never on hosted.
-- Tests never depend on it. Each slice extends it for its own tables.

-- Local dev password for the backend's role (never used on hosted, where an
-- administrator sets a generated one). DATABASE_URL in .env.example uses it.
ALTER ROLE app_backend PASSWORD 'app_backend_dev';
