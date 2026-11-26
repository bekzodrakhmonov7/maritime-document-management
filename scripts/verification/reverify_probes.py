"""Re-verification probes for 08b93fa: F-02 (NUL byte -> 422) and F-15
(file-url for a version whose stored object is gone -> 404). Needs D1.

    uv run python scripts/verification/reverify_probes.py
"""

from __future__ import annotations

import asyncio
import uuid

import d1 as d1mod
import vlib


async def main() -> None:
    ev = vlib.Evidence("F02_F15")
    ids = d1mod.load()
    acc = d1mod.accounts(ids)
    a1 = acc["A1"]
    db = await vlib.owner()
    start = await vlib.max_audit_id(db)
    pos = await db.fetchval("SELECT id FROM public.position ORDER BY id LIMIT 1")
    with vlib.client() as c:
        probes = [
            ("GET", "/api/seafarers?search=a%00b", None),
            ("GET", "/api/audit?actor_email=a%00b", None),
            ("POST", "/api/vessels", {"name": "Nul\u0000Vessel", "imo_number": "9199999", "flag": "MT"}),
            ("POST", "/api/seafarers", {"first_name": "Nul\u0000", "last_name": "Probe", "position_id": str(pos)}),
            ("GET", "/api/dashboard?name=a%00b", None),
        ]
        for m, p, body in probes:
            r = c.request(m, p, json=body, headers=a1.h)
            ev.exchange(f"NUL {m} {p}", r)
            ev.row(case=f"F-02 NUL byte {m} {p.split('?')[0]}", status=r.status_code,
                   ok=r.status_code == 422 if "dashboard" not in p else r.status_code in (200, 422))
        # F-15: a version whose stored object is gone (version rows are immutable,
        # so the object of a fresh upload is removed through the Storage API, service key)
        vid, path = await db.fetchrow("""SELECT v.id, v.file_path FROM public.version v JOIN storage.objects o
            ON o.bucket_id='crew-documents' AND o.name=v.file_path ORDER BY v.id DESC LIMIT 1""")
        r = c.post(f"/api/versions/{vid}/file-url", headers=a1.h)
        ev.row(case="F-15 control: version with its object present", status=r.status_code, ok=r.status_code == 200)
        sk = vlib.ENV["SUPABASE_SERVICE_ROLE_KEY"]
        d = c.request("DELETE", f"{vlib.SUPABASE_URL}/storage/v1/object/crew-documents",
                      json={"prefixes": [path]}, headers={"Authorization": f"Bearer {sk}", "apikey": sk})
        ev.row(case="F-15 setup: object removed through Storage", status=d.status_code, removed=d.text[:120],
               ok=d.status_code == 200)
        r = c.post(f"/api/versions/{vid}/file-url", headers=a1.h)
        ev.exchange("file-url, object missing", r)
        ev.row(case="F-15 file-url for a version whose object is missing", status=r.status_code,
               body=r.text[:200], ok=r.status_code == 404)
    ev.write("audit.json", await vlib.audit_after(db, start))
    ev.save()
    await db.close()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r["case"], r["status"])


if __name__ == "__main__":
    asyncio.run(main())
