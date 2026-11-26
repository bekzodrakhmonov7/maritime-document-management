"""U1: pages that together show every status of every dimension (from the tables).
Also adds a 'not confirmed' verification so that label exists. Writes <evidence>/U/u1_pages.json."""
import asyncio, json, uuid
import vlib
async def main():
    seed = json.load(open(vlib.EVIDENCE / "U" / "seed.json"))
    acc = json.load(open(vlib.EVIDENCE / "U" / "browser-accounts.json"))
    db = await vlib.owner()
    q = lambda sql: db.fetchval(sql)
    rej = await q("SELECT v.document_id FROM public.review r JOIN public.version v ON v.id=r.version_id WHERE r.decision='reject' LIMIT 1")
    ver = await q("SELECT v.document_id FROM public.verification c JOIN public.version v ON v.id=c.version_id WHERE c.result='confirmed' LIMIT 1")
    exp = await q("SELECT document_id FROM public.version WHERE expiry_date < current_date ORDER BY id DESC LIMIT 1")
    ns = await q("SELECT v.document_id FROM public.version v JOIN public.document d ON d.id=v.document_id JOIN public.document_type t ON t.id=d.document_type_id WHERE v.expiry_date IS NULL AND t.expires LIMIT 1")
    noexp = await q("SELECT v.document_id FROM public.version v JOIN public.document d ON d.id=v.document_id JOIN public.document_type t ON t.id=d.document_type_id WHERE NOT t.expires LIMIT 1")
    endo = await q("SELECT d.id FROM public.document d JOIN public.document_type t ON t.id=d.document_type_id WHERE t.depends_on_id IS NOT NULL LIMIT 1")
    # a 'not confirmed' verification on some current version, recorded by account b
    nc_doc = await q("SELECT v.document_id FROM public.version v WHERE NOT EXISTS (SELECT 1 FROM public.verification c WHERE c.version_id=v.id) ORDER BY v.id DESC LIMIT 1")
    nc_ver = await q(f"SELECT id FROM public.version WHERE document_id={nc_doc} ORDER BY uploaded_at DESC, id DESC LIMIT 1")
    await db.close()
    with vlib.client() as c:
        h = vlib.bearer(vlib.make_token(uuid.UUID(seed["admin_id"])))
        r = c.post(f"/api/versions/{nc_ver}/verifications", data={"checked_on": vlib.now_utc().date().isoformat(), "source": "U1 registry", "result": "not_confirmed", "reference": "U1-NC"}, headers=h)
    targets = json.load(open(vlib.EVIDENCE / "U" / "targets.json"))
    pages = {"dashboard": "/", "alerts": "/alerts", "seafarer-long-name": "/seafarers/447",
             "readiness-showcase": f"/assignments/{seed['readiness_assignment_id']}/readiness",
             "doc-rejected-version": f"/documents/{rej}", "doc-verified": f"/documents/{ver}", "doc-expired": f"/documents/{exp}",
             "doc-expiry-not-stated": f"/documents/{ns}", "doc-no-expiry": f"/documents/{noexp}", "doc-endorsement": f"/documents/{endo}",
             "doc-not-confirmed": f"/documents/{nc_doc}"}
    for k, t in targets.items():
        pages[f"seafarer-{k}"] = f"/seafarers/{t['seafarerId']}"
    (vlib.EVIDENCE / "U" / "u1_pages.json").write_text(json.dumps(pages, indent=1))
    print(r.status_code, json.dumps(pages, indent=1))
asyncio.run(main())
