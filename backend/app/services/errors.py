"""The refusals services raise; routers turn them into HTTP answers."""


class NotFound(Exception):
    pass


class Conflict(Exception):
    """The change clashes with existing data or the row's current state."""


class Invalid(Exception):
    """The change breaks a rule of the data itself (e.g. depends-on)."""


class OutOfScope(Exception):
    """The record exists but is outside the caller's Scope (answered as 404)."""

    def __init__(self, target_type: str, target_id: object, seafarer_id: int | None) -> None:
        super().__init__(target_type, target_id)
        self.target_type = target_type
        self.target_id = target_id
        self.seafarer_id = seafarer_id


class NotResponsible(Exception):
    """A crewing officer acting on a vessel they aren't a Responsible Officer
    for (answered as 403 and recorded as refused access)."""
