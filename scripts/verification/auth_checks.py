"""C2 password rules, C3 MFA and C13 lock-out: the checks that need real
Supabase Auth accounts (password + TOTP). Run through security_checks.py:

    uv run python scripts/verification/security_checks.py c2 c3 c13

Each scenario sends its own X-Forwarded-For address. The local uvicorn trusts
that header from 127.0.0.1 (its default), so one scenario's failed logins are
counted for its own address and do not block the next scenario.
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from collections import Counter

import httpx

import vlib
from security_checks import api_sign_in, direct_password_grant, fill, real_account, routes


def xff(n: int) -> dict[str, str]:
    return {"X-Forwarded-For": f"198.51.100.{n}"}


def claims(tok: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))


def pwned_count(password: str) -> int:
    h = hashlib.sha1(password.encode()).hexdigest().upper()
    r = httpx.get(f"https://api.pwnedpasswords.com/range/{h[:5]}",
                  headers={"Add-Padding": "true", "User-Agent": "ch4-verification"}, timeout=10)
    for line in r.text.splitlines():
        s, _, n = line.partition(":")
        if s == h[5:]:
            return int(n)
    return 0


def common_list() -> set[str]:
    p = vlib.ROOT / "backend" / "app" / "data" / "common_passwords.txt"
    return {l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")}


def choose_pwned_not_listed() -> tuple[str, int]:
    common = common_list()
    for cand in ("ilovemydogsomuch", "manchesterunited1", "correcthorsebatterystaple", "welcometothejungle",
                 "thequickbrownfox", "mypasswordisstrong", "liverpoolfc2010"):
        if len(cand) >= 12 and cand not in common:
            n = pwned_count(cand)
            if n > 0:
                return cand, n
    raise RuntimeError("no candidate")


def detail_code(r: httpx.Response):
    try:
        d = r.json().get("detail")
        return d.get("code") if isinstance(d, dict) else None
    except Exception:
        return None


async def c2() -> None:
    ev = vlib.Evidence("C2")
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    common = sorted(x for x in common_list() if len(x) >= 12)
    common_pw = common[100]
    pwned_pw, n = choose_pwned_not_listed()
    ev.meta.update({"common_choice": "100th (sorted) entry of the bundled list", "pwned_choice_count": n,
                    "pwned_choice_len": len(pwned_pw)})
    cases = [("11 characters", "Qz7#mVx2!pL", 422), ("12 characters, uncommon", "Qz7#mVx2!pLr", 200),
             ("on the bundled common list", common_pw, 422),
             (f"known to Pwned Passwords ({n} times), not on the list", pwned_pw, 422)]
    with vlib.client() as c:
        for name, pw, exp in cases:
            email = f"c2reg-{uuid.uuid4().hex[:6]}@example.com"
            r = c.post("/api/auth/register", json={"email": email, "full_name": "Pw Check", "password": pw})
            ev.exchange(f"register: {name}", r)
            ev.row(flow="registration", case=name, length=len(pw), status=r.status_code, code=detail_code(r),
                   ok=r.status_code == exp)
        acct = await real_account(db, prefix="c2reset")
        for name, pw, exp in [cases[0], cases[2], cases[3], cases[1]]:
            t0 = time.time()
            f = c.post("/api/auth/password/forgot", json={"email": acct["email"]})
            try:
                code = vlib.mailpit_code(acct["email"], t0, timeout=40)
            except TimeoutError:
                code = "000000"
            r = c.post("/api/auth/password/reset", json={"email": acct["email"], "code": code, "password": pw})
            ev.exchange(f"reset: {name}", r)
            ev.row(flow="password reset", case=name, length=len(pw), forgot_status=f.status_code, status=r.status_code,
                   code=detail_code(r), ok=r.status_code == exp)
            if r.status_code == 200:
                break
            time.sleep(61)  # one recovery e-mail per minute
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["flow"], r["case"], r["status"], r.get("code"))


async def c3() -> None:
    ev = vlib.Evidence("C3")
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    with vlib.client() as c:
        rts = routes(c)
        officer, officer_session = None, None
        for i, role in enumerate(("administrator", "crewing_officer", "manager")):
            a = await real_account(db, role=role, prefix=f"c3{role[:3]}")
            res, secret = api_sign_in(c, a["email"], a["password"], None, ev, f"first login {role}")
            tok = (res.get("body") or {}).get("access_token")
            ev.row(case=f"first login of an approved {role}: enrol step, then aal2", step=res.get("step"),
                   status=res["status"], aal=claims(tok).get("aal") if tok else None,
                   ok=res.get("step") == "enrol" and res["status"] == 200 and claims(tok).get("aal") == "aal2")
            a["secret"] = secret
            if role == "crewing_officer":
                officer, officer_session = a, res["body"]
        g = direct_password_grant(officer["email"], officer["password"])
        aal1 = g.json()["access_token"]
        sts = Counter()
        for m, p in rts:
            r = c.request(m, fill(p, {}), headers=vlib.bearer(aal1), json={} if m in ("POST", "PUT") else None)
            sts[r.status_code] += 1
        ev.row(case="password-only token (aal1, straight from Supabase Auth) on every protected route",
               aal=claims(aal1).get("aal"), routes=len(rts), statuses=dict(sts), ok=set(sts) <= {401, 403})
        good = officer_session["access_token"]
        got = {}
        for p in ("/api/me", "/api/dashboard", "/api/seafarers", "/api/vessels", "/api/alerts", "/api/document-types"):
            got[p] = c.get(p, headers=vlib.bearer(good)).status_code
        ev.row(case="second-factor (aal2) token from the API sign-in", statuses=got, ok=all(v == 200 for v in got.values()))
        # Five wrong codes end the challenge
        r = c.post("/api/auth/login", json={"email": officer["email"], "password": officer["password"]}, headers=xff(31))
        ch = r.json()["challenge"]
        wrong = []
        for _ in range(5):
            bad = "000000" if vlib.totp_now(officer["secret"]) != "000000" else "111111"
            v = c.post("/api/auth/verify", json={"email": officer["email"], "challenge": ch, "code": bad}, headers=xff(31))
            wrong.append(v.status_code)
        vlib.wait_fresh_totp_window()
        v = c.post("/api/auth/verify", json={"email": officer["email"], "challenge": ch,
                                             "code": vlib.totp_now(officer["secret"])}, headers=xff(31))
        ev.exchange("right code after five wrong ones", v)
        ev.row(case="five wrong codes, then the right one on the same challenge", wrong=wrong, sixth=v.status_code,
               body=v.text[:150], ok=v.status_code != 200)
        # Password reset by e-mail needs the authenticator (08b93fa: reset takes `totp`; reverify script fix)
        newpw = "Verif-New-" + uuid.uuid4().hex[:10]
        t0 = time.time()
        c.post("/api/auth/password/forgot", json={"email": officer["email"]})
        code = vlib.mailpit_code(officer["email"], t0, timeout=40)
        r0 = c.post("/api/auth/password/reset", json={"email": officer["email"], "code": code, "password": newpw})
        ev.exchange("password reset without the authenticator code", r0)
        ev.row(case="password reset by e-mail without the authenticator code is refused", status=r0.status_code,
               code=detail_code(r0), ok=r0.status_code == 400 and detail_code(r0) == "totp_required")
        time.sleep(61)  # one recovery e-mail per minute
        t0 = time.time()
        c.post("/api/auth/password/forgot", json={"email": officer["email"]})
        code = vlib.mailpit_code(officer["email"], t0, timeout=40)
        bad = "000000" if vlib.totp_now(officer["secret"]) != "000000" else "111111"
        rw = c.post("/api/auth/password/reset", json={"email": officer["email"], "code": code, "password": newpw, "totp": bad})
        ev.exchange("password reset with a wrong authenticator code", rw)
        ev.row(case="password reset by e-mail with a wrong authenticator code is refused", status=rw.status_code,
               code=detail_code(rw), ok=rw.status_code == 403 and detail_code(rw) == "totp_invalid")
        time.sleep(61)
        t0 = time.time()
        c.post("/api/auth/password/forgot", json={"email": officer["email"]})
        code = vlib.mailpit_code(officer["email"], t0, timeout=40)
        vlib.wait_fresh_totp_window()
        r = c.post("/api/auth/password/reset", json={"email": officer["email"], "code": code, "password": newpw,
                                                     "totp": vlib.totp_now(officer["secret"])})
        ev.exchange("password reset", r)
        r2 = c.post("/api/auth/login", json={"email": officer["email"], "password": newpw}, headers=xff(32))
        ev.exchange("login with the new password", r2)
        body = r2.json() if r2.content else {}
        ev.row(case="after a password reset by e-mail, sign-in asks for the authenticator code",
               reset=r.status_code, login=r2.status_code, step=body.get("step"), has_session="access_token" in body,
               ok=r.status_code == 200 and body.get("step") == "totp" and "access_token" not in body)
        v2 = None
        if body.get("challenge"):
            vlib.wait_fresh_totp_window()
            v2 = c.post("/api/auth/verify", json={"email": officer["email"], "challenge": body["challenge"],
                                                  "code": vlib.totp_now(officer["secret"])}, headers=xff(32))
            ev.exchange("verify after reset", v2)
        tok2 = (v2.json() if v2 is not None and v2.content else {}).get("access_token")
        me2 = c.get("/api/me", headers=vlib.bearer(tok2)).status_code if tok2 else None
        ev.row(case="new password + authenticator code gives an aal2 session", verify=v2.status_code if v2 is not None else None,
               aal=claims(tok2).get("aal") if tok2 else None, me=me2, ok=me2 == 200 and claims(tok2).get("aal") == "aal2")
        old = c.get("/api/me", headers=vlib.bearer(good))
        ev.row(case="the aal2 session from before the reset", status=old.status_code, ok=old.status_code == 401)
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})


async def c13() -> None:
    ev = vlib.Evidence("C13")
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    await db.execute("DELETE FROM public.login_block")

    async def block_rows():
        return {(r["kind"], r["key"]): r["blocked_until"] for r in
                await db.fetch("SELECT kind, key, blocked_until FROM public.login_block")}

    with vlib.client() as c:
        a = await real_account(db, prefix="c13")
        res, secret = api_sign_in(c, a["email"], a["password"], None, None, "")
        assert res["status"] == 200, res
        H = xff(40)
        sts = []
        for i in range(12):
            r = c.post("/api/auth/login", json={"email": a["email"], "password": f"Wrong-Password-{i}"}, headers=H)
            sts.append((i + 1, r.status_code, r.headers.get("retry-after")))
            if i in (8, 9, 10):
                ev.exchange(f"wrong password #{i + 1}", r)
        ev.row(case="wrong passwords 1..12 for one account from one address", attempts=sts,
               ok=all(s[1] != 429 for s in sts[:9]) and sts[10][1] == 429 and sts[10][2] == "900",
               note="criterion: after 10 failed logins further attempts get 429; the 10th itself is the 10th failure")
        b1 = await block_rows()
        r = c.post("/api/auth/login", json={"email": a["email"], "password": a["password"]}, headers=xff(41))
        ev.exchange("right password during the block, from another address", r)
        ev.row(case="right password during the e-mail block", status=r.status_code,
               retry_after=r.headers.get("retry-after"), ok=r.status_code == 429)
        time.sleep(3)
        for _ in range(3):
            c.post("/api/auth/login", json={"email": a["email"], "password": "Wrong-again-x"}, headers=H)
        b2 = await block_rows()
        ev.row(case="blocked attempts do not extend the block",
               before={f"{k}": str(v) for k, v in b1.items()}, after={f"{k}": str(v) for k, v in b2.items()},
               ok=all(b2.get(k) == v for k, v in b1.items()))
        recs = await vlib.audit_after(db, start)
        blocked = [x for x in recs if "blocked" in (x["reason"] or "") or "blocked" in x["action"]]
        ev.row(case="blocked attempts recorded", records=len(blocked),
               kinds=sorted({(x["action"], x["reason"], x["outcome"]) for x in blocked}), ok=len(blocked) > 0)
        await db.execute("UPDATE public.login_block SET blocked_until = now() - interval '1 second'")
        res2, _ = api_sign_in(c, a["email"], a["password"], secret, None, "")
        ev.row(case="after the 15 minutes (block row moved to the past), sign-in works", status=res2["status"],
               ok=res2["status"] == 200)
        # One address, several e-mails
        H2 = xff(50)
        sts = []
        for i in range(11):
            r = c.post("/api/auth/login", json={"email": f"c13-unknown-{i}-{uuid.uuid4().hex[:4]}@example.com",
                                                "password": "Wrong-Password"}, headers=H2)
            sts.append(r.status_code)
        r = c.post("/api/auth/login", json={"email": a["email"], "password": a["password"]}, headers=H2)
        ev.row(case="one address, 11 different e-mails, then a valid login from that address", statuses=sts,
               valid_login=r.status_code, ok=all(s != 429 for s in sts[:10]) and sts[10] == 429 and r.status_code == 429)
        # Wrong TOTP codes count
        await db.execute("DELETE FROM public.login_block")
        b = await real_account(db, prefix="c13totp")
        api_sign_in(c, b["email"], b["password"], None, None, "")
        H3 = xff(60)
        sts = []
        for _ in range(11):
            r = c.post("/api/auth/login", json={"email": b["email"], "password": b["password"]}, headers=H3)
            if r.status_code != 200:
                sts.append(("login", r.status_code))
                continue
            v = c.post("/api/auth/verify", json={"email": b["email"], "challenge": r.json()["challenge"], "code": "000000"}, headers=H3)
            sts.append(("verify", v.status_code))
        ev.row(case="wrong authenticator codes count towards the block", attempts=sts,
               ok=("login", 429) in sts or ("verify", 429) in sts)
        # Unknown e-mail: same answer
        await db.execute("DELETE FROM public.login_block")
        k = c.post("/api/auth/login", json={"email": a["email"], "password": "Wrong-Password-x"}, headers=xff(70))
        u = c.post("/api/auth/login", json={"email": f"nobody-{uuid.uuid4().hex[:6]}@example.com",
                                            "password": "Wrong-Password-x"}, headers=xff(71))
        ev.exchange("known e-mail, wrong password", k)
        ev.exchange("unknown e-mail", u)
        ev.row(case="unknown e-mail answered like a known one", known=[k.status_code, k.text], unknown=[u.status_code, u.text],
               ok=k.status_code == u.status_code and k.json() == u.json())
        recs = await vlib.audit_after(db, start)
        ev.row(case="addresses in the login-failed records",
               ips=dict(Counter(str(x["ip"]) for x in recs if x["action"] == "login_failed")), ok=None)
    await db.execute("DELETE FROM public.login_block")
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print({True: "OK  ", False: "FAIL", None: "INFO"}[r.get("ok")], r["case"], {k: v for k, v in r.items() if k not in ("case", "ok")})


CHECKS = {"c2": c2, "c3": c3, "c13": c13}
