"""Chapter 4 functional acceptance checks B-FR01 .. B-FR25 (plan section 5).

Black-box through the running API (V_API, default http://127.0.0.1:8000) on
data set D1 (d1.py) plus objects each check makes for itself. Expected values
come from the definitions in this file and d1.DEFINITION, and from direct
reads of the tables (own queries), never from the API's answers.
B-FR16 drives the daily check in-process with a recording mailer, as
scripts/nfr/three_day_gap.py does (locally RESEND_API_KEY is empty).

    uv run python scripts/verification/acceptance_api.py [fr01 fr02 ...]   # default: all
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
import sys
import time
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone

import httpx

import d1 as d1mod
import vlib
from security_checks import admin_create_auth_user, api_sign_in, rid, routes, tiny_pdf, upload, audit_by_request

IDS = d1mod.load()
ACC = d1mod.accounts(IDS)
T = date.fromisoformat(IDS["today_utc"])
POS = IDS["position"]
TY = IDS["types"]
V = IDS["vessels"]


def iso(d: date) -> str:
    return d.isoformat()


def D(n: int) -> str:
    return iso(T + timedelta(days=n))


async def new_seafarer(c: httpx.Client, first: str, vessel: str | None = None, start: int = 10, end: int = 100,
                       h: dict | None = None) -> tuple[int, int | None]:
    h = h or ACC["A1"].h
    r = c.post("/api/seafarers", json={"first_name": first, "last_name": "Bcheck", "position_id": POS}, headers=h)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    aid = None
    if vessel:
        r = c.post("/api/assignments", json={"seafarer_id": sid, "vessel_id": V[vessel], "position_id": POS,
                                             "start_date": D(start), "end_date": D(end)}, headers=h)
        assert r.status_code == 201, r.text
        aid = r.json()["id"]
    return sid, aid


async def past_assignment(sid: int, vessel: str, start: int, end: int) -> int:
    db = await vlib.owner()
    aid = await db.fetchval("INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date) "
                            "VALUES ($1,$2,$3,$4,$5) RETURNING id", sid, V[vessel], POS, T + timedelta(days=start), T + timedelta(days=end))
    await db.close()
    return aid


def up(c, h, sid, tkey, number="B-NUM", issue=-100, expiry: int | None = 400, not_stated=False, content=None, filename="doc.pdf"):
    return upload(c, h, sid, TY[tkey] if isinstance(tkey, str) else tkey, number=number, issue=D(issue),
                  expiry=D(expiry) if expiry is not None else None, not_stated=not_stated, content=content, filename=filename)


def cur(doc: dict) -> dict | None:
    return next((v for v in doc["versions"] if v["is_current"]), None)


class Checks:
    def __init__(self) -> None:
        self.ev = vlib.Evidence("B")
        self.c = vlib.client(timeout=120)

    def row(self, check: str, part: str, ok: bool | None, **kw):
        r = self.ev.row(check=check, part=part, ok=ok, **kw)
        print({True: "OK  ", False: "FAIL", None: "INFO"}[ok], check, "|", part, "|", {k: v for k, v in kw.items()})
        return r

    # ------------------------------------------------------------------ FR-01
    async def fr01(self):
        c = self.c
        db = await vlib.owner()
        for label, extra in (("plain", {}), ("with role=administrator", {"role": "administrator"})):
            email = f"bfr01-{uuid.uuid4().hex[:6]}@example.com"
            t0 = time.time()
            r = c.post("/api/auth/register", json={"email": email, "full_name": "B Register", "password": "Unusual-Reg-Pass-5521", **extra})
            self.ev.exchange(f"FR01 register {label}", r)
            step = r.json().get("step") if r.status_code == 200 else None
            # Finish registration with the e-mailed code, as a visitor would
            code = vlib.mailpit_code(email, t0, timeout=40)
            v = c.post("/api/auth/verify", json={"email": email, "challenge": r.json()["challenge"], "code": code})
            row = await db.fetchrow("SELECT id, status, role FROM public.users WHERE email=$1", email)
            self.row("B-FR01", f"register {label}: pending, no role", row is not None and row["status"] == "pending" and row["role"] is None,
                     status=r.status_code, step=step, verify_status=v.status_code, next_step=v.json().get("step") if v.content else None,
                     account=dict(status=row["status"], role=row["role"]) if row else None,
                     note="criterion says 201; API answers 200 with the next sign-in step")
            if row:
                await db.execute("INSERT INTO public.verified_session (session_id, user_id) VALUES ($1,$1) ON CONFLICT DO NOTHING", row["id"])
                h = vlib.bearer(vlib.make_token(row["id"], email=email))
                sts = {}
                for m, p in routes(c):
                    if p.startswith("/api/me"):
                        continue
                    rr = c.request(m, re.sub(r"\{[a-z_]+\}", "1", p), headers=h, json={} if m in ("POST", "PUT") else None)
                    sts[f"{m} {p}"] = rr.status_code
                self.row("B-FR01", f"pending account ({label}) gets 403 on every business endpoint",
                         all(s == 403 for s in sts.values()), endpoints=len(sts), non403={k: v for k, v in sts.items() if v != 403})
        await db.close()

    # ------------------------------------------------------------------ FR-02
    async def fr02(self):
        c = self.c
        db = await vlib.owner()
        p2 = await vlib.make_account(db, status="pending", role=None, email=f"bfr02p-{uuid.uuid4().hex[:6]}@example.com")
        p3 = await vlib.make_account(db, status="pending", role=None, email=f"bfr02q-{uuid.uuid4().hex[:6]}@example.com")
        for who in ("O1", "M", "P"):
            r = c.post(f"/api/accounts/{p3.id}/approve", json={"role": "crewing_officer", "reason": "B", "vessel_ids": []}, headers=ACC[who].h)
            self.row("B-FR02", f"{who} approves an account", r.status_code == 403, status=r.status_code)
        r = c.post(f"/api/accounts/{p2.id}/approve", json={"role": "crewing_officer", "reason": "B check", "vessel_ids": [V["V3"]]}, headers=ACC["A1"].h)
        row = await db.fetchrow("SELECT status, role FROM public.users WHERE id=$1", p2.id)
        self.row("B-FR02", "A1 approves with one role", r.status_code == 200 and row["status"] == "active" and row["role"] == "crewing_officer",
                 status=r.status_code, account=dict(row))
        r = c.post(f"/api/accounts/{p2.id}/role", json={"role": "manager", "reason": "B role change"}, headers=ACC["A1"].h)
        row = await db.fetchrow("SELECT status, role FROM public.users WHERE id=$1", p2.id)
        self.row("B-FR02", "A1 changes the role (exactly one)", r.status_code == 200 and row["role"] == "manager", status=r.status_code, account=dict(row))
        for who in ("O1", "M"):
            r = c.post(f"/api/accounts/{p2.id}/role", json={"role": "administrator", "reason": "x"}, headers=ACC[who].h)
            self.row("B-FR02", f"{who} changes a role", r.status_code == 403, status=r.status_code)
        # Deactivate a fresh officer, then it calls every endpoint
        x2 = await vlib.make_account(db, role="crewing_officer", email=f"bfr02x-{uuid.uuid4().hex[:6]}@example.com")
        r = c.post(f"/api/accounts/{x2.id}/deactivate", json={"reason": "B deactivation"}, headers=ACC["A1"].h)
        self.row("B-FR02", "A1 deactivates an account", r.status_code == 200, status=r.status_code)
        sts = {}
        for m, p in routes(c):
            rr = c.request(m, re.sub(r"\{[a-z_]+\}", "1", p), headers=x2.h, json={} if m in ("POST", "PUT") else None)
            sts[f"{m} {p}"] = rr.status_code
        self.row("B-FR02", "deactivated account gets 403 on every endpoint", all(v == 403 for v in sts.values()),
                 endpoints=len(sts), non403={k: v for k, v in sts.items() if v != 403})
        await db.close()

    # ------------------------------------------------------------------ FR-03
    async def fr03(self):
        c = self.c
        name_to_key = {f"{d['first']}": k for k, d in d1mod.DEFINITION["seafarers"].items()}
        for who in ("O1", "O2", "A1"):
            r = c.get("/api/seafarers", headers=ACC[who].h)
            got = {name_to_key[s["first_name"]] for s in r.json() if s["last_name"] == "Dataset"}
            exp = set(d1mod.DEFINITION["seafarers"]) if who == "A1" else d1mod.expected_scope(who)
            self.row("B-FR03", f"{who} seafarer list equals the expected set", got == exp, got=sorted(got), expected=sorted(exp))

    # ------------------------------------------------------------------ FR-04
    async def fr04(self):
        c = self.c
        for who in ("O1", "A1"):
            body = {"first_name": f"Five{who}", "last_name": "Fields", "date_of_birth": "1990-01-31", "nationality": "PL", "position_id": POS}
            r = c.post("/api/seafarers", json=body, headers=ACC[who].h)
            sid = r.json().get("id")
            ok1 = r.status_code == 201 and all(r.json()[k] == v for k, v in body.items())
            body2 = {"first_name": f"Edited{who}", "last_name": "Changed", "date_of_birth": "1991-02-28", "nationality": "LV", "position_id": POS}
            r2 = c.put(f"/api/seafarers/{sid}", json=body2, headers=ACC[who].h)
            ok2 = r2.status_code == 200 and all(r2.json()[k] == v for k, v in body2.items())
            self.row("B-FR04", f"{who} creates with five fields", ok1, status=r.status_code)
            self.row("B-FR04", f"{who} edits all five fields", ok2, status=r2.status_code)
        s1 = IDS["seafarers"]["S1"]
        before = c.get(f"/api/seafarers/{s1}", headers=ACC["A1"].h).json()
        a = c.get(f"/api/assignments/{IDS['assignments']['S1']}", headers=ACC["A1"].h).json()
        r = c.put(f"/api/assignments/{IDS['assignments']['S1']}", json={"vessel_id": V["V3"], "position_id": POS,
                                                                         "start_date": a["start_date"], "end_date": a["end_date"]}, headers=ACC["A1"].h)
        after = c.get(f"/api/seafarers/{s1}", headers=ACC["A1"].h).json()
        c.put(f"/api/assignments/{IDS['assignments']['S1']}", json={"vessel_id": V["V1"], "position_id": POS,
                                                                     "start_date": a["start_date"], "end_date": a["end_date"]}, headers=ACC["A1"].h)
        back = c.get(f"/api/seafarers/{s1}", headers=ACC["A1"].h).json()
        self.row("B-FR04", "current vessel follows the current assignment",
                 before["current_vessel_id"] == V["V1"] and after["current_vessel_id"] == V["V3"] and back["current_vessel_id"] == V["V1"],
                 edit_status=r.status_code, before=before["current_vessel_name"], after=after["current_vessel_name"], back=back["current_vessel_name"])
        r = c.delete(f"/api/seafarers/{IDS['seafarers']['S3']}", headers=ACC["A1"].h)
        self.row("B-FR04", "DELETE /api/seafarers/{id} returns 405", r.status_code == 405, status=r.status_code, allow=r.headers.get("allow"))

    # ------------------------------------------------------------------ FR-05
    async def fr05(self):
        import random
        IMO1, IMO2, IMO3 = (str(random.randint(9200000, 9899999)) for _ in range(3))
        c = self.c
        r = c.post("/api/vessels", json={"name": "B Vessel", "imo_number": IMO1, "flag": "NO"}, headers=ACC["A1"].h)
        vid = r.json().get("id")
        self.row("B-FR05", "A1 creates a vessel (name, IMO, flag)", r.status_code == 201, status=r.status_code)
        r = c.put(f"/api/vessels/{vid}", json={"name": "B Vessel Edited", "imo_number": IMO2, "flag": "DK"}, headers=ACC["A1"].h)
        self.row("B-FR05", "A1 edits name, IMO and flag", r.status_code == 200 and r.json()["imo_number"] == IMO2 and r.json()["flag"] == "DK", status=r.status_code)
        r = c.get("/api/vessels", headers=ACC["O1"].h)
        self.row("B-FR05", "O1 reads vessels", r.status_code == 200, status=r.status_code, n=len(r.json()) if r.status_code == 200 else None)
        r1 = c.post("/api/vessels", json={"name": "O1 Vessel", "imo_number": IMO3, "flag": "NO"}, headers=ACC["O1"].h)
        r2 = c.put(f"/api/vessels/{vid}", json={"name": "O1 edit", "imo_number": IMO2, "flag": "DK"}, headers=ACC["O1"].h)
        self.row("B-FR05", "O1 create / edit -> 403", r1.status_code == 403 and r2.status_code == 403, create=r1.status_code, edit=r2.status_code)

    # ------------------------------------------------------------------ FR-06
    async def fr06(self):
        c = self.c
        sid, _ = await new_seafarer(c, "Fr06")
        h = ACC["A1"].h
        r = c.post("/api/assignments", json={"seafarer_id": sid, "vessel_id": V["V1"], "position_id": POS, "start_date": D(15), "end_date": D(120)}, headers=h)
        aid = r.json().get("id")
        self.row("B-FR06", "assignment with start and end -> 201", r.status_code == 201, status=r.status_code)
        r = c.post("/api/assignments", json={"seafarer_id": sid, "vessel_id": V["V1"], "position_id": POS, "start_date": D(200)}, headers=h)
        self.row("B-FR06", "missing end date -> 422", r.status_code == 422, status=r.status_code)
        r = c.put(f"/api/assignments/{aid}", json={"vessel_id": V["V1"], "position_id": POS, "start_date": D(16), "end_date": D(121)}, headers=h)
        self.row("B-FR06", "edit -> 200", r.status_code == 200, status=r.status_code)
        rd0 = c.get(f"/api/assignments/{aid}/readiness", headers=h)
        r = c.post(f"/api/assignments/{aid}/cancel", json={"reason": "B cancel"}, headers=h)
        self.row("B-FR06", "cancel -> 200", r.status_code == 200, status=r.status_code)
        rd = c.get(f"/api/assignments/{aid}/readiness", headers=h)
        dash = c.get("/api/dashboard", params={"queue": "starting_soon", "limit": 200}, headers=h).json()
        listed = any(a["assignment_id"] == aid for a in dash.get("assignments", []))
        self.row("B-FR06", "cancelled assignment leaves the readiness checks", rd.status_code != 200 and not listed,
                 readiness_before=rd0.status_code, readiness_after=rd.status_code, body=rd.text[:150], in_starting_soon=listed)

    # ------------------------------------------------------------------ FR-07
    async def fr07(self):
        c = self.c
        body = {"name": f"B Endorsement full {uuid.uuid4().hex[:4]}", "expires": True, "max_validity_months": 36, "renewable_at_sea": True, "depends_on_id": TY["COC"]}
        r = c.post("/api/document-types", json=body, headers=ACC["A1"].h)
        self.row("B-FR07", "A1 stores every attribute", r.status_code == 201 and all(r.json()[k] == v for k, v in body.items()),
                 status=r.status_code, stored={k: r.json().get(k) for k in body} if r.status_code == 201 else r.text[:200])
        for who in ("O1", "M"):
            r = c.post("/api/document-types", json={**body, "name": f"{who} type"}, headers=ACC[who].h)
            self.row("B-FR07", f"{who} creates a type -> 403", r.status_code == 403, status=r.status_code)

    # ------------------------------------------------------------------ FR-08
    async def fr08(self):
        c = self.c
        name = {v: k for k, v in TY.items()}
        base = set(d1mod.DEFINITION["required"])
        expect = {"V1": base | {"FAM"}, "V2": base | {"LRE"}, "V3": base}
        for vk in ("V1", "V2", "V3"):
            sid, _ = await new_seafarer(c, f"Fr08{vk}")
            await past_assignment(sid, vk, -5, 90)  # under way: the record's missing strip uses the current vessel
            rec = c.get(f"/api/seafarers/{sid}", headers=ACC["A1"].h).json()
            got = {name[m["document_type_id"]] for m in rec.get("missing_documents", [])}
            ev = c.get("/api/requirements/evaluate", params={"position": POS, "vessel": V[vk]}, headers=ACC["A1"].h).json()
            got_ev = {name[t["id"]] for t in ev["required"]}
            self.row("B-FR08", f"required/missing on {vk} ({d1mod.DEFINITION['vessels'][vk]['flag']})", got == expect[vk] and got_ev == expect[vk],
                     missing=sorted(got), evaluate=sorted(got_ev), expected=sorted(expect[vk]))

    # ------------------------------------------------------------------ FR-09
    async def fr09(self):
        c = self.c
        db = await vlib.owner()
        sid, _ = await new_seafarer(c, "Fr09", "V1", 5, 90)
        h = ACC["O1"].h
        r = up(c, h, sid, "COC", "FR09-1")
        v = cur(r.json()) if r.status_code == 201 else None
        self.row("B-FR09", "valid upload -> version 1 awaiting review (201)", r.status_code == 201 and v["number"] == 1 and v["review_state"] == "not_reviewed",
                 status=r.status_code, number=v and v["number"], review_state=v and v["review_state"])
        n0 = await db.fetchval("SELECT count(*) FROM public.document WHERE seafarer_id=$1", sid)
        r = up(c, h, sid, "BST", "FR09-2", expiry=None)
        n1 = await db.fetchval("SELECT count(*) FROM public.document WHERE seafarer_id=$1", sid)
        self.row("B-FR09", "expiring type without a date -> 422, nothing created", r.status_code == 422 and n1 == n0, status=r.status_code, created=n1 - n0)
        r = up(c, h, sid, "BST", "FR09-3", expiry=None, not_stated=True)
        v = cur(r.json()) if r.status_code == 201 else None
        self.row("B-FR09", "'Expiry not stated' ticked -> 201 without a date", r.status_code == 201 and v["expiry_date"] is None,
                 status=r.status_code, expiry_status=r.json().get("expiry_status") if r.status_code == 201 else None)
        await db.close()

    # ------------------------------------------------------------------ FR-10 .. FR-13
    async def fr10_13(self):
        c = self.c
        db = await vlib.owner()
        sid, _ = await new_seafarer(c, "Fr10", "V1", 5, 90)
        hO, hA, hA2 = ACC["O1"].h, ACC["A1"].h, ACC["A2"].h
        d = up(c, hO, sid, "COC", "FR10-A", expiry=500).json()
        doc = d["id"]
        objs0 = await db.fetchval("SELECT count(*) FROM storage.objects WHERE bucket_id='crew-documents'")
        d2 = up(c, hO, sid, "COC", "FR10-A", expiry=500, content=tiny_pdf("second file")).json()
        v2 = cur(d2)
        objs1 = await db.fetchval("SELECT count(*) FROM storage.objects WHERE bucket_id='crew-documents'")
        self.row("B-FR10", "new file -> next version awaiting review", v2["number"] == 2 and v2["review_state"] == "not_reviewed" and objs1 == objs0 + 1,
                 number=v2["number"], state=v2["review_state"], new_objects=objs1 - objs0)
        r = c.post(f"/api/documents/{doc}/versions", json={"document_number": "FR10-B", "issuing_authority": "D1 Authority",
                                                           "issue_date": D(-100), "expiry_date": D(500)}, headers=hO)
        v3 = cur(r.json())
        objs2 = await db.fetchval("SELECT count(*) FROM storage.objects WHERE bucket_id='crew-documents'")
        paths = await db.fetch("SELECT id, file_path FROM public.version WHERE document_id=$1 ORDER BY id", doc)
        same = paths[-1]["file_path"] == paths[-2]["file_path"]
        self.row("B-FR10", "details-only change -> next version, same stored object, no new object",
                 r.status_code == 201 and v3["number"] == 3 and v3["review_state"] == "not_reviewed" and same and objs2 == objs1,
                 status=r.status_code, number=v3["number"], file_from=v3["file_from_version_number"], same_path=same, new_objects=objs2 - objs1)
        full = c.get(f"/api/documents/{doc}", headers=hO).json()
        v1 = next(v for v in full["versions"] if v["number"] == 1)
        fu = c.post(f"/api/versions/{v1['id']}/file-url", headers=hO)
        g = httpx.get(fu.json()["url"], timeout=30) if fu.status_code == 200 else None
        self.row("B-FR10", "earlier versions stay readable (details and file)", len(full["versions"]) == 3 and v1["document_number"] == "FR10-A" and g is not None and g.status_code == 200,
                 versions=len(full["versions"]), v1_file=g.status_code if g else fu.status_code)
        nv = await db.fetchval("SELECT count(*) FROM public.version WHERE document_id=$1", doc)
        r = c.post(f"/api/versions/{v3['id']}/reviews", json={"decision": "accept", "comment": "Looks fine"}, headers=hA)
        nv2 = await db.fetchval("SELECT count(*) FROM public.version WHERE document_id=$1", doc)
        self.row("B-FR10", "a review comment creates no version", r.status_code in (200, 201) and nv2 == nv, status=r.status_code, versions_before=nv, after=nv2)
        # FR-11
        r = c.post(f"/api/versions/{v3['id']}/reviews", json={"decision": "accept", "comment": "own"}, headers=hO)
        self.row("B-FR11", "review by the uploader -> 403", r.status_code == 403, status=r.status_code)
        r = c.post(f"/api/versions/{v3['id']}/reviews", json={"decision": "reject", "comment": "Later decision by A2"}, headers=hA2)
        full = c.get(f"/api/documents/{doc}", headers=hA).json()
        v3r = next(v for v in full["versions"] if v["id"] == v3["id"])
        decs = [(x["decision"], x["reviewed_by_name"]) for x in v3r["reviews"]]
        self.row("B-FR11", "later decision supersedes, both kept", len(v3r["reviews"]) == 2 and v3r["review_state"] == "rejected",
                 status=r.status_code, reviews=decs, state=v3r["review_state"], current_now=cur(full)["number"] if cur(full) else None)
        for m in ("PUT", "PATCH", "DELETE"):
            r = c.request(m, f"/api/versions/{v3['id']}/reviews", json={"decision": "accept", "comment": "x"}, headers=hA)
            self.row("B-FR11", f"{m} on a decision -> 405", r.status_code == 405, status=r.status_code)
        # FR-12 (on a fresh document)
        d = up(c, hO, sid, "MED", "FR12-1", expiry=300).json()
        vv = cur(d)
        r = c.post(f"/api/versions/{vv['id']}/verifications", data={"checked_on": iso(T), "source": "Issuer registry", "result": "not_confirmed", "reference": "R1"}, headers=hA)
        st0 = r.json()["verified"]
        r = c.post(f"/api/versions/{vv['id']}/verifications", data={"checked_on": iso(T), "source": "Issuer registry", "result": "confirmed", "reference": "R2"}, headers=hA)
        st1 = r.json()["verified"]
        d2 = up(c, hO, sid, "MED", "FR12-2", expiry=310).json()
        self.row("B-FR12", "'verified' only with a confirmed record on the current version, then 'not verified' after a new version",
                 st0 is False and st1 is True and d2["verified"] is False, not_confirmed=st0, confirmed=st1, after_new_version=d2["verified"])
        # FR-13
        d = up(c, hO, sid, "FAM", "FR13-1", expiry=200).json()
        doc13 = d["id"]
        c.post(f"/api/versions/{cur(d)['id']}/reviews", json={"decision": "accept", "comment": "ok 1"}, headers=hA)
        d = up(c, hO, sid, "FAM", "FR13-2", expiry=210).json()
        c.post(f"/api/versions/{cur(d)['id']}/verifications", data={"checked_on": iso(T), "source": "S", "result": "confirmed", "reference": "R"}, headers=hA)
        c.post(f"/api/documents/{doc13}/versions", json={"document_number": "FR13-3", "issuing_authority": "D1 Authority", "issue_date": D(-100), "expiry_date": D(220)}, headers=hO)
        full = c.get(f"/api/documents/{doc13}", headers=hA).json()
        fields = all(all(k in v for k in ("uploaded_by_name", "uploaded_at", "document_number", "issuing_authority", "issue_date", "expiry_date", "reviews", "verifications")) for v in full["versions"])
        self.row("B-FR13", "three versions, three entries with uploader, time, details, reviews and verifications",
                 len(full["versions"]) == 3 and fields and any(v["reviews"] for v in full["versions"]) and any(v["verifications"] for v in full["versions"]),
                 entries=[(v["number"], v["uploaded_by_name"], v["document_number"], len(v["reviews"]), len(v["verifications"])) for v in full["versions"]])
        await db.close()

    # ------------------------------------------------------------------ FR-14 / FR-15
    async def fr15(self):
        c = self.c
        hA = ACC["A1"].h
        sid, _ = await new_seafarer(c, "Fr15", "V3", 5, 90)
        steps = c.get("/api/settings", headers=hA).json()["alert_steps"]
        largest = max(steps)
        cases = [("today", 0, "expiring_soon"), ("tomorrow", 1, "expiring_soon"), (f"in exactly {largest} days", largest, "expiring_soon"),
                 (f"in {largest + 1} days", largest + 1, "unexpired"), ("yesterday", -1, "expired")]
        for name, n, exp in cases:
            t = c.post("/api/document-types", json={"name": f"B15 {name} {uuid.uuid4().hex[:4]}", "expires": True}, headers=hA).json()["id"]
            r = upload(c, ACC["O1"].h if False else hA, sid, t, number=f"FR15-{n}", issue=D(-400), expiry=D(n))
            st = r.json().get("expiry_status") if r.status_code == 201 else r.text[:120]
            self.row("B-FR15", f"expiry {name} -> {exp}", st == exp, status=r.status_code, got=st)
        r = up(c, hA, sid, "BOOK", "FR15-BOOK", expiry=None)
        self.row("B-FR15", "type that does not expire, no date -> no expiry date", r.json().get("expiry_status") == "no_expiry_date", got=r.json().get("expiry_status"))
        r = up(c, hA, sid, "BST", "FR15-NS", expiry=None, not_stated=True)
        self.row("B-FR15", "expiring type, no date -> expiry not stated", r.json().get("expiry_status") == "expiry_not_stated", got=r.json().get("expiry_status"))
        # awaiting-review versions are included (all above are unreviewed)
        self.row("B-FR15", "versions awaiting review get a status (all the above are unreviewed)", True, note="see rows above")
        # FR-14 endorsement, both date orders
        for label, coc_exp, end_exp in (("certificate first", 50, 400), ("endorsement first", 400, 50)):
            s2, _ = await new_seafarer(c, f"Fr14{label[:4]}", "V3", 5, 90)
            up(c, hA, s2, "COC", "COC", expiry=coc_exp)
            r = up(c, hA, s2, "END", "END", expiry=end_exp)
            j = r.json()
            exp_eff = D(min(coc_exp, end_exp))
            self.row("B-FR14", f"effective expiry = earlier date ({label})", j.get("effective_expiry") == exp_eff and j.get("expiry_status") == "expiring_soon",
                     effective=j.get("effective_expiry"), expected=exp_eff, status=j.get("expiry_status"), capped_by=j.get("capped_by"))
        s3, a3 = await new_seafarer(c, "Fr14nocert", "V3", 5, 90)
        r = up(c, hA, s3, "END", "END-alone", expiry=400)
        j = r.json()
        rd = c.get(f"/api/assignments/{a3}/readiness", headers=hA).json()
        endrow = [e for b in rd["buckets"].values() for e in b if e["document_type_id"] == TY["END"]]
        self.row("B-FR14", "endorsement without a recorded certificate -> expired and expires before the start",
                 j.get("expiry_status") == "expired" and endrow and endrow[0]["coverage"] == "runs_out_before_start",
                 status=j.get("expiry_status"), certificate_missing=j.get("certificate_missing"), coverage=endrow[0]["coverage"] if endrow else None)
        # One date not stated: COC not stated, END dated
        s4, a4 = await new_seafarer(c, "Fr14ns", "V3", 5, 90)
        up(c, hA, s4, "COC", "COC-ns", expiry=None, not_stated=True)
        r = up(c, hA, s4, "END", "END-dated-far", expiry=400)
        r2 = None
        self.row("B-FR14", "certificate date not stated, endorsement far away -> expiry not stated", r.json().get("expiry_status") == "expiry_not_stated",
                 got=r.json().get("expiry_status"))
        s5, a5 = await new_seafarer(c, "Fr14ns2", "V3", 5, 90)
        up(c, hA, s5, "COC", "COC-ns", expiry=None, not_stated=True)
        r = up(c, hA, s5, "END", "END-dated-soon", expiry=20)
        self.row("B-FR14", "certificate date not stated, endorsement in 20 days -> expiring soon (known date decides)", r.json().get("expiry_status") == "expiring_soon",
                 got=r.json().get("expiry_status"))

    # ------------------------------------------------------------------ FR-16 (daily check in-process)
    async def fr16(self):
        sys.path.insert(0, str(vlib.ROOT / "backend"))
        import asyncpg
        from app.services import daily_check

        class RecordingMailer:
            def __init__(self):
                self.sent = []

            async def send(self, to, subject, html):
                self.sent.append({"to": to, "subject": subject, "html": html})

        class NoStorage:
            async def upload(self, *a): ...
            async def delete(self, *a): ...

        c = self.c
        hA = ACC["A1"].h
        owner = await vlib.owner()
        await owner.execute("TRUNCATE public.alert_delivery, public.alert, public.daily_check_run")
        await owner.execute("UPDATE public.settings SET daily_check_time='00:00', time_zone='UTC', alert_steps='{90,60,30,0}'")
        # Documents for seafarers on V1 (officer O1) and on V3 (no officer -> administrators)
        s_v1, _ = await new_seafarer(c, "Fr16v1", "V1", 3, 90)
        s_v3, _ = await new_seafarer(c, "Fr16v3", "V3", 3, 90)
        cases = {}
        for n, tkey_name in ((90, "90"), (60, "60"), (30, "30"), (0, "0"), (91, "91"), (25, "25")):
            t = c.post("/api/document-types", json={"name": f"B16 in {tkey_name} {uuid.uuid4().hex[:4]}", "expires": True}, headers=hA).json()["id"]
            d = upload(c, hA, s_v1, t, number=f"SECRET-NUM-{n}", issue=D(-400), expiry=D(n)).json()
            cases[n] = (t, d["id"])
        t3 = c.post("/api/document-types", json={"name": f"B16 v3 in 30 {uuid.uuid4().hex[:4]}", "expires": True}, headers=hA).json()["id"]
        d3 = upload(c, hA, s_v3, t3, number="SECRET-NUM-V3", issue=D(-400), expiry=D(30)).json()
        app = await asyncpg.connect(vlib.APP_DB_URL)
        mailer = RecordingMailer()
        now = datetime.combine(T, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=1)
        res = await daily_check.run_if_due(app, mailer, now=now, storage=NoStorage())
        alerts = [dict(r) for r in await owner.fetch("SELECT a.document_id, a.step, a.expiry_date, a.skipped FROM public.alert a ORDER BY id")]
        by_doc = defaultdict(list)
        skipped_by_doc = defaultdict(list)
        for a in alerts:
            (skipped_by_doc if a["skipped"] else by_doc)[a["document_id"]].append(a["step"])
        exp = {90: [90], 60: [60], 30: [30], 0: [0], 91: [], 25: [30]}
        for n, (t, doc) in cases.items():
            self.row("B-FR16", f"document expiring in {n} days -> alert steps {exp[n]}", sorted(by_doc.get(doc, [])) == exp[n], got=by_doc.get(doc, []), stored_as_skipped=skipped_by_doc.get(doc, []))
        # Repeat: no new alerts
        res2 = await daily_check.run_if_due(app, mailer, now=now + timedelta(hours=2), storage=NoStorage())
        n_alerts = await owner.fetchval("SELECT count(*) FROM public.alert")  # incl. skipped rows
        self.row("B-FR16", "a second run the same day adds nothing", n_alerts == len(alerts), first=len(alerts), after=n_alerts, second_run=str(res2))
        # New version with the same expiry date: none
        t60, doc60 = cases[60]
        upload(c, hA, s_v1, t60, number="SECRET-NUM-60b", issue=D(-300), expiry=D(60))
        await owner.execute("DELETE FROM public.daily_check_run")
        await daily_check.run_if_due(app, mailer, now=now + timedelta(hours=3), storage=NoStorage())
        n60 = await owner.fetchval("SELECT count(*) FROM public.alert WHERE document_id=$1 AND NOT skipped", doc60)
        self.row("B-FR16", "a new version with the same expiry date creates no alert", n60 == 1, alerts_for_doc=n60)
        # Recipients and content
        emails = {a.email: k for k, a in ACC.items()}
        to = Counter(emails.get(m["to"], m["to"]) for m in mailer.sent)
        leaked = [m["to"] for m in mailer.sent if "SECRET-NUM" in m["html"] or "SECRET-NUM" in m["subject"]]
        admins = {r["email"] for r in await owner.fetch("SELECT email FROM public.users WHERE role='administrator' AND status='active'")}
        v3_mails = [m for m in mailer.sent if "Fr16v3" in m["html"]]
        v1_mails = [m for m in mailer.sent if "Fr16v1" in m["html"]]
        self.row("B-FR16", "e-mail for V1 documents goes to V1's officer (O1)", {emails.get(m["to"]) for m in v1_mails} == {"O1"},
                 recipients=sorted({emails.get(m["to"], m["to"]) for m in v1_mails}))
        self.row("B-FR16", "e-mail for a vessel without an officer goes to the administrators", {m["to"] for m in v3_mails} == admins,
                 recipients=sorted(emails.get(m["to"], m["to"]) for m in v3_mails), admins=len(admins))
        self.row("B-FR16", "never to managers", not any(emails.get(m["to"]) == "M" for m in mailer.sent), sent_to=dict(to))
        self.row("B-FR16", "no document number in any e-mail", not leaked, mails=len(mailer.sent))
        self.ev.write("fr16_mails.json", [{"to": emails.get(m["to"], m["to"]), "subject": m["subject"], "html": m["html"]} for m in mailer.sent])
        # In the application
        seen = {}
        for who in ("O1", "O2", "A1", "M"):
            r = c.get("/api/alerts", headers=ACC[who].h)
            body = r.json() if r.status_code == 200 else []
            docs = {a.get("document_id") for a in body} if isinstance(body, list) else set()
            seen[who] = (r.status_code, len(docs & {d for _, d in cases.values()}), d3["id"] in docs)
        self.row("B-FR16", "officers in scope and administrators see the alerts; O2 not; manager none",
                 seen["O1"][0] == 200 and seen["O1"][1] == 5 and not seen["O1"][2] and seen["A1"][1] == 5 and seen["A1"][2]
                 and seen["O2"][1] == 0 and seen["M"][0] in (403,) , seen=seen)
        await app.close()
        await owner.close()

    # ------------------------------------------------------------------ FR-17
    async def fr17(self):
        c = self.c
        hA = ACC["A1"].h
        sid, _ = await new_seafarer(c, "Fr17", "V3", 5, 90)
        for k in ("COC", "MED", "BST"):
            up(c, hA, sid, k, f"FR17-{k}", expiry=300)
        rec = c.get(f"/api/seafarers/{sid}", headers=hA).json()
        miss = [m["document_type_id"] for m in rec["missing_documents"]]
        self.row("B-FR17", "three of four -> exactly the fourth is missing", miss == [TY["END"]], missing=miss)
        up(c, hA, sid, "END", "FR17-END", expiry=300)
        rec = c.get(f"/api/seafarers/{sid}", headers=hA).json()
        self.row("B-FR17", "all four -> complete (no missing documents)", rec["missing_documents"] == [], missing=rec["missing_documents"],
                 label_note="the API returns an empty list; the web client shows 'No required documents missing'")

    # ------------------------------------------------------------------ FR-18 / FR-19
    async def fr18_19(self):
        c = self.c
        hA = ACC["A1"].h
        # upcoming on V2: start T+20, end T+120; required COC END MED BST LRE
        sid, aid = await new_seafarer(c, "Fr18", "V2", 20, 120)
        up(c, hA, sid, "COC", "C", expiry=19)        # before start
        up(c, hA, sid, "MED", "M", expiry=20)        # on start date: during (renewable at sea)
        up(c, hA, sid, "BST", "B", expiry=120)       # on end date: during (not renewable at sea)
        up(c, hA, sid, "LRE", "L", expiry=None, not_stated=True)  # not stated
        # END missing
        rd = c.get(f"/api/assignments/{aid}/readiness", headers=hA)
        j = rd.json()
        name = {v: k for k, v in TY.items()}
        entries = {}
        for b, es in j["buckets"].items():
            for e in es:
                entries.setdefault(name.get(e["document_type_id"]), e)
                entries[name.get(e["document_type_id"])].setdefault("_buckets", []).append(b)
        exp = {"COC": "runs_out_before_start", "MED": "runs_out_during", "BST": "runs_out_during", "LRE": "expiry_not_stated", "END": "missing"}
        for k, e in exp.items():
            self.row("B-FR18", f"{k}: coverage {e}", entries.get(k, {}).get("coverage") == e, got=entries.get(k, {}).get("coverage"),
                     buckets=entries.get(k, {}).get("_buckets"))
        # covers: after the end
        sid2, aid2 = await new_seafarer(c, "Fr18b", "V3", 20, 120)
        up(c, hA, sid2, "COC", "C", expiry=121)
        up(c, hA, sid2, "BOOK", "BOOK", expiry=None)
        db = await vlib.owner()
        await db.execute("INSERT INTO public.position_requirement (position_id, document_type_id) VALUES ($1,$2) ON CONFLICT DO NOTHING", POS, TY["BOOK"])
        j2 = c.get(f"/api/assignments/{aid2}/readiness", headers=hA).json()
        await db.execute("DELETE FROM public.position_requirement WHERE position_id=$1 AND document_type_id=$2", POS, TY["BOOK"])
        await db.close()
        e2 = {name.get(e["document_type_id"]): e for es in j2["buckets"].values() for e in es}
        self.row("B-FR18", "expiry after the end -> covers the assignment", e2.get("COC", {}).get("coverage") == "covers_all", got=e2.get("COC", {}).get("coverage"))
        self.row("B-FR18", "no date on a type that does not expire -> covers", e2.get("BOOK", {}).get("coverage") == "covers_all", got=e2.get("BOOK", {}).get("coverage"))
        self.row("B-FR18", "no document -> missing", e2.get("END", {}).get("coverage") == "missing", got=e2.get("END", {}).get("coverage"))
        # FR-19
        sep = all(all(k in e for k in ("coverage", "expiry_date", "review_state", "verified")) for e in entries.values())
        self.row("B-FR19", "coverage class, expiry date, review status and verification are separate fields", sep, fields=sorted(next(iter(entries.values())).keys()))
        sug = {k: entries[k].get("suggestion") for k in ("MED", "BST") if k in entries}
        self.row("B-FR19", "advice differs for a type renewable at sea", sug.get("MED") != sug.get("BST") and sug.get("MED") is not None,
                 suggestions=sug, med_bucket=entries.get("MED", {}).get("_buckets"), bst_bucket=entries.get("BST", {}).get("_buckets"))
        problems = {"missing": "END" in entries and "before_joining" in entries["END"]["_buckets"],
                    "awaiting review": all("not_reviewed" in entries[k]["_buckets"] for k in ("COC", "MED", "BST", "LRE")),
                    "expiring": "before_joining" in entries["COC"]["_buckets"],
                    "expiry not stated": "expiry_not_stated" in entries["LRE"]["_buckets"]}
        self.row("B-FR19", "missing, awaiting review, expiring and 'expiry not stated' are put in highlighted groups", all(problems.values()),
                 groups=problems, counters=j["counters"])
        # only rejected versions -> missing
        sid3, aid3 = await new_seafarer(c, "Fr19rej", "V3", 20, 120)
        d = up(c, ACC["A2"].h, sid3, "COC", "C", expiry=400).json()
        c.post(f"/api/versions/{cur(d)['id']}/reviews", json={"decision": "reject", "comment": "bad"}, headers=hA)
        j3 = c.get(f"/api/assignments/{aid3}/readiness", headers=hA).json()
        e3 = {name.get(e["document_type_id"]): e for es in j3["buckets"].values() for e in es}
        self.row("B-FR19", "a document with only rejected versions appears as missing", e3.get("COC", {}).get("coverage") == "missing", got=e3.get("COC", {}).get("coverage"))
        txt = json.dumps(j).lower() + json.dumps(j2).lower()
        bad = [p for p in ("may not serve", "must not serve", "cannot serve", "not allowed to serve", "not fit", "unfit", "may not join", "cannot join") if p in txt]
        self.row("B-FR19", "no 'may not serve' statement in the readiness answers", not bad, found=bad)
        self.ev.write("fr19_readiness.json", j)

    # ------------------------------------------------------------------ FR-20 (counts vs own SQL)
    async def fr20(self):
        c = self.c
        db = await vlib.owner()
        exp = await own_dashboard_counts(db)
        for who in ("A1", "O1"):
            r = c.get("/api/dashboard", headers=ACC[who].h)
            got = r.json()["counts"]
            e = exp[who]
            self.row("B-FR20", f"{who} dashboard counts equal own SQL counts", {k: got[k] for k in e} == e, got=got, expected=e)
        # filters
        for who in ("A1",):
            for flt, val, test in (("vessel_id", V["V1"], lambda s: s["current_vessel_id"] == V["V1"]),
                                   ("position_id", POS, lambda s: s["position_id"] == POS),
                                   ("name", "Sone", lambda s: "sone" in (s["first_name"] + " " + s["last_name"]).lower())):
                ok = True
                seen = 0
                for q in ("missing", "expired", "expiring_soon", "waiting_for_review", "in_order", "expiry_not_stated"):
                    r = c.get("/api/dashboard", params={flt: val, "queue": q, "limit": 200}, headers=ACC[who].h).json()
                    for g in r["groups"]:
                        seen += 1
                        ok &= test(g["seafarer"])
                self.row("B-FR20", f"filter {flt}={val} returns only matching rows", ok and seen > 0, rows=seen)
            ty = TY["COC"]
            ok, seen = True, 0
            for q in ("missing", "expired", "expiring_soon", "waiting_for_review", "in_order"):
                r = c.get("/api/dashboard", params={"document_type_id": ty, "queue": q, "limit": 200}, headers=ACC[who].h).json()
                for g in r["groups"]:
                    for e in g["entries"]:
                        seen += 1
                        ok &= e["document_type_id"] == ty
            self.row("B-FR20", "filter document_type_id returns only that type", ok and seen > 0, rows=seen)
            r = c.get("/api/dashboard", params={"ashore": "true", "queue": "missing", "limit": 200}, headers=ACC[who].h).json()
            self.row("B-FR20", "filter ashore returns only seafarers without a current vessel", all(g["seafarer"]["current_vessel_id"] is None for g in r["groups"]), rows=len(r["groups"]))
        r = c.get("/api/dashboard/totals", headers=ACC["M"].h)
        txt = r.text
        names_leak = [n for n in ("Sone", "Stwo", "Dataset", "Bcheck") if n in txt]
        self.row("B-FR20", "manager gets fleet totals without names", r.status_code == 200 and not names_leak, status=r.status_code, leak=names_leak, totals=r.json() if r.status_code == 200 else None)
        rd = c.get("/api/dashboard", headers=ACC["M"].h)
        self.row("B-FR20", "manager on the named dashboard", None, status=rd.status_code)
        await db.close()

    # ------------------------------------------------------------------ FR-21
    async def fr21(self):
        import pikepdf
        c = self.c
        for who in ("A1", "O1"):
            for kind, path in (("vessel V1", f"/api/vessels/{V['V1']}/report"), ("assignment S1", f"/api/assignments/{IDS['assignments']['S1']}/report")):
                for fmt in ("csv", "pdf"):
                    r = c.get(path, params={"format": fmt}, headers=ACC[who].h)
                    info = {"status": r.status_code, "ctype": r.headers.get("content-type"), "bytes": len(r.content)}
                    ok = r.status_code == 200
                    if ok and fmt == "csv":
                        rows = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
                        hdr = [h.lower() for h in rows[0]] if rows else []
                        info["header"] = rows[0] if rows else None
                        info["rows"] = len(rows) - 1
                        need = ("coverage", "expir", "review", "verif")
                        info["separate_columns"] = {n: any(n in h for h in hdr) for n in need}
                        ok = all(info["separate_columns"].values())
                    if ok and fmt == "pdf":
                        pdf = pikepdf.open(io.BytesIO(r.content))
                        text = b"".join(pikepdf.Pdf.get_object(pdf, x.objgen).read_bytes() for x in pdf.objects if isinstance(x, pikepdf.Stream) and "/Length" in x and x.get("/Subtype") is None)
                        low = text.lower()
                        info["pdf_has"] = {n: n.encode() in low for n in ("coverage", "expir", "review", "verif")}
                        ok = r.content[:5] == b"%PDF-"
                    self.row("B-FR21", f"{who} {kind} {fmt.upper()}", ok, **info)
        for kind, path in (("vessel V1", f"/api/vessels/{V['V1']}/report"), ("assignment S1", f"/api/assignments/{IDS['assignments']['S1']}/report")):
            r = c.get(path, params={"format": "csv"}, headers=ACC["O2"].h)
            self.row("B-FR21", f"O2 asks for {kind} (outside scope) -> 403/404", r.status_code in (403, 404), status=r.status_code)
        r = c.get(f"/api/vessels/{V['V1']}/report", params={"format": "csv"}, headers=ACC["M"].h)
        self.row("B-FR21", "manager asks for a vessel report", None, status=r.status_code, note="Table 7/UC-14 give managers reports")

    # ------------------------------------------------------------------ FR-22
    async def fr22(self):
        c = self.c
        db = await vlib.owner()
        hA = ACC["A1"].h
        sid, aid = await new_seafarer(c, "Fr22", "V1", 5, 90)
        acct_email = f"bfr22-{uuid.uuid4().hex[:6]}@example.com"
        pw = "Verif-" + uuid.uuid4().hex[:12]
        uid = admin_create_auth_user(acct_email, pw)
        await db.execute("UPDATE public.users SET status='active', role='crewing_officer' WHERE id=$1", uid)
        api_sign_in(c, acct_email, pw, None)  # enrol (its success is recorded too)
        d = up(c, ACC["O1"].h, sid, "COC", "FR22", expiry=300).json()
        ver = cur(d)["id"]
        st = c.get("/api/settings", headers=hA).json()
        body_settings = {k: st[k] for k in ("alert_steps", "planning_horizon_days", "max_file_size_mb", "max_pdf_pages", "time_zone",
                                           "daily_check_time", "retention_replaced_version_years", "retention_inactive_seafarer_years",
                                           "retention_audit_record_years", "version")}
        events = [
            ("login succeeded", "POST", "/api/auth/login", None, "login"),
            ("login failed (wrong password)", "POST", "/api/auth/login", {"email": acct_email, "password": "Wrong-Pass-x1"}, None),
            ("refused: wrong role", "GET", "/api/audit", None, "O1"),
            ("refused: out of scope", "GET", f"/api/seafarers/{IDS['seafarers']['S2']}", None, "O1"),
            ("refused: forged token", "GET", "/api/me", None, "forged"),
            ("record changed (seafarer edit)", "PUT", f"/api/seafarers/{sid}", {"first_name": "Fr22e", "last_name": "Bcheck", "position_id": POS}, "A1"),
            ("setting changed", "PUT", "/api/settings", {**body_settings, "planning_horizon_days": 91}, "A1"),
            ("review", "POST", f"/api/versions/{ver}/reviews", {"decision": "accept", "comment": "ok"}, "A1"),
            ("verification", "POST", f"/api/versions/{ver}/verifications", "verif", "A1"),
            ("file URL", "POST", f"/api/versions/{ver}/file-url", None, "A1"),
        ]
        for name, m, p, body, who in events:
            rq = rid()
            hdr = {"X-Request-ID": rq, "X-Forwarded-For": "198.51.100.122"}
            if who == "login":
                r0 = c.post("/api/auth/login", json={"email": acct_email, "password": pw}, headers=hdr)
                import pyotp  # noqa
                # code from the stored secret is not known here: use a second full sign-in instead
                r = r0
                rq_login = rq
            elif who is None:
                r = c.post(p, json=body, headers=hdr)
            elif who == "forged":
                r = c.get(p, headers={**hdr, **vlib.bearer(vlib.make_token(ACC["A1"].id, key="forged-forged-forged-forged-forged"))})
            elif body == "verif":
                r = c.post(p, data={"checked_on": iso(T), "source": "S", "result": "confirmed", "reference": "R"}, headers={**ACC[who].h, **hdr})
            else:
                r = c.request(m, p, json=body, headers={**ACC[who].h, **hdr})
            recs = (await audit_by_request(db, [rq])).get(rq, [])
            if who == "login":
                self.row("B-FR22", f"{name}: password step records nothing yet (the record comes after the code)", len(recs) == 0,
                         status=r.status_code, records=[(x["action"], x["outcome"]) for x in recs])
                continue
            self.row("B-FR22", f"{name}: exactly one audit record", len(recs) == 1, status=r.status_code,
                     records=[(x["action"], x["outcome"], x["reason"]) for x in recs])
        # A whole successful login (password + code): one login_succeeded
        a = {"email": f"bfr22b-{uuid.uuid4().hex[:6]}@example.com", "password": "Verif-" + uuid.uuid4().hex[:12]}
        uid2 = admin_create_auth_user(a["email"], a["password"])
        await db.execute("UPDATE public.users SET status='active', role='manager' WHERE id=$1", uid2)
        start = await vlib.max_audit_id(db)
        res, _ = api_sign_in(c, a["email"], a["password"], None)
        recs = [x for x in await vlib.audit_after(db, start) if x["actor_id"] == uid2]
        self.row("B-FR22", "login succeeded (password and code): exactly one record", Counter(x["action"] for x in recs) == Counter({"login_succeeded": 1}),
                 status=res["status"], records=[(x["action"], x["outcome"]) for x in recs])
        # Deletion by retention: see B-FR24 (records written by the retention functions)
        await db.execute("UPDATE public.settings SET planning_horizon_days=90")
        await db.close()

    # ------------------------------------------------------------------ FR-23
    async def fr23(self):
        c = self.c
        hA = ACC["A1"].h
        r1 = c.get("/api/audit", headers=hA)
        r2 = c.get("/api/audit", params={"action": "access_refused", "outcome": "refused", "page_size": 50}, headers=hA)
        filt_ok = r2.status_code == 200 and all(x["action"] == "access_refused" for x in r2.json().get("items", r2.json() if isinstance(r2.json(), list) else []))
        r3 = c.get("/api/audit/export.csv", params={"action": "access_refused"}, headers=hA)
        self.row("B-FR23", "A1 views, filters and exports (200)", r1.status_code == 200 and filt_ok and r3.status_code == 200 and r3.content.count(b"\n") > 1,
                 view=r1.status_code, filter=r2.status_code, export=r3.status_code, export_lines=r3.content.count(b"\n"), keys=list(r2.json().keys()) if isinstance(r2.json(), dict) else None)
        for who in ("O1", "M"):
            a, b = c.get("/api/audit", headers=ACC[who].h), c.get("/api/audit/export.csv", headers=ACC[who].h)
            self.row("B-FR23", f"{who} -> 403", a.status_code == 403 and b.status_code == 403, view=a.status_code, export=b.status_code)
        spec = c.get("/openapi.json").json()
        bad = [(m, p) for p, ops in spec["paths"].items() for m in ops if "audit" in p and m.upper() != "GET"]
        self.row("B-FR23", "no route changes or deletes audit records (OpenAPI)", not bad, non_get_audit_routes=bad)
        for m in ("PUT", "PATCH", "DELETE", "POST"):
            r = c.request(m, "/api/audit", headers=hA)
            self.row("B-FR23", f"{m} /api/audit", r.status_code == 405, status=r.status_code)

    # ------------------------------------------------------------------ FR-24
    async def fr24(self):
        sys.path.insert(0, str(vlib.ROOT / "backend"))
        c = self.c
        hA = ACC["A1"].h
        db = await vlib.owner()
        await db.execute("UPDATE public.settings SET retention_replaced_version_years=1, retention_inactive_seafarer_years=1, retention_audit_record_years=1")
        sid, _ = await new_seafarer(c, "Fr24", "V3", 5, 90)
        d = up(c, hA, sid, "COC", "R1", expiry=300).json()
        up(c, hA, sid, "COC", "R2", expiry=310)
        d3 = up(c, hA, sid, "COC", "R3", expiry=320).json()
        # details-only version that reuses the file of the current one, then age everything by 2 years
        r = c.post(f"/api/documents/{d['id']}/versions", json={"document_number": "R4", "issuing_authority": "D1 Authority", "issue_date": D(-100), "expiry_date": D(330)}, headers=hA)
        vers = [dict(x) for x in await db.fetch("SELECT id, file_path, uploaded_at FROM public.version WHERE document_id=$1 ORDER BY id", d["id"])]
        # Age through the bypass the retention migration provides for its own functions is not available to us;
        # versions are immutable, so the aged rows are inserted afresh by the owner with an old upload time.
        await db.execute("SELECT set_config('app.retention_bypass','on',true)")
        aged_doc = await db.fetchval("INSERT INTO public.document (seafarer_id, document_type_id) VALUES ($1,$2) RETURNING id", sid, TY["MED"])
        old = datetime.now(timezone.utc) - timedelta(days=800)
        uid = ACC["A1"].id
        ids_old = []
        for i, (path, when) in enumerate((("versions/aged-old-1.pdf", old), ("versions/aged-old-2.pdf", old + timedelta(days=1)), ("versions/aged-current.pdf", old + timedelta(days=2)))):
            ids_old.append(await db.fetchval("""INSERT INTO public.version (document_id, file_path, original_filename, content_type, document_number,
                     issuing_authority, issue_date, expiry_date, uploaded_by, uploaded_at) VALUES ($1,$2,'a.pdf','application/pdf',$3,'A',$4,$5,$6,$7) RETURNING id""",
                                             aged_doc, path, f"AGED-{i}", T - timedelta(days=900), T + timedelta(days=300), uid, when))
        # Retention counts from the review that accepted the successor: accept versions 2 and 3 long ago (A2 reviews A1's uploads).
        for vid, when in ((ids_old[1], old + timedelta(days=5)), (ids_old[2], old + timedelta(days=6))):
            await db.execute("INSERT INTO public.review (version_id, decision, comment, reviewed_by, reviewed_at) VALUES ($1,'accept','aged',$2,$3)", vid, ACC["A2"].id, when)
        # an inactive seafarer, inactive for 2 years
        s_in, _ = await new_seafarer(c, "Fr24inactive")
        await db.execute("UPDATE public.seafarer SET inactive_since = now() - interval '2 years', inactive_reason='left' WHERE id=$1", s_in)
        start = await vlib.max_audit_id(db)
        import asyncpg
        app = await asyncpg.connect(vlib.APP_DB_URL)
        rv = await app.fetchval("SELECT public.retention_remove_replaced_versions(500)")
        rs = await app.fetchval("SELECT public.retention_remove_inactive_seafarers(500)")
        await app.close()
        left = [r["id"] for r in await db.fetch("SELECT id FROM public.version WHERE document_id=$1 ORDER BY id", aged_doc)]
        recent_left = [r["id"] for r in await db.fetch("SELECT id FROM public.version WHERE document_id=$1 ORDER BY id", d["id"])]
        queued = [dict(r) for r in await db.fetch("SELECT * FROM private.retention_file_queue ORDER BY 1")] if await db.fetchval("SELECT to_regclass('private.retention_file_queue') IS NOT NULL") else "no queue table"
        s_left = await db.fetchval("SELECT count(*) FROM public.seafarer WHERE id=$1", s_in)
        recs = await vlib.audit_after(db, start)
        self.row("B-FR24", "older replaced versions removed, current kept", left == [ids_old[2]], removed=rv, left=left, expected_left=[ids_old[2]])
        self.row("B-FR24", "newer replaced versions kept", len(recent_left) == 4, left=len(recent_left))
        self.row("B-FR24", "inactive seafarer past the period removed", s_left == 0, removed=rs)
        self.row("B-FR24", "deletions logged with identifiers only", bool(recs) and all(x["action"] == "retention_removal" for x in recs),
                 records=[{k: x[k] for k in ("action", "target_type", "target_id", "seafarer_id", "before", "after", "actor_email")} for x in recs][:6])
        self.ev.write("fr24_queue.json", queued)
        # Audit records: only the owner job
        job = await db.fetchrow("SELECT jobname, schedule, username, command FROM cron.job WHERE jobname='audit-retention'")
        self.row("B-FR24", "audit records deleted only by the owner-role job", job is not None and job["username"] == "postgres", job=dict(job) if job else None)
        n_before = await db.fetchval("SELECT count(*) FROM public.audit_log")
        removed = await db.fetchval("SELECT public.retention_remove_old_audit_records()")
        self.row("B-FR24", "owner job function runs (1-year period, all records newer)", True, removed=removed, before=n_before)
        await db.execute("UPDATE public.settings SET retention_replaced_version_years=DEFAULT, retention_inactive_seafarer_years=DEFAULT, retention_audit_record_years=DEFAULT")
        await db.close()

    # ------------------------------------------------------------------ FR-25
    async def fr25(self):
        c = self.c
        hA = ACC["A1"].h
        db = await vlib.owner()

        def put(**changes):
            st = c.get("/api/settings", headers=hA).json()
            body = {k: st[k] for k in ("alert_steps", "planning_horizon_days", "max_file_size_mb", "max_pdf_pages", "time_zone",
                                       "daily_check_time", "retention_replaced_version_years", "retention_inactive_seafarer_years",
                                       "retention_audit_record_years", "version")}
            body.update(changes)
            rq = rid()
            r = c.put("/api/settings", json=body, headers={**hA, "X-Request-ID": rq})
            return r, rq

        async def nrec(rq):
            return [(x["action"], x["before"], x["after"]) for x in (await audit_by_request(db, [rq])).get(rq, [])]

        sid, aid = await new_seafarer(c, "Fr25", "V3", 40, 120)
        t = c.post("/api/document-types", json={"name": f"B25 in 75 {uuid.uuid4().hex[:4]}", "expires": True}, headers=hA).json()["id"]
        d = upload(c, hA, sid, t, number="FR25", issue=D(-300), expiry=D(75)).json()
        s0 = d["expiry_status"]
        r, rq = put(alert_steps=[60, 30, 0])
        s1 = c.get(f"/api/documents/{d['id']}", headers=hA).json()["expiry_status"]
        self.row("B-FR25", "alert thresholds 90->60: a document 75 days ahead turns unexpired", s0 == "expiring_soon" and s1 == "unexpired",
                 status=r.status_code, before=s0, after=s1, audit=await nrec(rq))
        put(alert_steps=[90, 60, 30, 0])
        dash0 = any(a["assignment_id"] == aid for a in c.get("/api/dashboard", params={"queue": "starting_soon", "limit": 200}, headers=hA).json()["assignments"])
        r, rq = put(planning_horizon_days=30)
        dash1 = any(a["assignment_id"] == aid for a in c.get("/api/dashboard", params={"queue": "starting_soon", "limit": 200}, headers=hA).json()["assignments"])
        self.row("B-FR25", "planning horizon 90->30: an assignment starting in 40 days leaves 'starting soon'", dash0 and not dash1,
                 status=r.status_code, before=dash0, after=dash1, audit=await nrec(rq))
        put(planning_horizon_days=90)
        r, rq = put(max_file_size_mb=1)
        import make_corpus
        big = make_corpus.padded_pdf(1024 * 1024 + 1000)
        u = upload(c, hA, sid, "BST" and TY["BST"], number="FR25big", issue=D(-10), expiry=D(300), content=big)
        self.row("B-FR25", "file limit 4->1 MB: an upload just over 1 MB gets 413", u.status_code == 413, status=r.status_code, upload=u.status_code, audit=await nrec(rq))
        put(max_file_size_mb=4)
        r, rq = put(retention_replaced_version_years=2)
        self.row("B-FR25", "retention period change is stored and logged (its use: B-FR24)", r.status_code == 200, status=r.status_code, audit=await nrec(rq))
        put(retention_replaced_version_years=5)
        # time zone: company date around midnight
        utc_now = vlib.now_utc()
        tz_ahead = "Pacific/Kiritimati"  # UTC+14: always a different date than UTC-12 zones
        r, rq = put(time_zone=tz_ahead)
        today_ahead = c.get("/api/dashboard", headers=hA).json()["today"]
        put(time_zone="Etc/GMT+12")
        today_behind = c.get("/api/dashboard", headers=hA).json()["today"]
        put(time_zone="UTC")
        exp_ahead = (utc_now + timedelta(hours=14)).date().isoformat()
        exp_behind = (utc_now - timedelta(hours=12)).date().isoformat()
        self.row("B-FR25", "time zone: 'today' follows the company time zone", today_ahead == exp_ahead and today_behind == exp_behind,
                 status=r.status_code, utc_now=utc_now.isoformat(), ahead=today_ahead, expected_ahead=exp_ahead, behind=today_behind, expected_behind=exp_behind, audit=await nrec(rq))
        # daily check time: due or not at the next use
        sys.path.insert(0, str(vlib.ROOT / "backend"))
        from app import domain
        r, rq = put(daily_check_time="23:45")
        st = await db.fetchrow("SELECT daily_check_time, time_zone FROM public.settings")
        from zoneinfo import ZoneInfo
        due_before = domain.daily_check_due(datetime(T.year, T.month, T.day, 23, 44, tzinfo=ZoneInfo("UTC")), st["daily_check_time"], False)
        due_at = domain.daily_check_due(datetime(T.year, T.month, T.day, 23, 45, tzinfo=ZoneInfo("UTC")), st["daily_check_time"], False)
        self.row("B-FR25", "daily check time 23:45 stored and used by the due rule (23:44 not due, 23:45 due)", r.status_code == 200 and not due_before and due_at,
                 status=r.status_code, stored=str(st["daily_check_time"]), audit=await nrec(rq), note="live timing on staging: D6")
        r, rq = put(daily_check_time="23:50")
        self.row("B-FR25", "a check time not on a quarter hour", None, status=r.status_code, body=r.text[:150])
        put(daily_check_time="07:00")
        for who in ("O1", "M"):
            st = c.get("/api/settings", headers=hA).json()
            body = {k: st[k] for k in ("alert_steps", "planning_horizon_days", "max_file_size_mb", "max_pdf_pages", "time_zone", "daily_check_time",
                                       "retention_replaced_version_years", "retention_inactive_seafarer_years", "retention_audit_record_years", "version")}
            r = c.put("/api/settings", json=body, headers=ACC[who].h)
            self.row("B-FR25", f"{who} changes settings -> 403", r.status_code == 403, status=r.status_code)
        await db.close()


async def own_dashboard_counts(db) -> dict:
    """The queue counts from the tables, with the rules of FR-14/15/17 and the user guide."""
    st = await db.fetchrow("SELECT alert_steps, planning_horizon_days, time_zone FROM public.settings")
    today = (vlib.now_utc()).date() if st["time_zone"] == "UTC" else None
    largest = max(st["alert_steps"])
    seaf = [dict(r) for r in await db.fetch("SELECT id, position_id FROM public.seafarer WHERE inactive_since IS NULL")]
    types = {r["id"]: dict(r) for r in await db.fetch("SELECT * FROM public.document_type")}
    asg = [dict(r) for r in await db.fetch("SELECT a.*, v.flag FROM public.assignment a JOIN public.vessel v ON v.id=a.vessel_id WHERE cancelled_at IS NULL")]
    req = defaultdict(set)
    for r in await db.fetch("SELECT * FROM public.position_requirement"):
        req[r["position_id"]].add(r["document_type_id"])
    exc = [dict(r) for r in await db.fetch("SELECT * FROM public.requirement_exception")]
    docs = [dict(r) for r in await db.fetch("SELECT * FROM public.document")]
    vers = defaultdict(list)
    for r in await db.fetch("SELECT * FROM public.version ORDER BY uploaded_at, id"):
        vers[r["document_id"]].append(dict(r))
    latest_rev = {}
    for r in await db.fetch("SELECT DISTINCT ON (version_id) version_id, decision FROM public.review ORDER BY version_id, id DESC"):
        latest_rev[r["version_id"]] = r["decision"]
    officer_vessels = defaultdict(set)
    for r in await db.fetch("SELECT ro.user_id, ro.vessel_id FROM public.responsible_officer ro JOIN public.users u ON u.id=ro.user_id WHERE u.status='active'"):
        officer_vessels[r["user_id"]].add(r["vessel_id"])

    def current_or_next(sid):
        live = [a for a in asg if a["seafarer_id"] == sid and a["end_date"] >= today]
        cur_ = [a for a in live if a["start_date"] <= today]
        if cur_:
            return cur_[0], "current"
        nxt = sorted([a for a in live if a["start_date"] > today], key=lambda a: a["start_date"])
        return (nxt[0], "next") if nxt else (None, None)

    def required(s):
        a, kind = current_or_next(s["id"])
        pos = s["position_id"]
        r = set(req[pos])
        if a is not None and kind == "current":
            for e in exc:
                if e["position_id"] not in (None, pos):
                    continue
                if (e["vessel_id"] and e["vessel_id"] == a["vessel_id"]) or (e["flag"] and e["flag"] == a["flag"]):
                    (r.add if e["effect"] == "add" else r.discard)(e["document_type_id"])
        return r

    def current_version(doc_id):
        vs = [v for v in vers[doc_id] if latest_rev.get(v["id"]) != "reject"]
        return vs[-1] if vs else None

    def scope(user_key):
        if user_key == "A1":
            return {s["id"] for s in seaf}
        vs = officer_vessels[ACC[user_key].id]
        out = set()
        for s in seaf:
            live = [a for a in asg if a["seafarer_id"] == s["id"] and a["end_date"] >= today]
            if not live or any(a["vessel_id"] in vs for a in live):
                out.add(s["id"])
        return out

    docs_by = defaultdict(dict)
    for d in docs:
        docs_by[d["seafarer_id"]][d["document_type_id"]] = d
    result = {}
    for who in ("A1", "O1"):
        sc = scope(who)
        cnt = Counter()
        for s in seaf:
            if s["id"] not in sc:
                continue
            for t in required(s):
                d = docs_by[s["id"]].get(t)
                if d is None or current_version(d["id"]) is None:
                    cnt["missing"] += 1
            for t, d in docs_by[s["id"]].items():
                cv = current_version(d["id"])
                if cv is None:
                    continue
                ty = types[t]
                eff = cv["expiry_date"]
                not_stated = False
                if ty["depends_on_id"]:
                    cd = docs_by[s["id"]].get(ty["depends_on_id"])
                    ccv = current_version(cd["id"]) if cd else None
                    if ccv is None:
                        eff = "expired"
                    elif ccv["expiry_date"] is None:
                        not_stated = True
                    elif eff is not None:
                        eff = min(eff, ccv["expiry_date"])
                if eff == "expired":
                    status = "expired"
                elif eff is None:
                    status = "no_expiry_date" if not ty["expires"] else "expiry_not_stated"
                else:
                    left = (eff - today).days
                    status = "expired" if left < 0 else ("expiring_soon" if left <= largest else "unexpired")
                    if not_stated and status == "unexpired":
                        status = "expiry_not_stated"
                if status == "expired":
                    cnt["expired"] += 1
                elif status == "expiring_soon":
                    cnt["expiring_soon"] += 1
                elif status == "expiry_not_stated":
                    cnt["expiry_not_stated"] += 1
                else:
                    cnt["in_order"] += 1
                if latest_rev.get(cv["id"]) is None:
                    cnt["waiting_for_review"] += 1
        horizon = today + timedelta(days=st["planning_horizon_days"])
        cnt["starting_soon"] = sum(1 for a in asg if a["seafarer_id"] in sc and today < a["start_date"] <= horizon
                                   and a["seafarer_id"] in {s["id"] for s in seaf})
        result[who] = {k: cnt.get(k, 0) for k in ("missing", "expired", "expiring_soon", "expiry_not_stated", "waiting_for_review", "starting_soon", "in_order")}
    return result


ORDER = ["fr01", "fr02", "fr03", "fr04", "fr05", "fr06", "fr07", "fr08", "fr09", "fr10_13", "fr15", "fr17", "fr18_19",
         "fr20", "fr21", "fr23", "fr22", "fr16", "fr25", "fr24"]


async def main(names: list[str]) -> None:
    ch = Checks()
    for n in names or ORDER:
        try:
            await getattr(ch, n)()
        except Exception as e:
            import traceback
            ch.row(n, "check crashed", False, error=f"{type(e).__name__}: {e}", tb=traceback.format_exc()[-800:])
    ch.ev.save()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:]))
