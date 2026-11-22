"""The caller's access to crew data, as one dependency.

Administrators and crewing officers pass the role check; managers get 403.
The Scope is taken as of today in the company time zone, read per request,
so a changed time zone applies at once.
"""

from dataclasses import dataclass

import asyncpg
from fastapi import Depends, Request

from app.audit import AuditContext, audit_context_for
from app.deps import get_db, require_role
from app.models.auth import UserPayload
from app.scope import Scope, seafarer_scope
from app.services.settings import company_today

crew_staff = require_role("administrator", "crewing_officer")


@dataclass(frozen=True)
class CrewAccess:
    user: UserPayload
    scope: Scope
    ctx: AuditContext


async def get_crew_access(
    request: Request,
    user: UserPayload = Depends(crew_staff),
    db: asyncpg.Connection = Depends(get_db),
) -> CrewAccess:
    return CrewAccess(
        user=user,
        scope=seafarer_scope(user, await company_today(db)),
        ctx=audit_context_for(request, user),
    )
