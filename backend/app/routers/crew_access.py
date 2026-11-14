"""The caller's access to crew data, as one dependency.

Administrators and crewing officers pass the role check; managers get 403.
The Scope is taken as of today in the company time zone, read per request,
so a changed time zone applies at once.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import asyncpg
from fastapi import Depends, HTTPException, status

from app.deps import account_refused, get_db, require_role
from app.models.auth import UserPayload
from app.refused_access import OutOfScope
from app.scope import Scope, seafarer_scope
from app.services import errors
from app.services.settings import company_today

crew_staff = require_role("administrator", "crewing_officer")


@dataclass(frozen=True)
class CrewAccess:
    user: UserPayload
    scope: Scope


async def get_crew_access(
    user: UserPayload = Depends(crew_staff), db: asyncpg.Connection = Depends(get_db)
) -> CrewAccess:
    return CrewAccess(user=user, scope=seafarer_scope(user, await company_today(db)))


@contextmanager
def errors_as_http() -> Iterator[None]:
    """Turn the services' refusals into HTTP answers. Out of Scope looks like a
    missing record (404) but is recorded, as is a missing responsibility (403)."""
    try:
        yield
    except errors.NotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    except errors.OutOfScope as exc:
        raise OutOfScope(exc.target_type, exc.target_id, seafarer_id=exc.seafarer_id)
    except errors.NotResponsible as exc:
        raise account_refused("not_responsible", str(exc))
    except errors.Conflict as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except errors.Invalid as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))
