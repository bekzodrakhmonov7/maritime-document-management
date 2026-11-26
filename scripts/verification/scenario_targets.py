"""U1/U2: pick one Missing document per browser (+1 for account B) among
seafarers with an upcoming assignment inside the planning horizon. Candidates
from the tables, the missing type from the API's seafarer record.
Writes <evidence>/U/targets.json for scripts/nfr/browser/scenarios.mjs."""
import asyncio, json, uuid
import vlib

async def main():
    seed = json.load(open(vlib.EVIDENCE / "U" / "seed.json"))
    h = vlib.bearer(vlib.make_token(uuid.UUID(seed["admin_id"])))
    db = await vlib.owner()
    rows = await db.fetch("""SELECT s.id, s.first_name || ' ' || s.last_name AS name FROM public.seafarer s
        JOIN public.assignment a ON a.seafarer_id = s.id AND a.cancelled_at IS NULL
        WHERE s.inactive_since IS NULL AND a.start_date BETWEEN current_date + 5 AND current_date + 80
          AND length(s.first_name || ' ' || s.last_name) < 30
          AND (SELECT count(*) FROM public.seafarer x WHERE x.first_name = s.first_name AND x.last_name = s.last_name) = 1
        ORDER BY s.id""")
    await db.close()
    out = {}
    with vlib.client() as c:
        for r in rows:
            if len(out) == 5:
                break
            rec = c.get(f"/api/seafarers/{r['id']}", headers=h).json()
            m = rec.get("missing_documents") or []
            if len(m) >= 1 and m[0]["document_id"] is None:
                key = ("chromium", "firefox", "chrome", "msedge", "B")[len(out)]
                out[key] = {"seafarer": r["name"], "filter": r["name"], "type": m[0]["name"], "typeId": m[0]["document_type_id"], "seafarerId": r["id"]}
    (vlib.EVIDENCE / "U" / "targets.json").write_text(json.dumps(out, indent=1))
    for k, v in out.items():
        print(k, v["seafarer"], "|", v["type"], v["typeId"])

asyncio.run(main())
