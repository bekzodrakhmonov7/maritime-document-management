-- Migration 0004: create seafarer table

CREATE TABLE public.seafarer (
    seafarer_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vessel_id bigint REFERENCES public.vessel(vessel_id) ON DELETE RESTRICT,
    first_name text NOT NULL,
    last_name text NOT NULL,
    rank text NOT NULL
);

CREATE INDEX idx_seafarer_vessel_id ON public.seafarer(vessel_id);
