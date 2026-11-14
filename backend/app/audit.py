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
    REQUIREMENT_ADDED = "requirement_added"
    REQUIREMENT_REMOVED = "requirement_removed"
    REQUIREMENT_EXCEPTION_CREATED = "requirement_exception_created"
    REQUIREMENT_EXCEPTION_EDITED = "requirement_exception_edited"
    REQUIREMENT_EXCEPTION_DELETED = "requirement_exception_deleted"
    SEAFARER_CREATED = "seafarer_created"
    SEAFARER_EDITED = "seafarer_edited"
    SEAFARER_SET_INACTIVE = "seafarer_set_inactive"
    SEAFARER_REACTIVATED = "seafarer_reactivated"
    ASSIGNMENT_CREATED = "assignment_created"
    ASSIGNMENT_EDITED = "assignment_edited"
    ASSIGNMENT_CANCELLED = "assignment_cancelled"
    RESPONSIBLE_OFFICER_ADDED = "responsible_officer_added"
    RESPONSIBLE_OFFICER_REMOVED = "responsible_officer_removed"
    VERSION_UPLOADED = "version_uploaded"
    UPLOAD_REJECTED = "upload_rejected"
    FILE_URL_ISSUED = "file_url_issued"
    SETTINGS_CHANGED = "settings_changed"
    AUDIT_SEARCHED = "audit_searched"
    AUDIT_EXPORTED = "audit_exported"
    # Written by the auth.audit_log_entries trigger, not by the API.
    LOGIN_SUCCEEDED = "login_succeeded"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    ACCESS_REFUSED = "access_refused"


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
    return request_audit_context(request, user.sub, user.email, user.role)


def request_audit_context(
    request: Request,
    actor_id: UUID | None,
    actor_email: str | None,
    actor_role: str | None,
) -> AuditContext:
    """The actor as given, plus the request's IP and id."""
    return AuditContext(
        actor_id=actor_id,
        actor_email=actor_email,
        actor_role=actor_role,
        ip=client_ip(request),
        request_id=getattr(request.state, "request_id", None),
    )


def client_ip(request: Request) -> str | None:
    host = request.client.host if request.client else None
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
