-- Migration 0006: create document table

CREATE TABLE public.document (
    document_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    seafarer_id bigint NOT NULL REFERENCES public.seafarer ON DELETE CASCADE,
    doc_type_id bigint NOT NULL REFERENCES public.document_type ON DELETE RESTRICT,
    document_number text NOT NULL,
    issue_date date NOT NULL,
    expiry_date date NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'verified', 'rejected', 'expiring_soon', 'expired')),
    file_path text NOT NULL,
    uploaded_by uuid REFERENCES public.users(id),
    created_at timestamptz DEFAULT now(),
    CONSTRAINT chk_expiry_after_issue CHECK (expiry_date > issue_date)
);

CREATE INDEX idx_document_seafarer_id ON public.document(seafarer_id);
CREATE INDEX idx_document_doc_type_id ON public.document(doc_type_id);
CREATE INDEX idx_document_status ON public.document(status);
CREATE INDEX idx_document_expiry_date ON public.document(expiry_date);
