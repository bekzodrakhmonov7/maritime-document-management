"""Pure domain computation over plain rows the queries fetch (no SQL views).

Readiness, the dashboard, the daily check and the reports share these
functions; later slices add theirs here.
"""

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from typing import Literal

Effect = Literal["add", "remove"]


@dataclass(frozen=True)
class VesselRef:
    id: int
    flag: str


@dataclass(frozen=True)
class RequirementException:
    """An add or remove of one Document Type for one vessel or one flag
    (exactly one of the two), for one Position or, with none, for all."""

    document_type_id: int
    effect: Effect
    vessel_id: int | None = None
    flag: str | None = None
    position_id: int | None = None
    id: int | None = None


# --- Requirements (FR-08, T2) ---------------------------------------------------


def deciding_exceptions(
    position_id: int, vessel: VesselRef | None, exceptions: Iterable[RequirementException]
) -> dict[int, RequirementException]:
    """For each Document Type an exception speaks about for this pair, the one
    that decides it: vessel beats flag, then Position-specific beats
    all-positions. With no vessel, none apply."""
    if vessel is None:
        return {}

    def rank(e: RequirementException) -> tuple[int, int] | None:
        if e.position_id is not None and e.position_id != position_id:
            return None
        if e.vessel_id is not None:
            scope = 2 if e.vessel_id == vessel.id else None
        else:
            scope = 1 if e.flag == vessel.flag else None
        if scope is None:
            return None
        return scope, 1 if e.position_id is not None else 0

    deciding: dict[int, tuple[tuple[int, int], RequirementException]] = {}
    for e in exceptions:
        r = rank(e)
        if r is None:
            continue
        held = deciding.get(e.document_type_id)
        if held is None or r > held[0]:
            deciding[e.document_type_id] = (r, e)
    return {type_id: e for type_id, (_, e) in deciding.items()}


def required_set(
    position_id: int,
    vessel: VesselRef | None,
    matrix: Iterable[tuple[int, int]],
    exceptions: Iterable[RequirementException],
    retired_types: Collection[int],
) -> set[int]:
    """The Document Types required for a Position, on a vessel or ashore.

    Starts from the matrix rows (position id, document type id) for the
    Position, then applies flag exceptions, then vessel exceptions; the most
    specific one decides each type. Retired types are never required, and an
    Endorsement's certificate is never followed either way.
    """
    required = {type_id for p, type_id in matrix if p == position_id}
    for type_id, e in deciding_exceptions(position_id, vessel, exceptions).items():
        if e.effect == "add":
            required.add(type_id)
        else:
            required.discard(type_id)
    return required - set(retired_types)
