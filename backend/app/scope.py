"""The Scope function: the seafarers this Account may see (T5, ADR 0001).

Every read of seafarer data goes through `seafarer_scope()`, so the rule
lives in one place:

- administrators see everyone;
- crewing officers see the Seafarers with an upcoming or under-way Assignment
  on a vessel they are a Responsible Officer for, plus the Unassigned Pool.
  Until Assignments exist (S6) nobody has one, so the Pool is everyone;
- managers see nobody (they get fleet totals only).

A Scope is a SQL condition over a `public.seafarer` alias, so list queries
filter by it and single-record reads can tell "missing" (404) from "out of
Scope" (404, recorded as refused access) without a second query.
"""

from dataclasses import dataclass

from app.models.auth import UserPayload


@dataclass(frozen=True)
class Scope:
    # A boolean SQL expression; `{s}` stands for the seafarer table's alias.
    _condition: str

    def where(self, alias: str = "s") -> str:
        return f"({self._condition.format(s=alias)})"


EVERYONE = Scope("true")
NOBODY = Scope("false")
# The Unassigned Pool: seafarers with no upcoming or under-way Assignment.
# No Assignments exist yet, so that is every seafarer; S6 narrows it and adds
# the seafarers booked onto the officer's own vessels.
UNASSIGNED_POOL = Scope("true")


def seafarer_scope(account: UserPayload) -> Scope:
    """The seafarers `account` may see and act on."""
    if account.status != "active":
        return NOBODY
    if account.role == "administrator":
        return EVERYONE
    if account.role == "crewing_officer":
        return UNASSIGNED_POOL
    return NOBODY
