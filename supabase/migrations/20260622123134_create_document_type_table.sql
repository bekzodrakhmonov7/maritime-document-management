-- Migration 0005: create document_type table

CREATE TABLE public.document_type (
    doc_type_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type_name text NOT NULL UNIQUE,
    is_mandatory boolean NOT NULL DEFAULT false
);
