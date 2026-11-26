"""Browser test accounts for U1/U2: real Supabase Auth users, approved, TOTP
enrolled once through the API. Writes <evidence>/U/browser-accounts.json
(git-ignored: e-mail, password, TOTP secret) for scripts/nfr/browser/lib.mjs.

    uv run python scripts/verification/browser_accounts.py      # API must run on :8000
Accounts: a, b = administrators (b reviews what a uploads), c = crewing officer.
"""

import asyncio
import json
import uuid

import vlib
from security_checks import admin_create_auth_user, api_sign_in


async def main() -> None:
    db = await vlib.owner()
    out = {}
    for letter, role in (("a", "administrator"), ("b", "administrator"), ("c", "crewing_officer")):
        email = f"browser-{letter}-{uuid.uuid4().hex[:6]}@example.com"
        password = "Browser-" + uuid.uuid4().hex[:14]
        uid = admin_create_auth_user(email, password, full_name=f"Browser {letter.upper()}")
        await db.execute("UPDATE public.users SET status='active', role=$2 WHERE id=$1", uid, role)
        with vlib.client() as c:
            res, secret = api_sign_in(c, email, password, None)
        assert res["status"] == 200, res
        out[letter] = {"email": email, "password": password, "secret": secret, "role": role, "id": str(uid)}
    await db.close()
    p = vlib.EVIDENCE / "U" / "browser-accounts.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print({k: (v["email"], v["role"]) for k, v in out.items()})


asyncio.run(main())
