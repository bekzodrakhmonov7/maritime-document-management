"""Retention (FR-24, FR-25 retention; T13): the last step of the scheduled
daily check, never the manual one.

The removal itself happens in the database, in one SECURITY DEFINER function
per kind of record (migration `..._retention.sql`): Replaced Versions and the
whole records of Inactive seafarers. Old Audit Records are not removed here:
app_backend may not start that, a nightly pg_cron job of the owner does
(SR-14, ADR 0008). Each removes what
its Retention Period has passed, writes the system's *retention removal*
Audit Records and queues the removed rows' files, all in its own transaction.
A run removes at most 500 Versions and 500 seafarers; the rest go next time.

After commit the queued files are deleted from Storage. A failed delete stays
queued with its error and is retried by the next run.
"""

import logging
from dataclasses import dataclass

import asyncpg

from app.storage import FileStorage

logger = logging.getLogger(__name__)

# Per run, for Versions and for seafarers alike.
CAP = 500


@dataclass(frozen=True)
class CleanupResult:
    versions: int
    seafarers: int
    files_removed: int
    files_failed: int


async def clean_up(conn: asyncpg.Connection, storage: FileStorage, run_id: int) -> CleanupResult:
    """Remove what is due, note it on the run, then delete the queued files."""
    versions = await conn.fetchval("SELECT public.retention_remove_replaced_versions($1)", CAP)
    seafarers = await conn.fetchval("SELECT public.retention_remove_inactive_seafarers($1)", CAP)
    await conn.execute(
        """
        UPDATE public.daily_check_run
           SET retention_finished_at = now(), removed_versions = $2,
               removed_seafarers = $3
         WHERE id = $1
        """,
        run_id, versions, seafarers,
    )
    removed, failed = await remove_queued_files(conn, storage)
    return CleanupResult(versions, seafarers, removed, failed)


async def remove_queued_files(conn: asyncpg.Connection, storage: FileStorage) -> tuple[int, int]:
    """Delete every queued file from Storage; returns (removed, failed). A
    file a Version or Verification points to again is dropped from the queue
    without being deleted."""
    removed = failed = 0
    for row in await conn.fetch(
        """
        SELECT q.id, q.file_path,
               EXISTS (SELECT 1 FROM public.version v WHERE v.file_path = q.file_path)
               OR EXISTS (SELECT 1 FROM public.verification f
                           WHERE f.proof_file_path = q.file_path) AS in_use
          FROM public.file_removal q
         ORDER BY q.id
        """
    ):
        if not row["in_use"]:
            try:
                await storage.delete(row["file_path"])
            except Exception as exc:
                failed += 1
                logger.warning("Removing %s from Storage failed: %s", row["file_path"], exc)
                await conn.execute(
                    "UPDATE public.file_removal SET attempts = attempts + 1, last_error = $2 "
                    "WHERE id = $1",
                    row["id"], str(exc)[:1000],
                )
                continue
            removed += 1
        await conn.execute("DELETE FROM public.file_removal WHERE id = $1", row["id"])
    return removed, failed


async def last_cleanup(conn: asyncpg.Connection) -> dict | None:
    """The latest scheduled run's clean-up, for the Settings page."""
    row = await conn.fetchrow(
        """
        SELECT local_date, retention_finished_at AS finished_at, removed_versions AS versions,
               removed_seafarers AS seafarers
          FROM public.daily_check_run
         WHERE retention_finished_at IS NOT NULL
         ORDER BY retention_finished_at DESC
         LIMIT 1
        """
    )
    return None if row is None else dict(row)


async def last_audit_cleanup(conn: asyncpg.Connection) -> dict | None:
    """The owner job's latest removal of old Audit Records, from its own
    *retention removal* record; None while it has removed nothing."""
    row = await conn.fetchrow(
        """
        SELECT occurred_at AS removed_at, (after->>'rows')::int AS rows
          FROM public.audit_log
         WHERE action = 'retention_removal' AND target_type = 'audit_log'
         ORDER BY id DESC
         LIMIT 1
        """
    )
    return None if row is None else dict(row)
