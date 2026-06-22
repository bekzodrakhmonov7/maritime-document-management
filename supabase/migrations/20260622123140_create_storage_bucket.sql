-- Migration 0011: create storage bucket and RLS

-- Create private storage bucket for crew documents
INSERT INTO storage.buckets (id, name, public)
VALUES ('crew-documents', 'crew-documents', false)
ON CONFLICT (id) DO NOTHING;


-- Allow authenticated users to upload to crew-documents bucket
CREATE POLICY "allow_upload_crew_documents"
    ON storage.objects FOR INSERT
    TO authenticated
    WITH CHECK (bucket_id = 'crew-documents');

-- Allow authenticated users to select from crew-documents bucket
CREATE POLICY "allow_select_crew_documents"
    ON storage.objects FOR SELECT
    TO authenticated
    USING (bucket_id = 'crew-documents');

-- Allow authenticated users to update in crew-documents bucket
CREATE POLICY "allow_update_crew_documents"
    ON storage.objects FOR UPDATE
    TO authenticated
    USING (bucket_id = 'crew-documents')
    WITH CHECK (bucket_id = 'crew-documents');

-- Allow authenticated users to delete from crew-documents bucket
CREATE POLICY "allow_delete_crew_documents"
    ON storage.objects FOR DELETE
    TO authenticated
    USING (bucket_id = 'crew-documents');
