-- A scheduled daily check run that never finished can be reclaimed (NFR-03).
--
-- If a run dies mid-send its row keeps finished_at NULL, and the unique local
-- date used to block every later wake-up that day. run_if_due now takes such
-- a row over once its lease has run out, restarting it by moving started_at to
-- the take-over time (so started_at is when the current attempt began). The
-- unique (Document, step, expiry date) still keeps a take-over from raising an
-- Alert twice.

GRANT UPDATE (started_at) ON public.daily_check_run TO app_backend;
