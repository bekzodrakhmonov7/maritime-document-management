-- The reference data of supabase/seed.sql (vessels, Positions, Document Types,
-- requirements, exceptions) for a hosted project that already has some of it.
-- Only the reference part: no app_backend password, no Vault values, no demo
-- people. Rows that already exist (by name) are kept as they are, so it can
-- run more than once. Needed before scripts/nfr/seed_volume.py on a hosted
-- project that was reset with --no-seed.

INSERT INTO public.vessel (name, imo_number, flag)
SELECT v.name, v.imo, v.flag
  FROM (VALUES ('MV Northern Star', '9312456', 'MT'),
               ('MV Baltic Dawn', '9405871', 'LR'),
               ('MT Aegean Spirit', '9527340', 'GR'),
               ('MV Pacific Trader', '9634018', 'PA')) AS v(name, imo, flag)
 WHERE NOT EXISTS (SELECT 1 FROM public.vessel x WHERE x.name = v.name OR x.imo_number = v.imo);

INSERT INTO public.position (name)
SELECT p.name
  FROM (VALUES ('Master'), ('Chief Officer'), ('Second Officer'), ('Chief Engineer'),
               ('Second Engineer'), ('Able Seaman'), ('Cook')) AS p(name)
 WHERE NOT EXISTS (SELECT 1 FROM public.position x WHERE x.name = p.name);

INSERT INTO public.document_type (name, expires, max_validity_months, renewable_at_sea)
SELECT t.name, t.expires, t.months, t.at_sea
  FROM (VALUES ('Passport', true, 120, false),
               ('Seaman''s Book', true, 120, false),
               ('Medical Certificate', true, 24, true),
               ('Certificate of Competency', true, 60, false),
               ('Basic Safety Training', true, 60, true),
               ('Yellow Fever Vaccination', false, NULL::int, false)) AS t(name, expires, months, at_sea)
 WHERE NOT EXISTS (SELECT 1 FROM public.document_type x WHERE x.name = t.name);

INSERT INTO public.document_type (name, expires, renewable_at_sea, depends_on_id)
SELECT 'Flag Endorsement of CoC', true, true, id
  FROM public.document_type
 WHERE name = 'Certificate of Competency'
   AND NOT EXISTS (SELECT 1 FROM public.document_type x WHERE x.name = 'Flag Endorsement of CoC');

INSERT INTO public.position_requirement (position_id, document_type_id)
SELECT p.id, t.id
  FROM public.position p CROSS JOIN public.document_type t
 WHERE (t.name IN ('Passport', 'Seaman''s Book', 'Medical Certificate', 'Basic Safety Training')
        OR (t.name IN ('Certificate of Competency', 'Flag Endorsement of CoC')
            AND p.name IN ('Master', 'Chief Officer', 'Second Officer', 'Chief Engineer', 'Second Engineer')))
   AND NOT EXISTS (SELECT 1 FROM public.position_requirement r
                    WHERE r.position_id = p.id AND r.document_type_id = t.id);

INSERT INTO public.requirement_exception (flag, document_type_id, effect, reason)
SELECT 'LR', id, 'add', 'Liberian flag requires yellow fever vaccination'
  FROM public.document_type t
 WHERE name = 'Yellow Fever Vaccination'
   AND NOT EXISTS (SELECT 1 FROM public.requirement_exception r
                    WHERE r.flag = 'LR' AND r.document_type_id = t.id);

INSERT INTO public.requirement_exception (vessel_id, document_type_id, effect, reason)
SELECT v.id, t.id, 'remove', 'Trades in Northern Europe only'
  FROM public.vessel v, public.document_type t
 WHERE v.name = 'MV Baltic Dawn' AND t.name = 'Yellow Fever Vaccination'
   AND NOT EXISTS (SELECT 1 FROM public.requirement_exception r
                    WHERE r.vessel_id = v.id AND r.document_type_id = t.id);
