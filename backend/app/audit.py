"""The one audit helper (T7, ADR 0002).

Every change writes its Audit Record through `record()`, on the same
connection and inside the same transaction as the change, so both succeed or
fail together. Actions come from the fixed list below; later slices add theirs.
"""

import ipaddress
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import Depends, Request

from app.deps import get_current_user
from app.models.auth import UserPayload


class AuditAction(StrEnum):
    ACCOUNT_APPROVED = "account_approved"
    ACCOUNT_ROLE_CHANGED = "account_role_changed"
    ACCOUNT_DEACTIVATED = "account_deactivated"
    ACCOUNT_REACTIVATED = "account_reactivated"
    VESSEL_CREATED = "vessel_created"
    VESSEL_EDITED = "vessel_edited"
    VESSEL_DEACTIVATED = "vessel_deactivated"
    VESSEL_REACTIVATED = "vessel_reactivated"
    POSITION_CREATED = "position_created"
    POSITION_EDITED = "position_edited"
    POSITION_RETIRED = "position_retired"
    POSITION_UNRETIRED = "position_unretired"
    POSITION_DELETED = "position_deleted"
    DOCUMENT_TYPE_CREATED = "document_type_created"
    DOCUMENT_TYPE_EDITED = "document_type_edited"
    DOCUMENT_TYPE_RETIRED = "document_type_retired"
    DOCUMENT_TYPE_UNRETIRED = "document_type_unretired"
    DOCUMENT_TYPE_DELETED = "document_type_deleted"


Outcome = Literal["succeeded", "refused"]

SYSTEM = "system"


@dataclass(frozen=True)
class AuditContext:
    """Who is acting, and from where. Copied into every record it writes."""

    actor_id: UUID | None
    actor_email: str | None
    actor_role: str | None
    ip: str | None = None
    request_id: str | None = None

    @classmethod
    def system(cls) -> "AuditContext":
        """For backend commands and scheduled jobs: no Account acts."""
        return cls(actor_id=None, actor_email=None, actor_role=SYSTEM)


def audit_context_for(request: Request, user: UserPayload) -> AuditContext:
    return AuditContext(
        actor_id=user.sub,
        actor_email=user.email,
        actor_role=user.role,
        ip=_ip(request.client.host if request.client else None),
        request_id=getattr(request.state, "request_id", None),
    )


def _ip(host: str | None) -> str | None:
    try:
        return str(ipaddress.ip_address(host)) if host else None
    except ValueError:
        return None


async def get_audit_context(
    request: Request, user: UserPayload = Depends(get_current_user)
) -> AuditContext:
    return audit_context_for(request, user)


def changed_fields(
    before: dict[str, Any], after: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Keep only the fields whose value differs."""
    keys = [k for k in after if before.get(k) != after.get(k)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


def _json(value: dict[str, Any] | None) -> str | None:
    return None if value is None else json.dumps(value, default=str)


async def record(
    conn: asyncpg.Connection,
    ctx: AuditContext,
    action: AuditAction,
    *,
    target_type: str | None = None,
    target_id: object | None = None,
    seafarer_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str | None = None,
    outcome: Outcome = "succeeded",
) -> None:
    """Write one Audit Record in the caller's open transaction."""
    if not conn.is_in_transaction():
        raise RuntimeError("Audit Records are written inside the change's transaction")
    await conn.execute(
        """
        INSERT INTO public.audit_log
            (actor_id, actor_email, actor_role, action, outcome, target_type, target_id,
             seafarer_id, before, after, reason, ip, request_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10::jsonb, $11, $12::inet, $13)
        """,
        ctx.actor_id,
        ctx.actor_email,
        ctx.actor_role,
        AuditAction(action).value,
        outcome,
        target_type,
        None if target_id is None else str(target_id),
        seafarer_id,
        _json(before),
        _json(after),
        reason,
        ctx.ip,
        ctx.request_id,
    )
