-- Seed data for Maritime Crew Document Expiry Monitoring System
-- Do NOT insert auth.users here; that will be done in tests.

-- Seed vessels
INSERT INTO public.vessel (vessel_name, imo_number)
VALUES
    ('MV Ocean Star', '1234567'),
    ('MV Atlantic Voyager', '7654321');

-- Seed seafarers (5 across 2 vessels)
INSERT INTO public.seafarer (vessel_id, first_name, last_name, rank)
VALUES
    (1, 'John', 'Smith', 'Captain'),
    (1, 'Maria', 'Garcia', 'Chief Engineer'),
    (1, 'Ahmed', 'Hassan', 'Deck Officer'),
    (2, 'Li', 'Wei', 'Second Engineer'),
    (2, 'Anna', 'Petrova', 'Chief Mate');

-- Seed document types (6 types)
INSERT INTO public.document_type (type_name, is_mandatory)
VALUES
    ('COC', true),
    ('STCW', true),
    ('Medical', true),
    ('Passport', true),
    ('Endorsement', false),
    ('GMDSS', true);
