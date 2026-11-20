"""Shared path parameter types."""

from typing import Annotated

from fastapi import Path

# A database id: a positive bigint. Anything outside is a 422, never a
# database error (SR-16).
MAX_ID = 2**63 - 1
Id = Annotated[int, Path(ge=1, le=MAX_ID)]
