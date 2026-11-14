-- S12: Alerts and the daily check (FR-16; T6, T9).
--
-- An Alert says a Document reached an Alert Step for one expiry date. Each
-- (Document, step, expiry date) is raised at most once, so a renewal with a
-- new expiry date starts the steps over while a details-only Version or a
-- rejection fallback with the same date doesn't. Steps reached late are kept
-- as skipped: only the most urgent one reached is sent.
--
-- Open-ness is computed by the API on read (the seafarer isn't Inactive and
-- the Current Version still has the raised expiry date); nothing stores it.
--
-- Each Alert that is sent gets one delivery row per recipient Account. A
-- failed send keeps its row unsent with the last error, and later runs retry
-- it while the Alert is still open.

CREATE TABLE public.alert (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Retention (O3) removes an Inactive seafarer whole, Documents included.
    document_id bigint NOT NULL REFERENCES public.document (id) ON DELETE CASCADE,
    -- Days before expiry, as the Alert Step was when it was raised.
    step int NOT NULL CHECK (step >= 0),
    expiry_date date NOT NULL,
    raised_at timestamptz NOT NULL DEFAULT now(),
    -- Reached together with a more urgent step, so stored but never sent.
    skipped boolean NOT NULL DEFAULT false,
    CONSTRAINT uq_alert_document_step_expiry UNIQUE (document_id, step, expiry_date)
);

CREATE INDEX idx_alert_document_expiry ON public.alert (document_id, expiry_date);

GRANT SELECT, INSERT ON public.alert TO app_backend;


CREATE TABLE public.alert_delivery (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alert_id bigint NOT NULL REFERENCES public.alert (id) ON DELETE CASCADE,
    -- Accounts are never deleted.
    recipient_id uuid NOT NULL REFERENCES public.users (id),
    attempts int NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    sent_at timestamptz,
    last_error text,
    CONSTRAINT uq_alert_delivery_alert_recipient UNIQUE (alert_id, recipient_id)
);

CREATE INDEX idx_alert_delivery_unsent ON public.alert_delivery (alert_id) WHERE sent_at IS NULL;
CREATE INDEX idx_alert_delivery_recipient_id ON public.alert_delivery (recipient_id);

-- Sending updates attempts, sent time and last error.
GRANT SELECT, INSERT, UPDATE (attempts, sent_at, last_error) ON public.alert_delivery TO app_backend;


-- One row per run. The scheduled run happens once per local date (company
-- time zone); manual runs don't count as the day's run, so the date is
-- unique among scheduled runs only.
CREATE TABLE public.daily_check_run (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    local_date date NOT NULL,
    manual boolean NOT NULL DEFAULT false,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    -- Who ran it by hand; NULL for the scheduled run.
    started_by uuid REFERENCES public.users (id),
    CONSTRAINT daily_check_run_manual_has_starter CHECK (manual = (started_by IS NOT NULL)),
    CONSTRAINT daily_check_run_finished_after_start CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE UNIQUE INDEX uq_daily_check_run_scheduled_local_date
    ON public.daily_check_run (local_date) WHERE NOT manual;
CREATE INDEX idx_daily_check_run_started_by ON public.daily_check_run (started_by);

GRANT SELECT, INSERT, UPDATE (finished_at) ON public.daily_check_run TO app_backend;


-- Deny-all RLS (ADR 0001), as in the baseline.
DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY['alert', 'alert_delivery', 'daily_check_run'] LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('REVOKE ALL ON public.%I FROM anon, authenticated', t);
        EXECUTE format(
            'CREATE POLICY app_backend_access ON public.%I TO app_backend USING (true) WITH CHECK (true)',
            t
        );
    END LOOP;
END
$$;
