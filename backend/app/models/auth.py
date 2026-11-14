from typing import Literal
from uuid import UUID

from pydantic import BaseModel

AccountStatus = Literal["pending", "active", "deactivated"]
Role = Literal["administrator", "crewing_officer", "manager"]


class UserPayload(BaseModel):
    """The signed-in Account, read from public.users on every request."""

    sub: UUID
    email: str
    full_name: str = ""
    status: AccountStatus
    role: Role | None = None
