"""The Scope function: the seafarers this Account may see (T5, ADR 0001).

Every read of seafarer data goes through `seafarer_scope()`, so the rule
lives in one place:

- administrators see everyone;
- crewing officers see the seafarers with an upcoming or under-way
  (non-cancelled) Assignment on a vessel they are a Responsible Officer for,
  plus the Unassigned Pool (no upcoming or under-way Assignment at all,
  Inactive seafarers included);
- managers, and any Account that isn't active, see nobody. A deactivated
  officer's vessel links are kept but ignored.

A Scope is a SQL condition over a `public.seafarer` alias, so list queries
filter by it and single-record reads can tell "missing" (404) from "out of
Scope" (404, recorded as refused access) without a second query. It is taken
as of `today` in the company time zone, which it also carries for the
date-derived states (Assignment state, Current Vessel) the reads compute.
"""

from dataclasses import dataclass
from datetime import date

from app.models.auth import UserPayload


@dataclass(frozen=True)
class Scope:
    # A boolean SQL expression; `{s}` stands for the seafarer table's alias.
    _condition: str
    today: date

    def where(self, alias: str = "s") -> str:
        return f"({self._condition.format(s=alias)})"


def _not_finished(today: date) -> str:
    # Upcoming or under way, not cancelled.
    return f"a.cancelled_at IS NULL AND a.end_date >= DATE '{today.isoformat()}'"


def _unassigned_pool(today: date) -> str:
    """Seafarers with no upcoming or under-way Assignment."""
    return f"""NOT EXISTS (
        SELECT 1 FROM public.assignment a
         WHERE a.seafarer_id = {{s}}.id AND {_not_finished(today)})"""


def _on_officers_vessels(account: UserPayload, today: date) -> str:
    # The id comes from the Account row as a UUID, so it is safe to inline.
    return f"""EXISTS (
        SELECT 1 FROM public.assignment a
          JOIN public.responsible_officer ro ON ro.vessel_id = a.vessel_id
         WHERE a.seafarer_id = {{s}}.id AND {_not_finished(today)}
           AND ro.user_id = '{account.sub}'::uuid)"""


def seafarer_scope(account: UserPayload, today: date) -> Scope:
    """The seafarers `account` may see and act on, as of `today`."""
    if account.status != "active":
        return Scope("false", today)
    if account.role == "administrator":
        return Scope("true", today)
    if account.role == "crewing_officer":
        return Scope(
            f"{_unassigned_pool(today)} OR {_on_officers_vessels(account, today)}", today
        )
    return Scope("false", today)
