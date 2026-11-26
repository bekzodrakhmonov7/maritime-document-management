"""Data set D1 (plan section 5): built through the API as administrator A1,
accounts through the owner connection as in backend/tests/conftest.py.

Wipes the business tables of the LOCAL stack first. Writes the identifiers
and the definition to <evidence>/D1/d1.json and returns them. The expected
results of the checks are derived from DEFINITION below, never from the API.

    uv run python scripts/verification/d1.py
"""

from __future__ import annotations

import asyncio
import json
from datetime import date, timedelta

import vlib

TODAY = date.today()  # Settings time zone is UTC after a reset; the client runs in UTC+2 but dates are taken in UTC below.


def utc_today() -> date:
    return vlib.now_utc().date()


T = utc_today()

# --- the definition: everything the expected results are derived from -------------------
DEFINITION = {
    "vessels": {
        "V1": {"name": "D1 Vessel One", "imo_number": "9100001", "flag": "MT"},
        "V2": {"name": "D1 Vessel Two", "imo_number": "9100002", "flag": "LR"},
        "V3": {"name": "D1 Vessel Three", "imo_number": "9100003", "flag": "GR"},
    },
    "accounts": {
        "A1": {"role": "administrator", "status": "active"},
        "A2": {"role": "administrator", "status": "active"},
        "O1": {"role": "crewing_officer", "status": "active", "vessels": ["V1"]},
        "O2": {"role": "crewing_officer", "status": "active", "vessels": ["V2"]},
        "M": {"role": "manager", "status": "active"},
        "P": {"role": None, "status": "pending"},
        "X": {"role": "crewing_officer", "status": "deactivated", "vessels": ["V1"]},
    },
    "position": "D1 Master",
    "types": {
        # name, expires, max_validity_months, renewable_at_sea, depends_on
        "COC": ("D1 Certificate of Competency", True, 60, False, None),
        "END": ("D1 Endorsement of CoC", True, 60, False, "COC"),
        "MED": ("D1 Medical certificate", True, 24, True, None),
        "BST": ("D1 Basic safety training", True, 60, False, None),
        "FAM": ("D1 Vessel familiarisation", True, 12, False, None),   # added on V1 only
        "LRE": ("D1 Liberian flag endorsement", True, 60, False, None),  # added under LR only
        "BOOK": ("D1 Seaman's book", False, None, False, None),        # never expires, not required
    },
    "required": ["COC", "END", "MED", "BST"],
    "exceptions": [
        {"vessel": "V1", "type": "FAM", "effect": "add", "reason": "D1 vessel exception"},
        {"flag": "LR", "type": "LRE", "effect": "add", "reason": "D1 flag exception"},
    ],
    # (name, assignment) with dates relative to T (UTC today)
    "seafarers": {
        "S1": {"first": "Sone", "assign": ("V1", -30, 60, False)},      # under way on V1
        "S2": {"first": "Stwo", "assign": ("V2", 20, 120, False)},      # upcoming on V2
        "S3": {"first": "Sthree", "assign": None},                     # no assignment
        "S4": {"first": "Sfour", "assign": ("V2", -200, -100, False)},  # finished on V2
        "S5": {"first": "Sfive", "assign": ("V1", 10, 100, True)},      # cancelled on V1
    },
}


def expected_scope(officer: str) -> set[str]:
    """FR-03 from the definition: seafarers on, or planned for, the officer's
    vessels (not cancelled, end date not passed), plus those without a current
    or planned assignment."""
    vessels = set(DEFINITION["accounts"][officer].get("vessels", []))
    out = set()
    for s, d in DEFINITION["seafarers"].items():
        a = d["assign"]
        live = a is not None and not a[3] and a[2] >= 0  # current or planned
        if not live:
            out.add(s)
        elif a[0] in vessels:
            out.add(s)
    return out


TABLES = ("alert_delivery, alert, review, verification, version, document, responsible_officer, "
          "assignment, seafarer, requirement_exception, position_requirement, document_type, position, vessel")


async def build() -> dict:
    db = await vlib.owner()
    try:
        await db.execute(f"TRUNCATE {', '.join('public.' + t.strip() for t in TABLES.split(','))} CASCADE")
        await db.execute("DELETE FROM public.users WHERE email LIKE 'd1-%@example.com'")
        await db.execute("DELETE FROM auth.users WHERE email LIKE 'd1-%@example.com'")
        await db.execute("""UPDATE public.settings SET alert_steps = DEFAULT, planning_horizon_days = DEFAULT,
               max_file_size_mb = 4, max_pdf_pages = DEFAULT, time_zone = DEFAULT, daily_check_time = DEFAULT,
               retention_replaced_version_years = DEFAULT, retention_inactive_seafarer_years = DEFAULT,
               retention_audit_record_years = DEFAULT, updated_by = NULL""")
        acc = {}
        for key, spec in DEFINITION["accounts"].items():
            a = await vlib.make_account(db, status=spec["status"], role=spec["role"],
                                        email=f"d1-{key.lower()}@example.com", full_name=f"D1 {key}")
            acc[key] = a
    finally:
        await db.close()

    ids: dict = {"accounts": {k: {"id": str(a.id), "email": a.email} for k, a in acc.items()},
                 "today_utc": T.isoformat()}
    h = acc["A1"].h
    with vlib.client() as c:
        def post(path, body, expect=201):
            r = c.post(path, json=body, headers=h)
            assert r.status_code in (expect, 200), (path, r.status_code, r.text)
            return r.json()

        ids["vessels"] = {k: post("/api/vessels", v)["id"] for k, v in DEFINITION["vessels"].items()}
        for key, spec in DEFINITION["accounts"].items():
            for v in spec.get("vessels", []):
                if spec["status"] == "deactivated":
                    continue
                post(f"/api/vessels/{ids['vessels'][v]}/responsible-officers", {"account_id": str(acc[key].id)})
        ids["position"] = post("/api/positions", {"name": DEFINITION["position"]})["id"]
        ids["types"] = {}
        for k, (name, exp, mx, sea, dep) in DEFINITION["types"].items():
            body = {"name": name, "expires": exp, "max_validity_months": mx, "renewable_at_sea": sea,
                    "depends_on_id": ids["types"][dep] if dep else None}
            ids["types"][k] = post("/api/document-types", body)["id"]
        for k in DEFINITION["required"]:
            r = c.put(f"/api/requirements/{ids['position']}/{ids['types'][k]}", headers=h)
            assert r.status_code in (200, 201, 204), r.text
        ids["exceptions"] = []
        for e in DEFINITION["exceptions"]:
            body = {"vessel_id": ids["vessels"][e["vessel"]] if "vessel" in e else None,
                    "flag": e.get("flag"), "position_id": ids["position"],
                    "document_type_id": ids["types"][e["type"]], "effect": e["effect"], "reason": e["reason"]}
            ids["exceptions"].append(post("/api/requirement-exceptions", body)["id"])
        ids["seafarers"], ids["assignments"] = {}, {}
        for k, s in DEFINITION["seafarers"].items():
            sid = post("/api/seafarers", {"first_name": s["first"], "last_name": "Dataset",
                                          "date_of_birth": "1985-05-05", "nationality": "UA",
                                          "position_id": ids["position"]})["id"]
            ids["seafarers"][k] = sid
            if s["assign"]:
                v, a, b, cancel = s["assign"]
                start, end = T + timedelta(days=a), T + timedelta(days=b)
                if a < 0:
                    # A past start cannot always be entered through the API: owner SQL.
                    db = await vlib.owner()
                    aid = await db.fetchval(
                        "INSERT INTO public.assignment (seafarer_id, vessel_id, position_id, start_date, end_date) "
                        "VALUES ($1,$2,$3,$4,$5) RETURNING id", sid, ids["vessels"][v], ids["position"], start, end)
                    await db.close()
                else:
                    aid = post("/api/assignments", {"seafarer_id": sid, "vessel_id": ids["vessels"][v],
                                                    "position_id": ids["position"],
                                                    "start_date": start.isoformat(), "end_date": end.isoformat()})["id"]
                if cancel:
                    r = c.post(f"/api/assignments/{aid}/cancel", json={"reason": "D1 cancelled"}, headers=h)
                    assert r.status_code == 200, r.text
                ids["assignments"][k] = aid
    ids["definition"] = DEFINITION
    ev = vlib.EVIDENCE / "D1"
    ev.mkdir(parents=True, exist_ok=True)
    (ev / "d1.json").write_text(json.dumps(ids, indent=1, default=str), encoding="utf-8")
    return ids


def load() -> dict:
    return json.loads((vlib.EVIDENCE / "D1" / "d1.json").read_text(encoding="utf-8"))


def accounts(ids: dict) -> dict[str, vlib.Account]:
    out = {}
    for k, a in ids["accounts"].items():
        spec = DEFINITION["accounts"][k]
        out[k] = vlib.Account(__import__("uuid").UUID(a["id"]), a["email"], spec["role"], spec["status"], f"D1 {k}")
    return out


if __name__ == "__main__":
    print(json.dumps(asyncio.run(build()), indent=1, default=str)[:3000])
