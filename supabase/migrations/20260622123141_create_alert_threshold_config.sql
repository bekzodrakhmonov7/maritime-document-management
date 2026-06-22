-- Migration 0012: create alert_threshold_config table, seed, and RLS

CREATE TABLE public.alert_threshold_config (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    days_90 int NOT NULL DEFAULT 90,
    days_60 int NOT NULL DEFAULT 60,
    days_30 int NOT NULL DEFAULT 30,
    updated_by uuid REFERENCES public.users(id),
    updated_at timestamptz DEFAULT now()
);

-- Seed one default row
INSERT INTO public.alert_threshold_config (days_90, days_60, days_30)
VALUES (90, 60, 30);

-- Enable and force RLS on alert_threshold_config
ALTER TABLE public.alert_threshold_config ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert_threshold_config FORCE ROW LEVEL SECURITY;

-- SELECT policy
CREATE POLICY "allow_select_alert_threshold_config"
    ON public.alert_threshold_config FOR SELECT
    TO authenticated
    USING (true);

-- INSERT policy: admin only
CREATE POLICY "allow_insert_alert_threshold_config_admin"
    ON public.alert_threshold_config FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

-- UPDATE policy: admin only
CREATE POLICY "allow_update_alert_threshold_config_admin"
    ON public.alert_threshold_config FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator')
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

-- DELETE policy: admin only
CREATE POLICY "allow_delete_alert_threshold_config_admin"
    ON public.alert_threshold_config FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');
