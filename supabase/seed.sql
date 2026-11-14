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

-- Requirements (S4): everyone needs the passport, seaman's book, medical and
-- safety training; officers and engineers also the CoC and its endorsement.
INSERT INTO public.position_requirement (position_id, document_type_id)
SELECT p.id, t.id
  FROM public.position p CROSS JOIN public.document_type t
 WHERE t.name IN ('Passport', 'Seaman''s Book', 'Medical Certificate', 'Basic Safety Training')
    OR (t.name IN ('Certificate of Competency', 'Flag Endorsement of CoC')
        AND p.name IN ('Master', 'Chief Officer', 'Second Officer', 'Chief Engineer', 'Second Engineer'));

-- Exceptions: Liberia wants the yellow fever vaccination from everyone, but
-- MV Baltic Dawn (Liberian flag) only trades in Northern Europe.
INSERT INTO public.requirement_exception (flag, document_type_id, effect, reason)
SELECT 'LR', id, 'add', 'Liberian flag requires yellow fever vaccination'
  FROM public.document_type WHERE name = 'Yellow Fever Vaccination';

INSERT INTO public.requirement_exception (vessel_id, document_type_id, effect, reason)
SELECT v.id, t.id, 'remove', 'Trades in Northern Europe only'
  FROM public.vessel v, public.document_type t
 WHERE v.name = 'MV Baltic Dawn' AND t.name = 'Yellow Fever Vaccination';

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

-- Documents (S10 readiness demo). Versions, Reviews and Verifications need
-- an Account, so two seed-only demo authors are made deactivated (no
-- password, can't sign in). Their Versions have no file in Storage, so
-- downloading them fails locally.
INSERT INTO auth.users (id, email, raw_user_meta_data, created_at, updated_at) VALUES
    ('00000000-0000-4000-8000-00000000d001', 'demo-uploader@example.invalid',
     '{"full_name": "Demo Uploader"}', now(), now()),
    ('00000000-0000-4000-8000-00000000d002', 'demo-reviewer@example.invalid',
     '{"full_name": "Demo Reviewer"}', now(), now());

UPDATE public.users
   SET status = 'deactivated', role = 'crewing_officer',
       status_reason = 'Seed-only author of the demo documents', status_changed_at = now()
 WHERE id IN ('00000000-0000-4000-8000-00000000d001', '00000000-0000-4000-8000-00000000d002');

-- Ivan's starting-soon Assignment (Chief Engineer on MV Baltic Dawn, day 14
-- to day 134) fills every readiness bucket:
--   before joining: passport runs out before start, CoC (not renewable at
--     sea) runs out during, the flag endorsement is missing;
--   renewable at sea: the medical runs out during (and awaits review);
--   not reviewed: the medical and the safety training;
--   covers all: the seaman's book (Verified).
-- Anna, under way on MV Northern Star, has a medical that expired on board.
INSERT INTO public.document (seafarer_id, document_type_id)
SELECT s.id, t.id
  FROM (VALUES
    ('Ivan', 'Passport'), ('Ivan', 'Seaman''s Book'), ('Ivan', 'Medical Certificate'),
    ('Ivan', 'Certificate of Competency'), ('Ivan', 'Basic Safety Training'),
    ('Anna', 'Passport'), ('Anna', 'Medical Certificate')
  ) AS d (f, t_name)
  JOIN public.seafarer s ON s.first_name = d.f
  JOIN public.document_type t ON t.name = d.t_name;

INSERT INTO public.version
    (document_id, file_path, original_filename, content_type, document_number,
     issuing_authority, issue_date, expiry_date, uploaded_by)
SELECT d.id, 'seed/' || gen_random_uuid() || '.pdf', v.filename, 'application/pdf', v.number,
       v.authority, CURRENT_DATE + v.issued, CURRENT_DATE + v.expires,
       '00000000-0000-4000-8000-00000000d001'
  FROM (VALUES
    ('Ivan', 'Passport', 'passport.pdf', 'HR-4471920', 'Ministry of the Interior, Croatia', -3640, 10),
    ('Ivan', 'Seaman''s Book', 'seamans-book.pdf', 'SB-208113', 'Harbour Master''s Office, Rijeka', -1500, 1500),
    ('Ivan', 'Medical Certificate', 'medical.pdf', 'MED-2026-0912', 'Port Health Clinic, Split', -270, 90),
    ('Ivan', 'Certificate of Competency', 'coc.pdf', 'COC-III/2-7781', 'Ministry of the Sea, Croatia', -1400, 60),
    ('Ivan', 'Basic Safety Training', 'bst.pdf', 'BST-55190', 'Maritime Training Centre, Rijeka', -500, 900),
    ('Anna', 'Passport', 'passport.pdf', 'BG-3381045', 'Ministry of the Interior, Bulgaria', -900, 2700),
    ('Anna', 'Medical Certificate', 'medical.pdf', 'MED-BG-6620', 'Seafarers'' Clinic, Varna', -700, -5)
  ) AS v (f, t_name, filename, number, authority, issued, expires)
  JOIN public.seafarer s ON s.first_name = v.f
  JOIN public.document_type t ON t.name = v.t_name
  JOIN public.document d ON d.seafarer_id = s.id AND d.document_type_id = t.id;

-- Accepted by the second demo author; the medical and the safety training
-- of Ivan's await review.
INSERT INTO public.review (version_id, decision, comment, reviewed_by)
SELECT ver.id, 'accept', 'Matches the original', '00000000-0000-4000-8000-00000000d002'
  FROM public.version ver
  JOIN public.document d ON d.id = ver.document_id
  JOIN public.seafarer s ON s.id = d.seafarer_id
  JOIN public.document_type t ON t.id = d.document_type_id
 WHERE NOT (s.first_name = 'Ivan' AND t.name IN ('Medical Certificate', 'Basic Safety Training'));

INSERT INTO public.verification (version_id, checked_on, source, result, reference, recorded_by)
SELECT ver.id, CURRENT_DATE - 3, 'E-mail to the issuing authority', 'confirmed', 'DEMO-VER-1',
       '00000000-0000-4000-8000-00000000d002'
  FROM public.version ver
  JOIN public.document d ON d.id = ver.document_id
  JOIN public.seafarer s ON s.id = d.seafarer_id
  JOIN public.document_type t ON t.id = d.document_type_id
 WHERE s.first_name = 'Ivan' AND t.name IN ('Seaman''s Book', 'Certificate of Competency');
