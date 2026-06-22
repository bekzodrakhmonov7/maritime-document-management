-- Migration 0002: create public.users table

CREATE TABLE public.users (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    full_name text NOT NULL,
    role text NOT NULL CHECK (role IN ('administrator', 'crewing_officer')),
    created_at timestamptz DEFAULT now()
);
