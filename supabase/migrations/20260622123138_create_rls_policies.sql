-- Migration 0009: enable RLS and create policies

-- Enable and force RLS on all tables
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;

ALTER TABLE public.vessel ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.vessel FORCE ROW LEVEL SECURITY;

ALTER TABLE public.seafarer ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.seafarer FORCE ROW LEVEL SECURITY;

ALTER TABLE public.document_type ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document_type FORCE ROW LEVEL SECURITY;

ALTER TABLE public.document ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.document FORCE ROW LEVEL SECURITY;

ALTER TABLE public.alert ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.alert FORCE ROW LEVEL SECURITY;


-- ==================== SELECT policies (all authenticated) ====================
CREATE POLICY "allow_select_users"
    ON public.users FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "allow_select_vessel"
    ON public.vessel FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "allow_select_seafarer"
    ON public.seafarer FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "allow_select_document_type"
    ON public.document_type FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "allow_select_document"
    ON public.document FOR SELECT
    TO authenticated
    USING (true);

CREATE POLICY "allow_select_alert"
    ON public.alert FOR SELECT
    TO authenticated
    USING (true);


-- ==================== INSERT policies ====================
-- Config tables: only admin can INSERT
CREATE POLICY "allow_insert_users_admin"
    ON public.users FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_insert_vessel_admin"
    ON public.vessel FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_insert_document_type_admin"
    ON public.document_type FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

-- Crew/doc tables: crewing_officer and admin can INSERT
CREATE POLICY "allow_insert_seafarer_crew"
    ON public.seafarer FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_insert_document_crew"
    ON public.document FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_insert_alert_crew"
    ON public.alert FOR INSERT
    TO authenticated
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));


-- ==================== UPDATE policies ====================
-- Config tables: only admin can UPDATE
CREATE POLICY "allow_update_users_admin"
    ON public.users FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator')
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_update_vessel_admin"
    ON public.vessel FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator')
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_update_document_type_admin"
    ON public.document_type FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator')
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

-- Crew/doc tables: crewing_officer and admin can UPDATE
CREATE POLICY "allow_update_seafarer_crew"
    ON public.seafarer FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'))
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_update_document_crew"
    ON public.document FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'))
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_update_alert_crew"
    ON public.alert FOR UPDATE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'))
    WITH CHECK ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));


-- ==================== DELETE policies ====================
-- Config tables: only admin can DELETE
CREATE POLICY "allow_delete_users_admin"
    ON public.users FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_delete_vessel_admin"
    ON public.vessel FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

CREATE POLICY "allow_delete_document_type_admin"
    ON public.document_type FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) = 'administrator');

-- Crew/doc tables: crewing_officer and admin can DELETE
CREATE POLICY "allow_delete_seafarer_crew"
    ON public.seafarer FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_delete_document_crew"
    ON public.document FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

CREATE POLICY "allow_delete_alert_crew"
    ON public.alert FOR DELETE
    TO authenticated
    USING ((SELECT role FROM public.users WHERE id = (SELECT auth.uid())) IN ('administrator', 'crewing_officer'));

