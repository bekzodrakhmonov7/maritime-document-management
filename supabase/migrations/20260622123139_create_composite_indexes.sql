-- Migration 0010: create composite and partial indexes

-- Composite index on document status + expiry_date
CREATE INDEX idx_document_status_expiry ON public.document(status, expiry_date);

-- Partial index for active document statuses
CREATE INDEX idx_document_active_status ON public.document(status, expiry_date)
    WHERE status IN ('verified', 'expiring_soon');
