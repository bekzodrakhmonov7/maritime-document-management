-- Migration 0007: create alert table

CREATE TABLE public.alert (
    alert_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id bigint NOT NULL REFERENCES public.document ON DELETE CASCADE,
    alert_threshold_days int NOT NULL,
    generated_at timestamptz DEFAULT now(),
    is_resolved boolean NOT NULL DEFAULT false
);

CREATE INDEX idx_alert_document_id ON public.alert(document_id);
CREATE INDEX idx_alert_is_resolved ON public.alert(is_resolved);
CREATE INDEX idx_alert_generated_at ON public.alert(generated_at);
