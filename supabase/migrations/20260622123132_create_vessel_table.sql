-- Migration 0003: create vessel table

CREATE TABLE public.vessel (
    vessel_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vessel_name text NOT NULL,
    imo_number text NOT NULL UNIQUE CHECK (imo_number ~ '^[0-9]{7}$')
);
