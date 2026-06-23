-- Migration: add 'valid' to document status CHECK constraint
-- Enables the Daily Document Expiry Check state machine to set status='valid'
-- for verified documents with > 90 days remaining.

ALTER TABLE public.document DROP CONSTRAINT IF EXISTS document_status_check;

ALTER TABLE public.document
    ADD CONSTRAINT document_status_check
    CHECK (status IN ('pending', 'verified', 'valid', 'rejected', 'expiring_soon', 'expired'));
