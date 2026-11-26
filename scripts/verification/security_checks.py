"""Chapter 4 black-box security checks (plan section 6), against the running
API on V_API (default http://127.0.0.1:8000) and the local Supabase stack.

    uv run python scripts/verification/security_checks.py c1 [c4 c5 c6 ...]

Each check writes docs/ch4-evidence/C-<id>/{exchanges.jsonl,results.json,audit.json}.
Every request carries a unique X-Request-ID, so the Audit Log records a request
produced are found by request_id, never by time windows alone.
"""

from __future__ import annotations

import asyncio
import base64
import csv
import io
import json
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import httpx

import d1 as d1mod
import vlib

HERE = Path(__file__).resolve().parent


def rid() -> str:
    return "v" + uuid.uuid4().hex[:20]


def routes(c: httpx.Client) -> list[tuple[str, str]]:
    spec = c.get("/openapi.json").json()
    out = []
    for p, ops in spec["paths"].items():
        if p.startswith("/api/auth/") or p == "/health":
            continue
        for m in ops:
            out.append((m.upper(), p))
    return sorted(out, key=lambda x: (x[1], x[0]))


def fill(path: str, values: dict[str, object]) -> str:
    return re.sub(r"\{([a-z_]+)\}", lambda m: str(values.get(m.group(1), 1)), path)


async def audit_by_request(db, request_ids: list[str]) -> dict[str, list[dict]]:
    rows = await db.fetch("SELECT * FROM public.audit_log WHERE request_id = ANY($1::text[]) ORDER BY id", request_ids)
    out: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        out[r["request_id"]].append(dict(r))
    return out


def b64url(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


# ---------------------------------------------------------------------------------------
# C1 WSTG-ATHN-04: every protected route with every bad token
# ---------------------------------------------------------------------------------------


def direct_supabase_session(email: str, password: str) -> dict:
    """Sign up and sign in at local Supabase Auth with the anon key, bypassing the backend."""
    h = {"apikey": vlib.ANON_KEY, "Content-Type": "application/json"}
    with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
        su = s.post("/auth/v1/signup", json={"email": email, "password": password}, headers=h)
        return {"signup_status": su.status_code, "signup": su.json() if su.content else None}


def direct_password_grant(email: str, password: str) -> httpx.Response:
    h = {"apikey": vlib.ANON_KEY, "Content-Type": "application/json"}
    with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
        return s.post("/auth/v1/token", params={"grant_type": "password"},
                      json={"email": email, "password": password}, headers=h)


def direct_totp_aal2(access_token: str) -> tuple[str | None, dict]:
    """Enrol and verify TOTP directly at Supabase Auth: an aal2 session the backend never verified."""
    import pyotp
    h = {"apikey": vlib.ANON_KEY, "Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
    info: dict = {}
    with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
        e = s.post("/auth/v1/factors", json={"factor_type": "totp", "friendly_name": "direct"}, headers=h)
        info["enrol_status"] = e.status_code
        if e.status_code != 200:
            info["enrol_body"] = e.text[:300]
            return None, info
        fid, secret = e.json()["id"], e.json()["totp"]["secret"]
        ch = s.post(f"/auth/v1/factors/{fid}/challenge", headers=h)
        info["challenge_status"] = ch.status_code
        v = s.post(f"/auth/v1/factors/{fid}/verify",
                   json={"challenge_id": ch.json()["id"], "code": pyotp.TOTP(secret).now()}, headers=h)
        info["verify_status"] = v.status_code
        if v.status_code != 200:
            return None, info
        return v.json()["access_token"], info


async def c1() -> None:
    ev = vlib.Evidence("C1")
    db = await vlib.owner()
    acct = await vlib.make_account(db, role="administrator", email=f"c1-{uuid.uuid4().hex[:6]}@example.com")
    good = vlib.make_token(acct.id, email=acct.email)
    head, payload, sig = good.split(".")
    flipped = sig[:-2] + ("AA" if sig[-2:] != "AA" else "BB")
    altered_payload = b64url({**json.loads(base64.urlsafe_b64decode(payload + "==")), "sub": str(uuid.uuid4())})
    variants: dict[str, dict[str, str] | None] = {
        "no_header": None,
        "empty_header": {"Authorization": ""},
        "wrong_signature": vlib.bearer(f"{head}.{payload}.{flipped}"),
        "altered_payload": vlib.bearer(f"{head}.{altered_payload}.{sig}"),
        "alg_none": vlib.bearer(f"{b64url({'alg': 'none', 'typ': 'JWT'})}.{payload}."),
        "hs256_wrong_key": vlib.bearer(vlib.make_token(acct.id, key="wrong-key-wrong-key-wrong-key-wrong-key")),
        "expired": vlib.bearer(vlib.make_token(acct.id, exp_delta=timedelta(minutes=-5))),
        "no_exp": vlib.bearer(vlib.make_token(acct.id, drop=("exp",))),
        "no_sub": vlib.bearer(vlib.make_token(acct.id, drop=("sub",))),
        "wrong_aud": vlib.bearer(vlib.make_token(acct.id, aud="service")),
        "aal1": vlib.bearer(vlib.make_token(acct.id, aal="aal1")),
        "no_aal": vlib.bearer(vlib.make_token(acct.id, aal=None)),
        "aal2_session_never_verified": vlib.bearer(vlib.make_token(acct.id, session_id=uuid.uuid4())),
    }
    # A session straight from local Supabase Auth with the public key.
    email, pw = f"c1direct-{uuid.uuid4().hex[:6]}@example.com", "Unusual-Direct-Pass-9431"
    info = direct_supabase_session(email, pw)
    await db.execute("UPDATE auth.users SET email_confirmed_at = now() WHERE email = $1", email)
    uid = await db.fetchval("SELECT id FROM auth.users WHERE email = $1", email)
    # Make that person an active administrator, so only the session decides.
    await db.execute("UPDATE public.users SET status='active', role='administrator' WHERE id=$1", uid)
    g = direct_password_grant(email, pw)
    info["password_grant_status"] = g.status_code
    if g.status_code == 200:
        tok = g.json()["access_token"]
        info["direct_token_header"] = json.loads(base64.urlsafe_b64decode(tok.split(".")[0] + "=="))
        info["direct_token_aal"] = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "==")).get("aal")
        variants["direct_supabase_password_grant"] = vlib.bearer(tok)
        aal2, mfa = direct_totp_aal2(tok)
        info["direct_mfa"] = mfa
        if aal2:
            variants["direct_supabase_aal2_totp"] = vlib.bearer(aal2)
    ev.write("direct_supabase.json", vlib.mask(info))

    with vlib.client() as c:
        rts = routes(c)
        ev.write("routes.json", rts)
        sent: list[tuple[str, str, str, str, int]] = []
        for vname, hdr in variants.items():
            for m, p in rts:
                r_id = rid()
                headers = {"X-Request-ID": r_id, **(hdr or {})}
                r = c.request(m, fill(p, {}), headers=headers,
                              json={} if m in ("POST", "PUT") else None)
                sent.append((vname, m, p, r_id, r.status_code))
                if p in ("/api/me", "/api/settings") or r.status_code != 401:
                    ev.exchange(f"{vname} {m} {p}", r)
        # Control: the good token reaches /api/me.
        ctl = c.get("/api/me", headers=vlib.bearer(good))
        ev.exchange("control good token GET /api/me", ctl)
    recs = await audit_by_request(db, [s[3] for s in sent])
    summary = {}
    for vname in variants:
        rows = [s for s in sent if s[0] == vname]
        statuses = Counter(s[4] for s in rows)
        nrec = Counter(len(recs.get(s[3], [])) for s in rows)
        reasons = Counter(r["reason"] for s in rows for r in recs.get(s[3], []))
        actions = Counter(r["action"] for s in rows for r in recs.get(s[3], []))
        expect_record = vname not in ("no_header", "empty_header")
        ok401 = statuses == Counter({401: len(rows)})
        okrec = nrec == Counter({1 if expect_record else 0: len(rows)})
        summary[vname] = ev.row(variant=vname, routes=len(rows), statuses=dict(statuses),
                                records_per_request=dict(nrec), actions=dict(actions), reasons=dict(reasons),
                                all_401=ok401, records_as_expected=okrec,
                                non401=[f"{s[1]} {s[2]}={s[4]}" for s in rows if s[4] != 401][:20])
    ev.write("audit.json", {k: v for k, v in list(recs.items())[:40]})
    ev.write("summary.json", summary)
    ev.save({"control_status": ctl.status_code, "routes": len(rts)})
    await db.close()
    for k, v in summary.items():
        print(f"{k:32s} 401-all={v['all_401']} rec-ok={v['records_as_expected']} {v['statuses']} {v['records_per_request']} {v['reasons']}")


# ---------------------------------------------------------------------------------------
# Spare objects and a document for the matrix (C5) and IDOR (C6)
# ---------------------------------------------------------------------------------------


def tiny_pdf(text: str = "D1 test document") -> bytes:
    import pikepdf
    pdf = pikepdf.new()
    pdf.add_blank_page(page_size=(200, 200))
    page = pdf.pages[0]
    font = pdf.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica))
    page.Resources = pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font))
    page.Contents = pdf.make_stream(f"BT /F1 10 Tf 10 100 Td ({text}) Tj ET".encode())
    buf = io.BytesIO()
    pdf.save(buf)
    return buf.getvalue()


def upload(c: httpx.Client, h: dict, seafarer_id: int, type_id: int, *, number: str, issue: str, expiry: str | None,
           content: bytes | None = None, filename: str = "doc.pdf", ctype: str = "application/pdf",
           not_stated: bool = False, extra_headers: dict | None = None) -> httpx.Response:
    data = {"document_number": number, "issuing_authority": "D1 Authority", "issue_date": issue}
    if expiry is not None:
        data["expiry_date"] = expiry
    if not_stated:
        data["expiry_not_stated"] = "true"
    files = {"file": (filename, content if content is not None else tiny_pdf(), ctype)}
    return c.post(f"/api/seafarers/{seafarer_id}/documents", params={"document_type_id": type_id},
                  data=data, files=files, headers={**h, **(extra_headers or {})})


async def matrix_fixture(ids: dict) -> dict:
    """Spare objects for the administrator's destructive calls, and S1/S2 documents."""
    acc = d1mod.accounts(ids)
    A1, O1, O2 = acc["A1"], acc["O1"], acc["O2"]
    T = date.fromisoformat(ids["today_utc"])
    fx: dict = {}
    with vlib.client() as c:
        h = A1.h
        fx["spare_vessel"] = c.post("/api/vessels", json={"name": "Spare vessel", "imo_number": "9199999", "flag": "PA"}, headers=h).json()["id"]
        fx["spare_position"] = c.post("/api/positions", json={"name": "Spare position"}, headers=h).json()["id"]
        fx["spare_type"] = c.post("/api/document-types", json={"name": "Spare type", "expires": False}, headers=h).json()["id"]
        r = c.put(f"/api/requirements/{fx['spare_position']}/{fx['spare_type']}", headers=h)
        fx["spare_exception"] = c.post("/api/requirement-exceptions", json={"vessel_id": fx["spare_vessel"], "document_type_id": fx["spare_type"], "effect": "add", "reason": "spare"}, headers=h).json()["id"]
        db = await vlib.owner()
        spare_off = await vlib.make_account(db, role="crewing_officer", email=f"spare-{uuid.uuid4().hex[:6]}@example.com")
        await db.close()
        c.post(f"/api/vessels/{fx['spare_vessel']}/responsible-officers", json={"account_id": str(spare_off.id)}, headers=h)
        fx["spare_officer"] = str(spare_off.id)
        # Documents: S1 (V1) by O2? No: by A1, so that O1 may review it. S2 (V2) by O2.
        def up(hh, s, t, n):
            r = upload(c, hh, ids["seafarers"][s], ids["types"][t], number=n,
                       issue=(T - timedelta(days=100)).isoformat(), expiry=(T + timedelta(days=400)).isoformat())
            assert r.status_code == 201, r.text
            return r.json()
        d_s1 = up(h, "S1", "COC", "NUM-S1-COC-7781")
        d_s2 = up(O2.h, "S2", "COC", "NUM-S2-COC-8892")
        fx["doc_S1"], fx["ver_S1"] = d_s1["id"], d_s1["versions"][0]["id"]
        fx["doc_S2"], fx["ver_S2"] = d_s2["id"], d_s2["versions"][0]["id"]
        # A verification with a proof file on each.
        for key, hh in (("S1", h), ("S2", acc["A2"].h)):
            r = c.post(f"/api/versions/{fx['ver_'+key]}/verifications",
                       data={"checked_on": T.isoformat(), "source": "Registry", "result": "confirmed", "reference": f"REF-{key}"},
                       files={"file": ("proof.pdf", tiny_pdf("proof"), "application/pdf")}, headers=hh)
            assert r.status_code in (200, 201), r.text
            cur = next(v for v in r.json()["versions"] if v["is_current"])
            fx["verif_" + key] = cur["verifications"][0]["id"]
        fx["doc_numbers"] = ["NUM-S1-COC-7781", "NUM-S2-COC-8892"]
    (vlib.EVIDENCE / "D1" / "matrix_fixture.json").write_text(json.dumps(fx, indent=1), encoding="utf-8")
    return fx


def path_values(ids: dict, fx: dict, role: str, m: str, p: str, scope_side: str = "own") -> dict:
    """Identifiers for a path: in O1's scope (V1, S1) unless scope_side='other' (V2, S2)."""
    s, v, a = ("S1", "V1", "S1") if scope_side == "own" else ("S2", "V2", "S2")
    destructive = m == "DELETE" or re.search(r"/(retire|unretire|deactivate|reactivate)$", p) or \
        (m == "PUT" and p.startswith("/api/requirements/"))
    vals = {
        "seafarer_id": ids["seafarers"][s], "vessel_id": ids["vessels"][v],
        "assignment_id": ids["assignments"][a], "document_id": fx["doc_" + s],
        "version_id": fx["ver_" + s], "verification_id": fx["verif_" + s],
        "row_id": ids["position"] if "/positions/" in p else ids["types"]["COC"],
        "position_id": ids["position"], "document_type_id": ids["types"]["COC"],
        "exception_id": ids["exceptions"][0], "account_id": ids["accounts"]["P"]["id"],
    }
    if destructive:
        vals.update({"vessel_id": fx["spare_vessel"], "row_id": fx["spare_position"] if "/positions/" in p else fx["spare_type"],
                     "position_id": fx["spare_position"], "document_type_id": fx["spare_type"],
                     "exception_id": fx["spare_exception"], "account_id": fx["spare_officer"]})
        if p.startswith("/api/seafarers/"):
            vals["seafarer_id"] = ids["seafarers"]["S3"]
    return vals


# ---------------------------------------------------------------------------------------
# C5 WSTG-ATHZ-02: every route and method with A1, O1, M, P, X
# ---------------------------------------------------------------------------------------


def load_expected() -> dict[tuple[str, str], dict[str, str]]:
    out = {}
    with open(HERE / "expected_matrix.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            out[(r["method"], r["path"])] = r
    return out


async def c5() -> None:
    ev = vlib.Evidence("C5")
    ids = d1mod.load()
    fx = json.loads((vlib.EVIDENCE / "D1" / "matrix_fixture.json").read_text())
    acc = d1mod.accounts(ids)
    expected = load_expected()
    db = await vlib.owner()
    results = []
    manager_bodies = []
    with vlib.client() as c:
        rts = routes(c)
        missing = [r for r in rts if r not in expected]
        extra = [k for k in expected if k not in rts]
        for role in ("X", "P", "M", "O1", "A1"):
            for m, p in rts:
                if role == "A1" and p == "/api/accounts/{account_id}/deactivate":
                    pass
                r_id = rid()
                url = fill(path_values(ids, fx, role, m, p), {}) if False else fill(p, path_values(ids, fx, role, m, p))
                params = {}
                if p.endswith("/report"):
                    params = {"format": "csv"}
                if p == "/api/requirements/evaluate":
                    params = {"position": ids["position"], "vessel": ids["vessels"]["V1"]}
                if p == "/api/seafarers/{seafarer_id}/documents" and m == "POST":
                    params = {"document_type_id": ids["types"]["MED"]}
                r = c.request(m, url, params=params, headers={**acc[role].h, "X-Request-ID": r_id},
                              json={} if m in ("POST", "PUT") and not p.endswith(("/file-url", "/proof-url", "/run")) else None)
                ev.exchange(f"{role} {m} {p}", r)
                got = "deny" if r.status_code == 403 else ("auth" if r.status_code == 401 else "allow")
                exp = expected.get((m, p), {}).get(role.rstrip("1"), "missing")
                if role == "O1":
                    exp = expected.get((m, p), {}).get("O", "missing")
                if role == "A1":
                    exp = expected.get((m, p), {}).get("A", "missing")
                results.append({"role": role, "method": m, "path": p, "status": r.status_code, "got": got,
                                "expected": exp, "request_id": r_id,
                                "match": exp == "unspec" or exp == got})
                if role == "M" and r.status_code < 400:
                    manager_bodies.append((m, p, r.text))
    recs = await audit_by_request(db, [x["request_id"] for x in results])
    for x in results:
        rr = recs.get(x["request_id"], [])
        x["refusal_records"] = sum(1 for r in rr if r["action"] == "access_refused")
        x["refusal_ok"] = x["status"] != 403 or x["refusal_records"] == 1
    # Manager leak check
    leaks = []
    for m, p, body in manager_bodies:
        for n in fx["doc_numbers"]:
            if n in body:
                leaks.append(f"{m} {p}: document number {n}")
        for pat in (r"versions/[0-9a-f]{32}", r"verifications/[0-9a-f]{32}", r"proof\.pdf", r"doc\.pdf", "file_path", "original_filename", "document_number"):
            if re.search(pat, body):
                leaks.append(f"{m} {p}: matches {pat}")
    ev.write("matrix_results.json", results)
    with open(ev.dir / "matrix_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    mism = [x for x in results if not x["match"]]
    norec = [x for x in results if not x["refusal_ok"]]
    ev.write("mismatches.json", mism)
    ev.write("manager_leaks.json", leaks)
    ev.save({"routes": len(rts), "calls": len(results), "mismatches": len(mism), "refusal_record_problems": len(norec),
             "routes_missing_from_expected": missing, "expected_rows_not_in_api": extra, "manager_leaks": len(leaks)})
    await db.close()
    print(f"routes={len(rts)} calls={len(results)} mismatches={len(mism)} refusal-record problems={len(norec)} leaks={len(leaks)}")
    for x in mism:
        print(f"  MISMATCH {x['role']:3s} {x['method']:6s} {x['path']} status={x['status']} expected={x['expected']}")
    for x in norec[:20]:
        print(f"  NOREC {x['role']} {x['method']} {x['path']} {x['status']} records={x['refusal_records']}")
    for l in leaks:
        print("  LEAK", l)


# ---------------------------------------------------------------------------------------
# Real Supabase Auth accounts (password + TOTP) for C2, C3, C4, C13
# ---------------------------------------------------------------------------------------


def admin_create_auth_user(email: str, password: str, full_name: str = "Real Account") -> uuid.UUID:
    """Create a confirmed Supabase Auth user through GoTrue's admin API (local
    service key), so that the sign-up trigger creates the Account row."""
    key = vlib.ENV["SUPABASE_SERVICE_ROLE_KEY"]
    with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
        r = s.post("/auth/v1/admin/users", json={"email": email, "password": password, "email_confirm": True,
                                                 "user_metadata": {"full_name": full_name}},
                   headers={"apikey": key, "Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return uuid.UUID(r.json()["id"])


def api_sign_in(c: httpx.Client, email: str, password: str, secret: str | None, ev: vlib.Evidence | None = None,
                label: str = "") -> tuple[dict, str | None]:
    """Password then TOTP through the API. Returns (final body, totp secret).
    Enrols when the account has no factor yet."""
    r = c.post("/api/auth/login", json={"email": email, "password": password})
    if ev:
        ev.exchange(f"{label} login", r)
    if r.status_code != 200:
        return {"status": r.status_code, "body": r.json() if r.content else None}, secret
    step = r.json()
    if step.get("step") == "enrol" or step.get("secret"):
        secret = step["secret"]
    vlib.wait_fresh_totp_window()
    v = c.post("/api/auth/verify", json={"email": email, "challenge": step["challenge"], "code": vlib.totp_now(secret)})
    if ev:
        ev.exchange(f"{label} verify", v)
    return {"status": v.status_code, "body": v.json() if v.content else None, "step": step.get("step")}, secret


async def real_account(db, role: str = "crewing_officer", status: str = "active", prefix: str = "real") -> dict:
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verif-" + uuid.uuid4().hex[:14]
    uid = admin_create_auth_user(email, password)
    if status != "pending":
        await db.execute("UPDATE public.users SET status=$2, role=$3 WHERE id=$1", uid, status, role)
    return {"id": uid, "email": email, "password": password}


# ---------------------------------------------------------------------------------------
# C4 WSTG-IDNT-02 / ATHZ-03: role injection and privilege escalation
# ---------------------------------------------------------------------------------------


async def c4() -> None:
    ev = vlib.Evidence("C4")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    with vlib.client() as c:
        # 1 role in the registration body
        email1 = f"c4reg-{uuid.uuid4().hex[:6]}@example.com"
        r = c.post("/api/auth/register", json={"email": email1, "full_name": "Role Injector", "password": "Unusual-Reg-Pass-7712",
                                               "role": "administrator", "status": "active"}, headers={"X-Request-ID": rid()})
        ev.exchange("register with role and status", r)
        row = await db.fetchrow("SELECT status, role FROM public.users WHERE email=$1", email1)
        ev.row(case="registration body with role=administrator", status=r.status_code,
               account=dict(row) if row else None, ok=bool(row) and row["role"] is None and row["status"] == "pending")
        # 2 user_metadata role straight at GoTrue
        email2 = f"c4meta-{uuid.uuid4().hex[:6]}@example.com"
        with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
            g = s.post("/auth/v1/signup", json={"email": email2, "password": "Unusual-Meta-Pass-8812",
                                                "data": {"role": "administrator", "status": "active", "full_name": "Meta"}},
                       headers={"apikey": vlib.ANON_KEY})
        row2 = await db.fetchrow("SELECT id, status, role FROM public.users WHERE email=$1", email2)
        meta = await db.fetchval("SELECT raw_user_meta_data FROM auth.users WHERE email=$1", email2)
        ev.row(case="GoTrue signup with data.role=administrator", gotrue_status=g.status_code,
               account={k: str(v) for k, v in dict(row2).items()} if row2 else None, user_metadata=meta,
               ok=bool(row2) and row2["role"] is None and row2["status"] == "pending")
        if row2:
            tok = vlib.make_token(row2["id"])
            await db.execute("INSERT INTO public.verified_session (session_id, user_id) VALUES ($1,$1) ON CONFLICT DO NOTHING", row2["id"])
            rr = c.get("/api/accounts", headers=vlib.bearer(tok))
            ev.exchange("metadata-role account GET /api/accounts", rr)
            ev.row(case="metadata-role account calls an admin endpoint", status=rr.status_code, ok=rr.status_code == 403)
        # 3 tokens carrying role claims, for the pending account P and officer O1
        P = acc["P"]
        for name, extra in (("role=service_role", {"role": "service_role"}),
                            ("app_metadata.role=administrator", {"app_metadata": {"role": "administrator"}}),
                            ("user_metadata.role=administrator", {"user_metadata": {"role": "administrator"}})):
            for who in ("P", "O1"):
                a = acc[who]
                tok = vlib.make_token(a.id, email=a.email, **extra)
                rq = rid()
                rr = c.get("/api/accounts", headers={**vlib.bearer(tok), "X-Request-ID": rq})
                ev.exchange(f"{who} token {name} GET /api/accounts", rr)
                n = len((await audit_by_request(db, [rq])).get(rq, []))
                ev.row(case=f"{who} token with {name} -> GET /api/accounts", status=rr.status_code, records=n,
                       ok=rr.status_code == 403 and n == 1)
        # 4 O1 tries administrator functions
        O1 = acc["O1"]
        settings = c.get("/api/settings", headers=acc["A1"].h).json()
        body_settings = {k: settings[k] for k in ("alert_steps", "planning_horizon_days", "max_file_size_mb", "max_pdf_pages",
                                                  "time_zone", "daily_check_time", "retention_replaced_version_years",
                                                  "retention_inactive_seafarer_years", "retention_audit_record_years", "version")}
        attempts = [
            ("approve pending account", "POST", f"/api/accounts/{P.id}/approve", {"role": "administrator", "reason": "x", "vessel_ids": []}),
            ("change own role to administrator", "POST", f"/api/accounts/{O1.id}/role", {"role": "administrator", "reason": "x"}),
            ("change another account's role", "POST", f"/api/accounts/{acc['O2'].id}/role", {"role": "manager", "reason": "x"}),
            ("change settings", "PUT", "/api/settings", {**body_settings, "planning_horizon_days": 30}),
            ("run the daily check", "POST", "/api/admin/daily-check/run", None),
            ("read the audit log", "GET", "/api/audit", None),
            ("export the audit log", "GET", "/api/audit/export.csv", None),
        ]
        for name, m, p, body in attempts:
            rq = rid()
            rr = c.request(m, p, json=body, headers={**O1.h, "X-Request-ID": rq})
            ev.exchange(f"O1 {name}", rr)
            n = (await audit_by_request(db, [rq])).get(rq, [])
            ev.row(case=f"O1: {name}", status=rr.status_code, records=len(n), reasons=[x["reason"] for x in n],
                   ok=rr.status_code == 403 and len(n) == 1)
        after = await db.fetchrow("SELECT status, role FROM public.users WHERE id=$1", O1.id)
        ev.row(case="O1 role afterwards", value=dict(after), ok=after["role"] == "crewing_officer")
        s2 = c.get("/api/settings", headers=acc["A1"].h).json()
        ev.row(case="settings unchanged", planning_horizon_days=s2["planning_horizon_days"], ok=s2["planning_horizon_days"] == settings["planning_horizon_days"])
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})


# ---------------------------------------------------------------------------------------
# C6 WSTG-ATHZ-04: other vessel's objects by identifier; PostgREST; Storage
# ---------------------------------------------------------------------------------------


async def c6() -> None:
    ev = vlib.Evidence("C6")
    ids = d1mod.load()
    fx = json.loads((vlib.EVIDENCE / "D1" / "matrix_fixture.json").read_text())
    acc = d1mod.accounts(ids)
    O1 = acc["O1"]
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    T = date.fromisoformat(ids["today_utc"])
    s2, v2, a2 = ids["seafarers"]["S2"], ids["vessels"]["V2"], ids["assignments"]["S2"]
    targets = [
        ("seafarer", "GET", f"/api/seafarers/{s2}", None),
        ("seafarer edit", "PUT", f"/api/seafarers/{s2}", {"first_name": "X", "last_name": "Y", "position_id": ids["position"]}),
        ("seafarer documents", "GET", f"/api/seafarers/{s2}/documents", None),
        ("seafarer assignments", "GET", f"/api/seafarers/{s2}/assignments", None),
        ("seafarer set-inactive", "POST", f"/api/seafarers/{s2}/set-inactive", {"reason": "x"}),
        ("document", "GET", f"/api/documents/{fx['doc_S2']}", None),
        ("details-only version", "POST", f"/api/documents/{fx['doc_S2']}/versions",
         {"document_number": "Z", "issuing_authority": "Z", "issue_date": (T - timedelta(days=5)).isoformat(), "expiry_date": (T + timedelta(days=300)).isoformat()}),
        ("file URL", "POST", f"/api/versions/{fx['ver_S2']}/file-url", None),
        ("proof-file URL", "POST", f"/api/verifications/{fx['verif_S2']}/proof-url", None),
        ("review", "POST", f"/api/versions/{fx['ver_S2']}/reviews", {"decision": "accept", "comment": "x"}),
        ("assignment", "GET", f"/api/assignments/{a2}", None),
        ("assignment edit", "PUT", f"/api/assignments/{a2}", {"vessel_id": v2, "position_id": ids["position"], "start_date": (T + timedelta(days=20)).isoformat(), "end_date": (T + timedelta(days=120)).isoformat()}),
        ("assignment cancel", "POST", f"/api/assignments/{a2}/cancel", {"reason": "x"}),
        ("readiness", "GET", f"/api/assignments/{a2}/readiness", None),
        ("assignment report", "GET", f"/api/assignments/{a2}/report?format=csv", None),
        ("vessel report", "GET", f"/api/vessels/{v2}/report?format=pdf", None),
        ("vessel crew", "GET", f"/api/vessels/{v2}/crew", None),
    ]
    with vlib.client() as c:
        for name, m, p, body in targets:
            rq = rid()
            r = c.request(m, p, json=body, headers={**O1.h, "X-Request-ID": rq})
            ev.exchange(f"O1 other-vessel {name}", r)
            recs = (await audit_by_request(db, [rq])).get(rq, [])
            leaked = any(s in r.text for s in ("Stwo", "NUM-S2", "D1 Vessel Two")) and r.status_code >= 400
            ev.row(group="other vessel", case=name, method=m, path=p, status=r.status_code, records=len(recs),
                   reasons=[x["reason"] for x in recs], body=r.text[:160],
                   ok=r.status_code == 404 and len(recs) == 1 and recs[0]["action"] == "access_refused" and not leaked)
        # Upload to the other vessel's seafarer
        rq = rid()
        r = upload(c, O1.h, s2, ids["types"]["MED"], number="IDOR", issue=(T - timedelta(days=5)).isoformat(),
                   expiry=(T + timedelta(days=300)).isoformat(), extra_headers={"X-Request-ID": rq})
        recs = (await audit_by_request(db, [rq])).get(rq, [])
        ev.row(group="other vessel", case="upload", status=r.status_code, records=len(recs), ok=r.status_code == 404 and len(recs) == 1)
        # Non-existent identifiers: no record
        for name, p in (("seafarer", "/api/seafarers/999999"), ("document", "/api/documents/999999"),
                        ("assignment", "/api/assignments/999999/readiness")):
            rq = rid()
            r = c.get(p, headers={**O1.h, "X-Request-ID": rq})
            recs = (await audit_by_request(db, [rq])).get(rq, [])
            ev.row(group="non-existent", case=name, status=r.status_code, records=len(recs), ok=r.status_code == 404 and len(recs) == 0)
        # Sequential enumeration of seafarer, document and version identifiers
        in_scope = d1mod.expected_scope("O1")
        sid_to_key = {v: k for k, v in ids["seafarers"].items()}
        lo, hi = min(ids["seafarers"].values()) - 3, max(ids["seafarers"].values()) + 5
        enum = []
        for i in range(lo, hi):
            rq = rid()
            r = c.get(f"/api/seafarers/{i}", headers={**O1.h, "X-Request-ID": rq})
            recs = (await audit_by_request(db, [rq])).get(rq, [])
            key = sid_to_key.get(i)
            exists = await db.fetchval("SELECT count(*) FROM public.seafarer WHERE id=$1", i)
            exp = 200 if key in in_scope else 404
            if key is None and exists:
                exp = None  # a non-D1 seafarer (none expected after the wipe)
            enum.append({"id": i, "d1": key, "exists": bool(exists), "status": r.status_code, "records": len(recs),
                         "ok": (exp is None) or (r.status_code == exp and len(recs) == (1 if (exists and exp == 404) else 0))})
        ev.write("enumeration_seafarers.json", enum)
        ev.row(group="enumeration", case=f"seafarer ids {lo}..{hi - 1}", ok=all(e["ok"] for e in enum),
               detail=[(e["id"], e["d1"], e["status"], e["records"]) for e in enum])
        enum_d = []
        for kind, path, table in (("document", "/api/documents/{}", "document"),):
            known = [fx["doc_S1"], fx["doc_S2"]]
            for i in range(min(known) - 2, max(known) + 4):
                rq = rid()
                r = c.get(path.format(i), headers={**O1.h, "X-Request-ID": rq})
                recs = (await audit_by_request(db, [rq])).get(rq, [])
                own = await db.fetchval(f"SELECT s.id FROM public.{table} d JOIN public.seafarer s ON s.id=d.seafarer_id WHERE d.id=$1", i)
                key = sid_to_key.get(own) if own else None
                exp = 200 if key in in_scope else 404
                enum_d.append({"id": i, "owner": key, "status": r.status_code, "records": len(recs),
                               "ok": r.status_code == exp and len(recs) == (1 if (own and exp == 404) else 0)})
        ev.write("enumeration_documents.json", enum_d)
        ev.row(group="enumeration", case="document ids", ok=all(e["ok"] for e in enum_d), detail=[(e["id"], e["owner"], e["status"], e["records"]) for e in enum_d])

    # PostgREST and Storage directly, with the anon key and with a user JWT
    tables = [r["tablename"] for r in await db.fetch("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY 1")]
    user_jwt = vlib.make_token(acc["A1"].id, email=acc["A1"].email)
    rest = []
    with httpx.Client(base_url=vlib.SUPABASE_URL, timeout=30) as s:
        for t in tables:
            for who, hdr in (("anon", {"apikey": vlib.ANON_KEY}),
                             ("user_jwt", {"apikey": vlib.ANON_KEY, "Authorization": f"Bearer {user_jwt}"})):
                r = s.get(f"/rest/v1/{t}", params={"select": "*", "limit": "5"}, headers=hdr)
                try:
                    body = r.json()
                except Exception:
                    body = r.text[:200]
                rows = len(body) if isinstance(body, list) else None
                rest.append({"table": t, "as": who, "status": r.status_code, "rows": rows,
                             "error": body.get("code") if isinstance(body, dict) else None,
                             "ok": (rows == 0) or r.status_code >= 400})
        storage = []
        vpath = await db.fetchval("SELECT file_path FROM public.version WHERE id=$1", fx["ver_S1"])
        for who, hdr in (("anon", {"apikey": vlib.ANON_KEY, "Authorization": f"Bearer {vlib.ANON_KEY}"}),
                         ("user_jwt", {"apikey": vlib.ANON_KEY, "Authorization": f"Bearer {user_jwt}"})):
            for name, m, p, body in (("list bucket", "POST", "/storage/v1/object/list/crew-documents", {"prefix": "versions", "limit": 10}),
                                     ("list buckets", "GET", "/storage/v1/bucket", None),
                                     ("get object (authenticated route)", "GET", f"/storage/v1/object/authenticated/crew-documents/{vpath}", None),
                                     ("get object", "GET", f"/storage/v1/object/crew-documents/{vpath}", None),
                                     ("get object (public route)", "GET", f"/storage/v1/object/public/crew-documents/{vpath}", None)):
                r = s.request(m, p, json=body, headers=hdr)
                try:
                    j = r.json()
                except Exception:
                    j = None
                items = len(j) if isinstance(j, list) else None
                got_pdf = r.content[:5] == b"%PDF-"
                storage.append({"as": who, "case": name, "status": r.status_code, "items": items, "got_file": got_pdf,
                                "body": r.text[:160] if not got_pdf else "<pdf>", "ok": not got_pdf and not items})
    ev.write("postgrest.json", rest)
    ev.write("storage_direct.json", storage)
    ev.row(group="postgrest", case=f"{len(tables)} public tables x anon/user JWT", ok=all(x["ok"] for x in rest),
           failures=[x for x in rest if not x["ok"]], statuses={f"{k[0]} {k[1]}": v for k, v in Counter((x["status"], x["error"]) for x in rest).items()})
    ev.row(group="storage", case="bucket list / object fetch without signature", ok=all(x["ok"] for x in storage),
           detail=[(x["as"], x["case"], x["status"], x["items"], x["got_file"]) for x in storage])
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r.get("group"), r["case"], r.get("status", ""), r.get("records", ""), r.get("reasons", ""))


# ---------------------------------------------------------------------------------------
# C7 WSTG-BUSL-01 data validation; C8 BUSL-06 work-flow circumvention
# ---------------------------------------------------------------------------------------


async def c7() -> None:
    ev = vlib.Evidence("C7")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    O1 = acc["O1"]
    T = date.fromisoformat(ids["today_utc"])
    db = await vlib.owner()
    s1, med, coc = ids["seafarers"]["S1"], ids["types"]["MED"], ids["types"]["BST"]

    async def versions() -> int:
        return await db.fetchval("SELECT count(*) FROM public.version")

    with vlib.client() as c:
        cases = [
            ("30 February (upload)", {"issue": "2026-02-30", "expiry": "2028-01-01"}, (422,)),
            ("2027-13-01 expiry (upload)", {"issue": "2026-01-01", "expiry": "2027-13-01"}, (422,)),
            ("issue date equal to expiry (upload)", {"issue": "2026-06-01", "expiry": "2026-06-01"}, (422,)),
            ("issue date after expiry (upload)", {"issue": "2026-06-02", "expiry": "2026-06-01"}, (422,)),
        ]
        for name, d, exp in cases:
            before = await versions()
            r = upload(c, O1.h, s1, med, number="C7", issue=d["issue"], expiry=d["expiry"])
            ev.exchange(name, r)
            after = await versions()
            ev.row(case=name, status=r.status_code, saved=after - before, ok=r.status_code in exp and after == before)
        # Over the maximum validity: MED max 24 months -> issue T-10d, expiry issue + 24 months + 1 day
        issue = T - timedelta(days=10)
        y, m = issue.year + 2, issue.month
        over = date(y, m, min(issue.day, 28)) + timedelta(days=1)
        before = await versions()
        r = upload(c, O1.h, s1, med, number="C7-OVER", issue=issue.isoformat(), expiry=over.isoformat())
        ev.exchange("validity one day above maximum", r)
        body = r.json() if r.content else {}
        ev.row(case="validity one day above the type maximum (24 months)", status=r.status_code,
               warnings=body.get("warnings"), saved=(await versions()) - before,
               above_flag=[v.get("above_max_validity") for v in body.get("versions", [])][:1],
               ok=r.status_code == 201 and bool(body.get("warnings")))
        doc = body.get("id")
        # Same cases on the details-only route
        if doc:
            for name, iss, expd in (("30 February (details-only)", "2026-02-30", "2028-01-01"),
                                    ("2027-13-01 (details-only)", "2026-01-01", "2027-13-01"),
                                    ("issue equal to expiry (details-only)", "2026-06-01", "2026-06-01"),
                                    ("issue after expiry (details-only)", "2026-06-02", "2026-06-01")):
                before = await versions()
                r = c.post(f"/api/documents/{doc}/versions", json={"document_number": "C7D", "issuing_authority": "A",
                                                                  "issue_date": iss, "expiry_date": expd}, headers=O1.h)
                ev.exchange(name, r)
                ev.row(case=name, status=r.status_code, saved=(await versions()) - before,
                       ok=r.status_code == 422 and (await versions()) == before)
        # Date of birth in the future in the company time zone
        await db.execute("UPDATE public.settings SET time_zone='Pacific/Kiritimati'")
        kt_today = (vlib.now_utc() + timedelta(hours=14)).date()
        for name, dob, exp in (("date of birth tomorrow (company TZ UTC+14)", kt_today + timedelta(days=1), 422),
                               ("date of birth today (company TZ UTC+14), control", kt_today - timedelta(days=0), None)):
            before = await db.fetchval("SELECT count(*) FROM public.seafarer")
            r = c.post("/api/seafarers", json={"first_name": "Dob", "last_name": "Check", "date_of_birth": dob.isoformat(),
                                               "position_id": ids["position"]}, headers=O1.h)
            ev.exchange(name, r)
            ev.row(case=name, dob=dob.isoformat(), status=r.status_code,
                   saved=(await db.fetchval("SELECT count(*) FROM public.seafarer")) - before,
                   ok=(r.status_code == 422) if exp else True)
        await db.execute("UPDATE public.settings SET time_zone='UTC'")
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["case"], r.get("status"), r.get("saved", ""), r.get("warnings", ""))


async def c8() -> None:
    ev = vlib.Evidence("C8")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    O1, A1, A2 = acc["O1"], acc["A1"], acc["A2"]
    T = date.fromisoformat(ids["today_utc"])
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    with vlib.client() as c:
        r = upload(c, O1.h, ids["seafarers"]["S1"], ids["types"]["BST"], number="C8-1",
                   issue=(T - timedelta(days=30)).isoformat(), expiry=(T + timedelta(days=700)).isoformat())
        doc = r.json()
        v1 = doc["versions"][0]["id"]
        rq = rid()
        r = c.post(f"/api/versions/{v1}/reviews", json={"decision": "accept", "comment": "own"}, headers={**O1.h, "X-Request-ID": rq})
        ev.exchange("uploader reviews own version", r)
        recs = (await audit_by_request(db, [rq])).get(rq, [])
        ev.row(case="uploader reviews own version via API", status=r.status_code, records=len(recs),
               reasons=[x["reason"] for x in recs], ok=r.status_code == 403 and len(recs) == 1)
        # As app_backend: INSERT a review by the uploader
        import asyncpg
        app = await asyncpg.connect(vlib.APP_DB_URL)
        try:
            await app.execute("INSERT INTO public.review (version_id, decision, comment, reviewed_by) VALUES ($1,'accept','sql',$2)", v1, O1.id)
            res = "inserted"
        except Exception as e:
            res = f"{type(e).__name__}: {e}"
        await app.close()
        ev.row(case="app_backend INSERT of a review by the uploader", result=res, ok=res != "inserted")
        # Non-current version: upload v2, then review v1
        r = upload(c, O1.h, ids["seafarers"]["S1"], ids["types"]["BST"], number="C8-2",
                   issue=(T - timedelta(days=20)).isoformat(), expiry=(T + timedelta(days=700)).isoformat())
        v2 = next(v["id"] for v in r.json()["versions"] if v["is_current"])
        r = c.post(f"/api/versions/{v1}/reviews", json={"decision": "accept", "comment": "old one"}, headers=A1.h)
        ev.exchange("review a non-current version", r)
        ev.row(case="review a version that is not current", status=r.status_code, body=r.text[:200], ok=None)
        r = c.post(f"/api/versions/{v1}/verifications", data={"checked_on": T.isoformat(), "source": "R", "result": "confirmed", "reference": "x"}, headers=A1.h)
        ev.exchange("verify a non-current version", r)
        ev.row(case="verify a version that is not current", status=r.status_code, body=r.text[:200], ok=None)
        # Rejected current version
        r = c.post(f"/api/versions/{v2}/reviews", json={"decision": "reject", "comment": "bad"}, headers=A1.h)
        ev.row(case="A1 rejects current version", status=r.status_code, ok=r.status_code in (200, 201))
        r = c.post(f"/api/versions/{v2}/reviews", json={"decision": "accept", "comment": "re-review rejected"}, headers=A2.h)
        ev.exchange("review a rejected version", r)
        ev.row(case="A2 reviews the rejected version again", status=r.status_code, body=r.text[:200], ok=None)
        r = c.post(f"/api/versions/{v2}/verifications", data={"checked_on": T.isoformat(), "source": "R", "result": "confirmed", "reference": "x"}, headers=A2.h)
        ev.exchange("verify a rejected version", r)
        ev.row(case="verify a rejected version", status=r.status_code, body=r.text[:200], ok=None)
        d = c.get(f"/api/documents/{doc['id']}", headers=A1.h).json()
        ev.row(case="document after these steps", review_states=[(v["number"], v["is_current"], v["review_state"], len(v["reviews"])) for v in d["versions"]],
               verified=d["verified"], ok=None)
        # Methods on decisions
        rev_id = None
        for v in d["versions"]:
            if v["reviews"]:
                rev_id = v["reviews"][0]["id"]
        for m in ("PUT", "PATCH", "DELETE"):
            r = c.request(m, f"/api/versions/{v2}/reviews", json={"decision": "accept", "comment": "x"}, headers=A1.h)
            ev.exchange(f"{m} /api/versions/{{id}}/reviews", r)
            ev.row(case=f"{m} on the reviews path", status=r.status_code, allow=r.headers.get("allow"), ok=r.status_code == 405)
            r = c.request(m, f"/api/reviews/{rev_id}", json={"decision": "accept", "comment": "x"}, headers=A1.h)
            ev.row(case=f"{m} /api/reviews/{{id}} (no such route)", status=r.status_code, ok=r.status_code in (404, 405))
        # app_backend UPDATE/DELETE of a review
        app = await asyncpg.connect(vlib.APP_DB_URL)
        for sql in ("UPDATE public.review SET decision='accept' WHERE id=$1", "DELETE FROM public.review WHERE id=$1"):
            try:
                await app.execute(sql, rev_id)
                res = "succeeded"
            except Exception as e:
                res = f"{type(e).__name__}: {e}"
            ev.row(case=f"app_backend: {sql.split()[0]} review", result=res, ok=res != "succeeded")
        await app.close()
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print({True: "OK  ", False: "FAIL", None: "INFO"}[r.get("ok")], r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})


# ---------------------------------------------------------------------------------------
# C9 WSTG-BUSL-08/09: the upload corpus
# ---------------------------------------------------------------------------------------


def chunked_multipart(fields: dict, filename: str, content: bytes, ctype: str):
    boundary = "vchk" + uuid.uuid4().hex
    def gen():
        for k, v in fields.items():
            yield f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode()
        yield f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{filename}\"\r\nContent-Type: {ctype}\r\n\r\n".encode()
        for i in range(0, len(content), 65536):
            yield content[i:i + 65536]
        yield f"\r\n--{boundary}--\r\n".encode()
    return gen(), f"multipart/form-data; boundary={boundary}"


async def c9() -> None:
    import make_corpus
    from PIL import Image
    ev = vlib.Evidence("C9")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    O1, A1 = acc["O1"], acc["A1"]
    T = date.fromisoformat(ids["today_utc"])
    db = await vlib.owner()
    st = await db.fetchrow("SELECT max_file_size_mb, max_pdf_pages FROM public.settings")
    max_bytes = min(st["max_file_size_mb"], 4) * 1024 * 1024
    cases = make_corpus.corpus(max_bytes, st["max_pdf_pages"])
    fields = {"document_number": "C9", "issuing_authority": "C9 Authority",
              "issue_date": (T - timedelta(days=10)).isoformat(), "expiry_date": (T + timedelta(days=300)).isoformat()}
    misleading = {"application/pdf": "image/png", "image/jpeg": "application/pdf", "image/png": "application/pdf"}
    s1, med = ids["seafarers"]["S1"], ids["types"]["MED"]
    start = await vlib.max_audit_id(db)
    with vlib.client(timeout=120) as c:
        for case in cases:
            for ct_mode in ("honest", "misleading"):
                ct = case.content_type if ct_mode == "honest" else misleading.get(case.content_type, "application/pdf")
                if case.group == "type" and ct_mode == "misleading":
                    ct = "application/pdf" if not case.filename.lower().endswith(".pdf") else "image/jpeg"
                rq = rid()
                before = await db.fetchval("SELECT count(*) FROM public.version")
                r = upload(c, O1.h, s1, med, number="C9", issue=fields["issue_date"], expiry=fields["expiry_date"],
                           content=case.content, filename=case.filename, ctype=ct, extra_headers={"X-Request-ID": rq})
                recs = (await audit_by_request(db, [rq])).get(rq, [])
                created = (await db.fetchval("SELECT count(*) FROM public.version")) - before
                code = (r.json().get("detail") or {}).get("code") if r.status_code >= 400 and r.headers.get("content-type", "").startswith("application/json") and isinstance(r.json().get("detail"), dict) else None
                rejected_rec = [x for x in recs if x["action"] == "upload_rejected"]
                row = ev.row(group=case.group, case=case.name, filename=case.filename, size=len(case.content),
                             content_type_sent=ct, ct_mode=ct_mode, status=r.status_code, code=code,
                             expected=list(case.expected), versions_created=created,
                             upload_rejected_records=len(rejected_rec), reasons=[x["reason"] for x in recs],
                             note=case.note,
                             ok=r.status_code in case.expected and (created == (1 if r.status_code == 201 else 0))
                             and (r.status_code == 201 or len(rejected_rec) == 1))
                ev.exchange(f"{case.group} {case.name} [{ct_mode}]", r)
                # Inspect the stored copy of the image cases
                if r.status_code == 201 and case.group == "image":
                    ver = next(v for v in r.json()["versions"] if v["is_current"])
                    fu = c.post(f"/api/versions/{ver['id']}/file-url", headers=O1.h).json()
                    stored = httpx.get(fu["url"], timeout=60).content
                    info = {"stored_bytes": len(stored), "sent_bytes": len(case.content),
                            "stored_sha_differs": stored != case.content}
                    try:
                        im = Image.open(io.BytesIO(stored))
                        info["format"] = im.format
                        info["exif_tags"] = len(im.getexif())
                        info["info_keys"] = sorted(k for k in im.info.keys() if k not in ("dpi", "jfif", "jfif_version", "jfif_unit", "jfif_density", "progressive", "progression"))
                    except Exception as e:
                        info["open_error"] = str(e)
                    info["has_zip_signature"] = b"PK\x03\x04" in stored
                    info["has_secret_text"] = any(s in stored for s in (b"SecretCameraMaker", b"SecretPngComment", b"SecretZipPayload"))
                    info["gps_in_original"] = b"SecretCameraMaker" in case.content
                    row["stored_copy"] = info
                    row["ok"] = row["ok"] and info.get("exif_tags", 1) == 0 and not info["has_zip_signature"] and not info["has_secret_text"]
        # Chunked body without Content-Length over the limit
        big = make_corpus.padded_pdf(max_bytes + 512 * 1024)
        gen, ctype = chunked_multipart(fields, "chunked.pdf", big, "application/pdf")
        rq = rid()
        before = await db.fetchval("SELECT count(*) FROM public.version")
        t0 = time.perf_counter()
        r = c.post(f"/api/seafarers/{s1}/documents", params={"document_type_id": med}, content=gen,
                   headers={**O1.h, "Content-Type": ctype, "X-Request-ID": rq})
        el = time.perf_counter() - t0
        recs = (await audit_by_request(db, [rq])).get(rq, [])
        ev.exchange("chunked body over the limit", r)
        ev.row(group="size", case="chunked body without Content-Length over the limit", status=r.status_code,
               request_had_content_length="content-length" in r.request.headers, seconds=round(el, 2),
               upload_rejected_records=sum(1 for x in recs if x["action"] == "upload_rejected"),
               versions_created=(await db.fetchval("SELECT count(*) FROM public.version")) - before,
               record_size=[x.get("after") for x in recs][:1],
               ok=r.status_code == 413 and sum(1 for x in recs if x["action"] == "upload_rejected") == 1)
        # Uploads are not rate-limited: 30 in 30 s
        t0 = time.perf_counter()
        statuses = []
        pdf = make_corpus.save(make_corpus.base_pdf())
        for i in range(30):
            r = upload(c, O1.h, s1, ids["types"]["FAM"], number=f"RATE-{i}", issue=fields["issue_date"],
                       expiry=(T + timedelta(days=200)).isoformat(), content=pdf)
            statuses.append(r.status_code)
            time.sleep(max(0, (i + 1) * 1.0 - (time.perf_counter() - t0)))
        ev.row(group="rate", case="30 uploads in 30 s (no upload rate limit)", seconds=round(time.perf_counter() - t0, 1),
               statuses=dict(Counter(statuses)), ok=None, note="all accepted = upload rate limiting not implemented (SR-17 second part)")
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save({"max_bytes": max_bytes, "max_pdf_pages": st["max_pdf_pages"]})
    await db.close()
    for r in ev.rows:
        print({True: "OK  ", False: "FAIL", None: "INFO"}[r.get("ok")], f"{r['group']:9s} {r['case'][:50]:50s} {r.get('ct_mode',''):10s} {r.get('status')} {r.get('code')} rec={r.get('upload_rejected_records')} new={r.get('versions_created')} {r.get('stored_copy','')}")


# ---------------------------------------------------------------------------------------
# C10 WSTG-CONF-11: private bucket, signed URLs
# ---------------------------------------------------------------------------------------


async def c10() -> None:
    ev = vlib.Evidence("C10")
    ids = d1mod.load()
    fx = json.loads((vlib.EVIDENCE / "D1" / "matrix_fixture.json").read_text())
    acc = d1mod.accounts(ids)
    db = await vlib.owner()
    buckets = [dict(r) for r in await db.fetch("SELECT id, name, public, file_size_limit, allowed_mime_types FROM storage.buckets")]
    policies = [dict(r) for r in await db.fetch("SELECT schemaname, tablename, policyname, roles, cmd FROM pg_policies WHERE schemaname='storage'")]
    ev.row(case="buckets", buckets=buckets, ok=[b["id"] for b in buckets] == ["crew-documents"] and not buckets[0]["public"])
    ev.row(case="storage policies", policies=policies, ok=len(policies) == 0)
    path = await db.fetchval("SELECT file_path FROM public.version WHERE id=$1", fx["ver_S1"])
    with httpx.Client(timeout=30) as s:
        r = s.get(f"{vlib.SUPABASE_URL}/storage/v1/object/public/crew-documents/{path}")
        ev.row(case="public object URL", status=r.status_code, got_file=r.content[:5] == b"%PDF-", ok=r.content[:5] != b"%PDF-")
    with vlib.client() as c:
        urls = []
        for kind, p in (("version file", f"/api/versions/{fx['ver_S1']}/file-url"), ("proof file", f"/api/verifications/{fx['verif_S1']}/proof-url")):
            rq = rid()
            r = c.post(p, headers={**acc["O1"].h, "X-Request-ID": rq})
            ev.exchange(f"issue {kind} URL", r)
            body = r.json()
            recs = (await audit_by_request(db, [rq])).get(rq, [])
            tok = re.search(r"token=([^&]+)", body["url"]).group(1)
            claims = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
            ev.row(case=f"{kind}: URL issued", status=r.status_code, expires_in=body["expires_in"],
                   token_lifetime_s=claims.get("exp", 0) - claims.get("iat", 0), records=len(recs),
                   actions=[x["action"] for x in recs], ok=r.status_code == 200 and len(recs) == 1 and body["expires_in"] <= 300)
            g = httpx.get(body["url"], timeout=30)
            ev.row(case=f"{kind}: signed URL works at once", status=g.status_code, got_file=g.content[:5] == b"%PDF-", ok=g.status_code == 200)
            urls.append((kind, body["url"], body["expires_in"]))
        wait = max(u[2] for u in urls) + 5
        print(f"C10: waiting {wait} s for the signed URLs to expire")
        time.sleep(wait)
        for kind, url, ttl in urls:
            g = httpx.get(url, timeout=30)
            ev.row(case=f"{kind}: signed URL after {ttl}+5 s", status=g.status_code, got_file=g.content[:5] == b"%PDF-",
                   body=g.text[:150] if g.content[:5] != b"%PDF-" else "<pdf>", ok=g.content[:5] != b"%PDF-")
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})


# ---------------------------------------------------------------------------------------
# C12 WSTG-ERRH-01: error handling
# ---------------------------------------------------------------------------------------

LEAK_PATTERNS = [r"Traceback", r"File \"", r"\.py\b", r"asyncpg", r"SELECT\s", r"INSERT\s", r"postgresql://",
                 r"app_backend", r"super-secret", r"eyJhbGci", r"sb_secret", r"Exception", r"line \d+", r"C:\\\\", r"/home/"]


async def c12() -> None:
    ev = vlib.Evidence("C12")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    A1 = acc["A1"]
    typed_password = "Typed-Secret-Password-4471"
    cases = [
        ("malformed JSON", "POST", "/api/vessels", {"content": b"{\"name\": ", "headers": {"Content-Type": "application/json"}}),
        ("wrong types", "POST", "/api/vessels", {"json": {"name": 5, "imo_number": True, "flag": [1]}}),
        ("missing fields", "POST", "/api/seafarers", {"json": {}}),
        ("id 2^63", "GET", f"/api/seafarers/{2**63}", {}),
        ("id 10^30", "GET", f"/api/seafarers/{10**30}", {}),
        ("id 0", "GET", "/api/seafarers/0", {}),
        ("id -1", "GET", "/api/seafarers/-1", {}),
        ("id not a number", "GET", "/api/seafarers/abc", {}),
        ("unknown route", "GET", "/api/does-not-exist", {}),
        ("wrong method", "PATCH", "/api/vessels", {}),
        ("very long header", "GET", "/api/me", {"headers": {"X-Long": "a" * 60000}}),
        ("invalid multipart", "POST", f"/api/seafarers/{ids['seafarers']['S1']}/documents?document_type_id={ids['types']['MED']}",
         {"content": b"--x\r\nContent-Disposition: form-data; name=\"file\"\r\n\r\nbroken", "headers": {"Content-Type": "multipart/form-data; boundary=x"}}),
        ("multipart without boundary", "POST", f"/api/seafarers/{ids['seafarers']['S1']}/documents?document_type_id={ids['types']['MED']}",
         {"content": b"abc", "headers": {"Content-Type": "multipart/form-data"}}),
        ("login with typed password, malformed email", "POST", "/api/auth/login", {"json": {"email": "not-an-email", "password": typed_password}, "noauth": True}),
        ("register weak typed password", "POST", "/api/auth/register", {"json": {"email": "c12@example.com", "full_name": "x", "password": typed_password[:8]}, "noauth": True}),
        ("query param type error", "GET", "/api/dashboard?limit=abc", {}),
        ("huge page_size", "GET", "/api/audit?page_size=100000000", {}),
        ("SQL-ish search", "GET", "/api/seafarers?search=%27%3B%20DROP%20TABLE%20seafarer%3B--", {}),
        ("null byte in search", "GET", "/api/seafarers?search=a%00b", {}),
    ]
    with vlib.client() as c:
        for name, m, p, kw in cases:
            headers = {} if kw.get("noauth") else dict(A1.h)
            headers.update(kw.get("headers", {}))
            try:
                r = c.request(m, p, headers=headers, json=kw.get("json"), content=kw.get("content"))
            except Exception as e:
                ev.row(case=name, error=str(e), ok=None)
                continue
            ev.exchange(name, r)
            leaks = [pat for pat in LEAK_PATTERNS if re.search(pat, r.text)]
            if typed_password in r.text or typed_password[:8] in r.text:
                leaks.append("typed password echoed")
            ev.row(case=name, status=r.status_code, body=vlib.mask_text(r.text[:300]), leaks=leaks,
                   headers={k: v for k, v in r.headers.items() if k.lower() in ("server", "x-powered-by", "via", "x-request-id")},
                   ok=400 <= r.status_code < 500 and not leaks)
        h = c.get("/health")
        ev.row(case="identifying headers on /health", headers=dict(h.headers), ok=None)
    ev.save()
    for r in ev.rows:
        print({True: "OK  ", False: "FAIL", None: "INFO"}[r.get("ok")], r["case"], r.get("status"), r.get("leaks"), (r.get("body") or "")[:110])


# ---------------------------------------------------------------------------------------
# C14 Audit log protection
# ---------------------------------------------------------------------------------------


async def c14() -> None:
    import asyncpg
    ev = vlib.Evidence("C14")
    db = await vlib.owner()
    grants = [dict(r) for r in await db.fetch(
        "SELECT grantee, privilege_type FROM information_schema.role_table_grants WHERE table_schema='public' AND table_name='audit_log' ORDER BY 1,2")]
    ev.row(case="grants on audit_log", grants=grants,
           app_backend=sorted(g["privilege_type"] for g in grants if g["grantee"] == "app_backend"),
           ok=sorted(g["privilege_type"] for g in grants if g["grantee"] == "app_backend") == ["INSERT", "SELECT"])
    owner_role = await db.fetchval("SELECT tableowner FROM pg_tables WHERE schemaname='public' AND tablename='audit_log'")
    ev.row(case="owner of audit_log", owner=owner_role, ok=owner_role != "app_backend")
    app = await asyncpg.connect(vlib.APP_DB_URL)
    any_id = await db.fetchval("SELECT max(id) FROM public.audit_log")
    for sql in ("UPDATE public.audit_log SET action='x' WHERE id=$1", "DELETE FROM public.audit_log WHERE id=$1", "TRUNCATE public.audit_log"):
        try:
            await (app.execute(sql, any_id) if "$1" in sql else app.execute(sql))
            res = "succeeded"
        except Exception as e:
            res = f"{type(e).__name__}: {e}"
        ev.row(case=f"app_backend: {sql.split()[0]}", result=res, ok="permission denied" in res.lower() or "InsufficientPrivilege" in res)
    try:
        await app.execute("SELECT public.retention_remove_old_audit_records()")
        res = "succeeded"
    except Exception as e:
        res = f"{type(e).__name__}: {e}"
    ev.row(case="app_backend executes retention_remove_old_audit_records()", result=res, ok=res != "succeeded")
    who = await app.fetchrow("SELECT current_user, session_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user")
    ev.row(case="app_backend role attributes", value=dict(who), ok=not who["rolsuper"] and not who["rolbypassrls"])
    await app.close()
    for sql in ("UPDATE public.audit_log SET action='x' WHERE id=$1", "DELETE FROM public.audit_log WHERE id=$1"):
        tr = db.transaction()
        await tr.start()
        try:
            await db.execute(sql, any_id)
            res = "succeeded"
        except Exception as e:
            res = f"{type(e).__name__}: {e}"
        await tr.rollback()
        ev.row(case=f"owner: {sql.split()[0]} (trigger)", result=res, ok=res != "succeeded")
    jobs = [dict(r) for r in await db.fetch("SELECT jobid, jobname, schedule, command, username, active FROM cron.job ORDER BY jobid")]
    ev.row(case="cron jobs", jobs=jobs, ok=any(j["jobname"] == "audit-retention" and j["username"] == owner_role for j in jobs))
    fn = await db.fetch("SELECT p.proname, pg_get_userbyid(p.proowner) owner, p.proacl::text acl, p.prosecdef FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'retention%'")
    ev.row(case="retention functions", functions=[dict(r) for r in fn], ok=None)
    trig = await db.fetch("SELECT tgname, pg_get_triggerdef(oid) def FROM pg_trigger WHERE tgrelid='public.audit_log'::regclass AND NOT tgisinternal")
    ev.row(case="triggers on audit_log", triggers=[dict(r) for r in trig], ok=len(trig) > 0)
    # Required fields of the records produced by the C checks
    rows = await db.fetch("SELECT * FROM public.audit_log ORDER BY id")
    by_action = defaultdict(list)
    for r in rows:
        by_action[(r["action"], r["outcome"])].append(dict(r))
    fields = []
    for (action, outcome), rs in sorted(by_action.items()):
        def share(col):
            return round(sum(1 for r in rs if r[col] is not None) / len(rs), 3)
        fields.append({"action": action, "outcome": outcome, "n": len(rs), "time": share("occurred_at"), "ip": share("ip"),
                       "user": share("actor_id"), "user_email": share("actor_email"), "affected_record": share("target_id"),
                       "outcome_set": share("outcome"), "request_id": share("request_id")})
    ev.write("field_completeness.json", fields)
    with open(ev.dir / "field_completeness.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(fields[0].keys()))
        w.writeheader()
        w.writerows(fields)
    ev.save({"audit_rows_examined": len(rows)})
    await db.close()
    for r in ev.rows:
        print({True: "OK  ", False: "FAIL", None: "INFO"}[r.get("ok")], r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})
    for f in fields:
        print(f)


CHECKS = {"c1": c1, "c4": c4, "c5": c5, "c6": c6, "c7": c7, "c8": c8, "c9": c9, "c10": c10, "c12": c12, "c14": c14}

if __name__ == "__main__":
    import auth_checks
    CHECKS.update(auth_checks.CHECKS)
    for name in sys.argv[1:]:
        if name == "fixture":
            print(asyncio.run(matrix_fixture(d1mod.load())))
            continue
        asyncio.run(CHECKS[name]())
