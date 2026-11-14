-- Local demo data only; runs on a local `supabase db reset`, never on hosted.
-- Tests never depend on it. Each slice extends it for its own tables.

-- Local dev password for the backend's role (never used on hosted, where an
-- administrator sets a generated one). DATABASE_URL in .env.example uses it.
ALTER ROLE app_backend PASSWORD 'app_backend_dev';

-- Reference data (S3): a flagged fleet, Positions and typed Document Types.
INSERT INTO public.vessel (name, imo_number, flag) VALUES
    ('MV Northern Star', '9312456', 'MT'),
    ('MV Baltic Dawn', '9405871', 'LR'),
    ('MT Aegean Spirit', '9527340', 'GR'),
    ('MV Pacific Trader', '9634018', 'PA');

INSERT INTO public.position (name) VALUES
    ('Master'),
    ('Chief Officer'),
    ('Second Officer'),
    ('Chief Engineer'),
    ('Second Engineer'),
    ('Able Seaman'),
    ('Cook');

INSERT INTO public.document_type (name, expires, max_validity_months, renewable_at_sea) VALUES
    ('Passport', true, 120, false),
    ('Seaman''s Book', true, 120, false),
    ('Medical Certificate', true, 24, true),
    ('Certificate of Competency', true, 60, false),
    ('Basic Safety Training', true, 60, true),
    ('Yellow Fever Vaccination', false, NULL, false);

-- An Endorsement: the flag state's recognition of the CoC.
INSERT INTO public.document_type (name, expires, renewable_at_sea, depends_on_id)
SELECT 'Flag Endorsement of CoC', true, true, id
  FROM public.document_type WHERE name = 'Certificate of Competency';
