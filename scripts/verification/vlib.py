"""Shared helpers for the Chapter 4 black-box checks (scripts/verification/*).

Talks to the running API over HTTP only (default http://127.0.0.1:8000) and to
the local database as the table owner, for arranging accounts and reading the
Audit Log. Never imports the app. Evidence goes to docs/ch4-evidence/<check>/
of the main checkout (EVIDENCE_DIR overrides), with tokens and passwords masked.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import jwt

ROOT = Path(__file__).resolve().parents[2]


def _env() -> dict[str, str]:
    values: dict[str, str] = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                values[k.strip()] = v.strip()
    values.update({k: v for k, v in os.environ.items() if k in values or k.startswith("V_")})
    return values


ENV = _env()
API = os.environ.get("V_API", "http://127.0.0.1:8000")
OWNER_URL = ENV.get("OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres")
APP_DB_URL = "postgresql://app_backend:app_backend_dev@127.0.0.1:54322/postgres"
JWT_SECRET = ENV["SUPABASE_JWT_SECRET"]
SUPABASE_URL = ENV.get("SUPABASE_URL", "http://127.0.0.1:54321")
ANON_KEY = ENV.get("SUPABASE_ANON_KEY", "")
MAILPIT = os.environ.get("V_MAILPIT", "http://127.0.0.1:54324")
EVIDENCE = Path(os.environ.get(
    "EVIDENCE_DIR",
    ROOT.parent / "maritime-document-management" / "docs" / "ch4-evidence",
))


def commit() -> str:
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True).stdout.strip()


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- masking -----------------------------------------------------------------------

_SECRET_KEYS = re.compile(r"(password|token|secret|authorization|apikey|api_key|challenge|code|cookie|uri|qr_code)", re.I)
_JWT = re.compile(r"eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*")
_SIGNED = re.compile(r"(token=)[^&\"' ]+")


def mask_text(s: str) -> str:
    s = _JWT.sub("<JWT masked>", s)
    return _SIGNED.sub(r"\1<masked>", s)


def mask(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _SECRET_KEYS.search(str(k)) and isinstance(v, str) and v:
                out[k] = f"<masked {len(v)} chars>"
            else:
                out[k] = mask(v)
        return out
    if isinstance(obj, list):
        return [mask(x) for x in obj]
    if isinstance(obj, str):
        return mask_text(obj)
    return obj


# --- evidence ------------------------------------------------------------------------


class Evidence:
    """One folder per check: exchanges.jsonl (request/response pairs, masked),
    results.json (the verdict rows), audit.json (records the check produced)."""

    def __init__(self, check_id: str) -> None:
        self.id = check_id
        self.dir = EVIDENCE / check_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.started = now_utc()
        self.rows: list[dict] = []
        self._ex = open(self.dir / "exchanges.jsonl", "a", encoding="utf-8")
        self.meta = {"check": check_id, "started_utc": self.started.isoformat(),
                     "commit": commit(), "api": API, "python": sys.version.split()[0],
                     "httpx": httpx.__version__, "command": " ".join(sys.argv)}

    def exchange(self, label: str, r: httpx.Response, note: str = "") -> None:
        req = r.request
        try:
            content = req.content
        except httpx.RequestNotRead:
            content = None
        body = content[:2000] if content else b""
        try:
            req_body = mask(json.loads(body)) if body else None
        except Exception:
            req_body = f"<{len(content)} bytes {req.headers.get('content-type','')}>" if content is not None else f"<streamed {req.headers.get('content-type','')}>"
        try:
            resp_body: Any = mask(r.json())
        except Exception:
            resp_body = mask_text(r.text[:1500]) if "text" in r.headers.get("content-type", "") or not r.content else f"<{len(r.content)} bytes {r.headers.get('content-type','')}>"
        rec = {"t": now_utc().isoformat(), "label": label, "note": note,
               "request": {"method": req.method, "url": mask_text(str(req.url)),
                           "headers": mask({k: v for k, v in req.headers.items() if k.lower() in ("authorization", "content-type", "content-length", "x-forwarded-for", "transfer-encoding")}),
                           "body": req_body},
               "response": {"status": r.status_code,
                            "headers": {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "retry-after", "x-request-id", "server", "location", "content-length")},
                            "body": resp_body}}
        self._ex.write(json.dumps(rec, default=str) + "\n")
        self._ex.flush()

    def row(self, **kw: Any) -> dict:
        self.rows.append(kw)
        return kw

    def save(self, extra: dict | None = None) -> None:
        self.meta["finished_utc"] = now_utc().isoformat()
        if extra:
            self.meta.update(extra)
        (self.dir / "results.json").write_text(
            json.dumps({"meta": self.meta, "rows": self.rows}, indent=1, default=str), encoding="utf-8")
        self._ex.close()

    def write(self, name: str, content: Any) -> Path:
        p = self.dir / name
        if isinstance(content, (dict, list)):
            p.write_text(json.dumps(content, indent=1, default=str), encoding="utf-8")
        elif isinstance(content, bytes):
            p.write_bytes(content)
        else:
            p.write_text(str(content), encoding="utf-8")
        return p


# --- tokens and accounts -----------------------------------------------------------------


def make_token(user_id: uuid.UUID, *, session_id: uuid.UUID | None = None, aal: str | None = "aal2",
               email: str = "x@example.com", key: str | None = None, alg: str = "HS256",
               drop: tuple[str, ...] = (), exp_delta: timedelta = timedelta(hours=1),
               **extra: Any) -> str:
    now = now_utc()
    payload: dict[str, Any] = {"sub": str(user_id), "session_id": str(session_id or user_id),
                               "email": email, "role": "authenticated", "aud": "authenticated",
                               "iat": int(now.timestamp()), "exp": int((now + exp_delta).timestamp())}
    if aal is not None:
        payload["aal"] = aal
    payload.update(extra)
    for k in drop:
        payload.pop(k, None)
    if alg == "none":
        return jwt.encode(payload, None, algorithm="none") if hasattr(jwt, "encode") else ""
    return jwt.encode(payload, key or JWT_SECRET, algorithm=alg)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class Account:
    id: uuid.UUID
    email: str
    role: str | None
    status: str
    name: str

    @property
    def h(self) -> dict[str, str]:
        return bearer(make_token(self.id, email=self.email))


async def owner() -> asyncpg.Connection:
    return await asyncpg.connect(OWNER_URL)


async def make_account(db: asyncpg.Connection, status: str = "active", role: str | None = "administrator",
                       email: str | None = None, full_name: str = "Verification Account",
                       verified_session: bool = True) -> Account:
    """As backend/tests/conftest.py make_account: an auth.users row through the
    real sign-up trigger, a verified session whose id is the account id."""
    uid = uuid.uuid4()
    email = email or f"v-{uid.hex[:10]}@example.com"
    await db.execute(
        """INSERT INTO auth.users (id, email, encrypted_password, raw_user_meta_data,
                                   email_confirmed_at, created_at, updated_at)
           VALUES ($1, $2, 'x', jsonb_build_object('full_name', $3::text), now(), now(), now())""",
        uid, email, full_name)
    if verified_session:
        await db.execute("INSERT INTO public.verified_session (session_id, user_id) VALUES ($1, $1)", uid)
    if status != "pending":
        await db.execute("UPDATE public.users SET status = $2, role = $3 WHERE id = $1", uid, status, role)
    return Account(uid, email, role if status != "pending" else None, status, full_name)


async def audit_since(db: asyncpg.Connection, since: datetime, **eq: Any) -> list[dict]:
    where = ["occurred_at >= $1"]
    args: list[Any] = [since]
    for k, v in eq.items():
        args.append(v)
        where.append(f"{k} = ${len(args)}")
    rows = await db.fetch(f"SELECT * FROM public.audit_log WHERE {' AND '.join(where)} ORDER BY id", *args)
    return [dict(r) for r in rows]


async def max_audit_id(db: asyncpg.Connection) -> int:
    return await db.fetchval("SELECT coalesce(max(id),0) FROM public.audit_log")


async def audit_after(db: asyncpg.Connection, after_id: int) -> list[dict]:
    rows = await db.fetch("SELECT * FROM public.audit_log WHERE id > $1 ORDER BY id", after_id)
    return [dict(r) for r in rows]


def client(timeout: float = 60) -> httpx.Client:
    return httpx.Client(base_url=API, timeout=timeout)


def aclient(timeout: float = 60) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API, timeout=timeout)


# --- real sign-in through the API (password + TOTP) -----------------------------------------


def mailpit_code(email: str, after: float, timeout: float = 30) -> str:
    """The newest 6-8 digit code e-mailed to `email` after `after` (epoch s)."""
    deadline = time.time() + timeout
    with httpx.Client(base_url=MAILPIT, timeout=10) as m:
        while time.time() < deadline:
            msgs = m.get("/api/v1/search", params={"query": f"to:{email}"}).json().get("messages", [])
            for msg in msgs:
                created = datetime.fromisoformat(msg["Created"].replace("Z", "+00:00")).timestamp()
                if created >= after - 2:
                    body = m.get(f"/api/v1/message/{msg['ID']}").json()
                    text = body.get("Text") or body.get("HTML") or ""
                    found = re.findall(r"\b(\d{6,8})\b", text)
                    if found:
                        return found[0]
            time.sleep(1)
    raise TimeoutError(f"no code for {email}")


def totp_now(secret: str, offset: int = 0) -> str:
    import pyotp
    return pyotp.TOTP(secret).at(time.time() + offset)


def wait_fresh_totp_window() -> None:
    """Avoid reusing a TOTP code across 30 s windows (GoTrue refuses reuse)."""
    left = 30 - (time.time() % 30)
    if left < 5:
        time.sleep(left + 1)
