-- Baseline 3/4: storage.
-- A private bucket for document files. There are no storage policies, so
-- anon and authenticated can't reach it; files are served only through
-- short-lived signed URLs that the API issues (ADR 0001).

INSERT INTO storage.buckets (id, name, public)
VALUES ('crew-documents', 'crew-documents', false)
ON CONFLICT (id) DO NOTHING;
