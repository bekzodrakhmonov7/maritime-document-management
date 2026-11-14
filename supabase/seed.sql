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

-- Seafarers (S5): personal details and a held Position; one Inactive.
INSERT INTO public.seafarer (first_name, last_name, date_of_birth, nationality, position_id)
SELECT f, l, d::date, n, (SELECT id FROM public.position WHERE name = p)
  FROM (VALUES
    ('Anna', 'Petrova', '1984-03-14', 'BG', 'Master'),
    ('Ivan', 'Horvat', '1979-11-02', 'HR', 'Chief Engineer'),
    ('Jose', 'Santos', '1991-06-21', 'PH', 'Able Seaman'),
    ('Mykola', 'Shevchenko', '1988-01-30', 'UA', 'Chief Officer'),
    ('Rahul', 'Mehta', '1993-09-08', 'IN', 'Second Engineer'),
    ('Elena', 'Popescu', '1995-04-17', 'RO', 'Cook')
  ) AS s (f, l, d, n, p);

UPDATE public.seafarer
   SET inactive_since = now(), inactive_reason = 'Left the company'
 WHERE first_name = 'Elena' AND last_name = 'Popescu';

-- Assignments (S6): one under way, one starting soon, one finished, one
-- cancelled. Dates are relative to the day of the reset. Responsible Officer
-- links need Accounts, which come from sign-up, so the seed has none.
INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date)
SELECT (SELECT id FROM public.seafarer WHERE first_name = f AND last_name = l),
       (SELECT id FROM public.vessel WHERE name = v),
       (SELECT id FROM public.position WHERE name = p),
       CURRENT_DATE + s, CURRENT_DATE + e
  FROM (VALUES
    ('Anna', 'Petrova', 'MV Northern Star', 'Master', -40, 80),
    ('Ivan', 'Horvat', 'MV Baltic Dawn', 'Chief Engineer', 14, 134),
    ('Jose', 'Santos', 'MT Aegean Spirit', 'Able Seaman', -200, -20)
  ) AS a (f, l, v, p, s, e);

INSERT INTO public.assignment
    (seafarer_id, vessel_id, position_id, start_date, end_date, cancelled_at, cancel_reason)
SELECT s.id, (SELECT id FROM public.vessel WHERE name = 'MV Pacific Trader'), s.position_id,
       CURRENT_DATE + 30, CURRENT_DATE + 150, now(), 'Vessel schedule changed'
  FROM public.seafarer s WHERE s.first_name = 'Mykola' AND s.last_name = 'Shevchenko';
