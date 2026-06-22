from uuid import UUID

from pydantic import BaseModel


class UserPayload(BaseModel):
    sub: UUID
    email: str
    role: str
