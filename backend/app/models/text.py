"""Text the API accepts: never a NUL byte (F-02).

PostgreSQL cannot store `\\x00` in text, so a NUL reaching the database is a
500. Every text field of a request model and every free-text query parameter
carries `NO_NUL`, which answers the usual 422 naming the field instead.

Put it after any `StringConstraints` (or `Query(...)`) in the `Annotated`, so
their messages stay "String should have at most N characters".
"""

from typing import Annotated, Any

from pydantic import AfterValidator, StringConstraints


def _refuse_nul(value: str) -> str:
    if "\x00" in value:
        raise ValueError("must not contain a NUL character")
    return value


NO_NUL = AfterValidator(_refuse_nul)

# Any text with no further constraint.
Text = Annotated[str, NO_NUL]


def TrimmedText(max_length: int) -> Any:  # noqa: N802 - used as a type
    """Text trimmed of surrounding spaces, 1 to `max_length` characters, no NUL."""
    return Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=max_length), NO_NUL
    ]
