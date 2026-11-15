-- The file ceiling is 4 MB (ADR-0003). Uploads go through the API on Vercel,
-- which refuses request bodies over 4.5 MB, so a larger setting would be
-- silently unusable. Range 1-4, default 4; any stored value above 4 is lowered.

UPDATE public.settings SET max_file_size_mb = 4 WHERE max_file_size_mb > 4;

ALTER TABLE public.settings
    DROP CONSTRAINT settings_max_file_size_mb_check,
    ADD CONSTRAINT settings_max_file_size_mb_check CHECK (max_file_size_mb BETWEEN 1 AND 4),
    ALTER COLUMN max_file_size_mb SET DEFAULT 4;
