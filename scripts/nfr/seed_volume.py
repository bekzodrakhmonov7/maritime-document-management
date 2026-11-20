"""NFR-01 / NFR-07: fill a freshly reset LOCAL database with synthetic volume.

Writes straight into the database as the table owner (OWNER_DATABASE_URL,
default postgresql://postgres:postgres@127.0.0.1:54322/postgres) with COPY.
It reuses the reference data of supabase/seed.sql (Positions, Document Types,
requirements, the four vessels) and tops the totals up so that, together with
the seed's own demo rows, the database holds exactly --seafarers seafarers,
--versions Versions and --assignments Assignments.

Shape (printed and written to --out as JSON together with useful ids):
- seafarers spread evenly over the Positions; every 40th has a long name
  (40+ characters); about 3 % Inactive (only with a finished/cancelled or
  no Assignment).
- extra synthetic vessels so a vessel carries about 20 seafarers under way,
  plus "MV Northern Star" taking ~15 % of everyone under way (many crew).
- one Document per required Document Type (97 %), Yellow Fever for ~50 %;
  1 to 3 Versions per Document so the total is exact.
- Current Version expiry: ~5 % expired, ~10 % expiring soon (0..90 days),
  ~2 % "expiry not stated" (no date on an expiring type), the rest unexpired;
  Yellow Fever (does not expire) has no date.
- Versions uploaded by administrator 1; ~70 % reviewed once by
  administrator 2 (88 % accept); ~5 % of accepted ones verified.
- Assignments, one per seafarer: ~50 % under way, ~25 % upcoming within the
  90-day planning horizon, ~15 % finished, ~10 % cancelled.
- Accounts: two administrators and one crewing officer (Responsible Officer
  for three vessels), each with a verified session whose id is its own id,
  as backend/tests/conftest.py `make_account` does.
- One showcase seafarer (long name, all 7 Document Types, 3 Versions each)
  with an upcoming Assignment that fills every readiness group.

Usage (from the repo root, after `npx --yes supabase@2 db reset`):
    uv run python scripts/nfr/seed_volume.py --seafarers 500 --versions 5000 \
        --assignments 500 --out docs/nfr-evidence/nfr-01/seed.json
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import asyncpg

OWNER_URL = os.environ.get(
    "OWNER_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)

ADMIN_1 = UUID("00000000-0000-4000-8000-0000000e0001")
ADMIN_2 = UUID("00000000-0000-4000-8000-0000000e0002")
OFFICER = UUID("00000000-0000-4000-8000-0000000e0003")
ACCOUNTS = [
    (ADMIN_1, "nfr-admin-1@example.com", "NFR Administrator One", "administrator"),
    (ADMIN_2, "nfr-admin-2@example.com", "NFR Administrator Two", "administrator"),
    (OFFICER, "nfr-officer@example.com", "NFR Crewing Officer", "crewing_officer"),
]

FIRST = ["Anna", "Ivan", "Jose", "Mykola", "Rahul", "Elena", "Marco", "Piotr", "Andrei", "Juan",
         "Maria", "Oleksandr", "Dimitrios", "Rodrigo", "Tomasz", "Sergei", "Nikolai", "Ana",
         "Luis", "Kiran", "Mehmet", "Lars", "Jonas", "Arjun", "Carlos", "Fernando", "Viktor",
         "Hana", "Pavel", "Emil", "Bogdan", "Ramon", "Yusuf", "Teodor", "Kristian", "Vasyl"]
LAST = ["Petrova", "Horvat", "Santos", "Shevchenko", "Mehta", "Popescu", "Rossi", "Kowalski",
        "Ionescu", "Dela Cruz", "Reyes", "Bondarenko", "Papadakis", "Fernandes", "Nowak",
        "Ivanov", "Kuznetsov", "Garcia", "Mendoza", "Nair", "Yilmaz", "Hansen", "Jensen",
        "Sharma", "Lopez", "Silva", "Marinov", "Novak", "Dvorak", "Kovac", "Tkachenko",
        "Aquino", "Demir", "Georgiev", "Lindqvist", "Melnyk"]
LONG_FIRST = ["Maximilian Alexander", "Maria Fernanda Guadalupe", "Konstantinos Ioannis",
              "Juan Carlos Emmanuel", "Oleksandr Volodymyrovych"]
LONG_LAST = ["Papadopoulos-Wojciechowski", "de los Santos Villanueva-Echeverria",
             "Hadjikyriakou-Constantinou", "Bondarenko-Kostiantynivska",
             "Vasilakopoulos-Montenegro"]
NATIONS = ["BG", "HR", "PH", "UA", "IN", "RO", "IT", "PL", "ES", "GR", "PT", "RU", "TR", "NO",
           "DK", "SE", "LV", "LT", "EE", "ID", "MM", "CN", "VN", "BR"]
FLAGS = ["MT", "LR", "PA", "GR", "MH", "BS", "CY", "SG", "NO", "PT"]
VESSEL_PREFIX = ["MV", "MT", "MV", "MV", "LNG"]
VESSEL_NAMES = ["Atlantic", "Nordic", "Adriatic", "Caspian", "Iberian", "Ionian", "Celtic",
                "Arctic", "Coral", "Amber", "Silver", "Golden", "Morning", "Evening", "Polar"]
VESSEL_NOUNS = ["Star", "Dawn", "Spirit", "Trader", "Pioneer", "Voyager", "Breeze", "Horizon",
                "Pride", "Wave", "Glory", "Fortune", "Harmony", "Mariner"]
AUTHORITY = {
    "Passport": "Ministry of the Interior",
    "Seaman's Book": "Harbour Master's Office",
    "Medical Certificate": "Port Health Clinic",
    "Certificate of Competency": "Maritime Administration",
    "Basic Safety Training": "Maritime Training Centre",
    "Yellow Fever Vaccination": "Travel Health Clinic",
    "Flag Endorsement of CoC": "Flag State Administration",
}


def months_to_days(months: int | None) -> int:
    # Conservative so expiry - issue never exceeds the maximum validity.
    return (months or 60) * 30 - 2


class Ids:
    """Explicit ids continuing each table's sequence (COPY takes them)."""

    def __init__(self, start: int) -> None:
        self.next = start

    def __call__(self) -> int:
        self.next += 1
        return self.next


async def next_id(conn, table: str) -> Ids:
    return Ids(await conn.fetchval(f"SELECT coalesce(max(id), 0) FROM public.{table}"))


async def seed(args) -> dict:
    host = urlsplit(OWNER_URL).hostname
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.exit(f"Refusing to seed a non-local database ({host}).")
    rnd = random.Random(args.random_seed)
    now = datetime.now(timezone.utc)
    today = now.date()  # Settings time zone is UTC after a reset.

    conn = await asyncpg.connect(OWNER_URL)
    t0 = time.perf_counter()
    try:
        tz = await conn.fetchval("SELECT time_zone FROM public.settings")
        if tz != "UTC":
            sys.exit(f"Expected Settings time zone UTC after a reset, found {tz}.")
        have = {
            t: await conn.fetchval(f"SELECT count(*) FROM public.{t}")
            for t in ("seafarer", "version", "assignment")
        }
        if have["seafarer"] > 10:
            sys.exit("The database already holds volume data; run `db reset` first.")

        positions = await conn.fetch("SELECT id, name FROM public.position WHERE NOT retired ORDER BY id")
        types = {r["id"]: dict(r) for r in await conn.fetch(
            "SELECT id, name, expires, max_validity_months, renewable_at_sea, depends_on_id "
            "FROM public.document_type WHERE NOT retired ORDER BY id")}
        by_name = {t["name"]: tid for tid, t in types.items()}
        required: dict[int, list[int]] = {p["id"]: [] for p in positions}
        for r in await conn.fetch("SELECT position_id, document_type_id FROM public.position_requirement ORDER BY 1, 2"):
            required[r["position_id"]].append(r["document_type_id"])
        yellow = by_name["Yellow Fever Vaccination"]

        async with conn.transaction():
            # --- Accounts (as make_account) -------------------------------------
            for uid, email, name, role in ACCOUNTS:
                await conn.execute(
                    """
                    INSERT INTO auth.users (id, email, encrypted_password, raw_user_meta_data,
                                            email_confirmed_at, created_at, updated_at)
                    VALUES ($1, $2, 'x', jsonb_build_object('full_name', $3::text), now(), now(), now())
                    """, uid, email, name)
                await conn.execute(
                    "INSERT INTO public.verified_session (session_id, user_id) VALUES ($1, $1)", uid)
                await conn.execute(
                    "UPDATE public.users SET status = 'active', role = $2 WHERE id = $1", uid, role)

            # --- Vessels -------------------------------------------------------
            vessels = [dict(r) for r in await conn.fetch("SELECT id, name, flag FROM public.vessel ORDER BY id")]
            extra = max(0, args.seafarers // 25 - len(vessels))
            vid = await next_id(conn, "vessel")
            rows = []
            for i in range(extra):
                v = {"id": vid(), "name": f"{VESSEL_PREFIX[i % 5]} {VESSEL_NAMES[i % 15]} "
                     f"{VESSEL_NOUNS[(i // 15) % 14]}" + (f" {i // 210 + 1}" if i >= 210 else ""),
                     "flag": rnd.choice(FLAGS)}
                rows.append((v["id"], v["name"], str(9700000 + i), v["flag"]))
                vessels.append(v)
            if rows:
                await conn.copy_records_to_table(
                    "vessel", schema_name="public", records=rows,
                    columns=["id", "name", "imo_number", "flag"])
            crowded = next(v for v in vessels if v["name"] == "MV Northern Star")
            pacific = next(v for v in vessels if v["name"] == "MV Pacific Trader")
            for v in (crowded, vessels[1], pacific):
                await conn.execute(
                    "INSERT INTO public.responsible_officer (user_id, vessel_id) VALUES ($1, $2)",
                    OFFICER, v["id"])

            # --- Seafarers -----------------------------------------------------
            n_seafarers = args.seafarers - have["seafarer"]
            n_assign = args.assignments - have["assignment"]
            n_versions = args.versions - have["version"]
            # One Assignment per new seafarer; any surplus (the seed's own
            # seafarers count, its Assignments too) becomes an earlier,
            # finished Assignment of a seafarer who already has one.
            n_primary = min(n_assign, n_seafarers)
            n_surplus = n_assign - n_primary
            if n_surplus > n_primary - 1:
                sys.exit("Too many Assignments for the number of seafarers.")
            sid = await next_id(conn, "seafarer")
            master = next(p["id"] for p in positions if p["name"] == "Master")
            seafarers = []
            for i in range(n_seafarers):
                if i == 0:
                    first, last, pos = "Maximilian Alexander", "Papadopoulos-Wojciechowski", master
                elif i % 40 == 0:
                    first, last = rnd.choice(LONG_FIRST), rnd.choice(LONG_LAST)
                    pos = positions[i % len(positions)]["id"]
                else:
                    first, last = rnd.choice(FIRST), rnd.choice(LAST)
                    pos = positions[i % len(positions)]["id"]
                seafarers.append({
                    "id": sid(), "first": first, "last": last, "pos": pos,
                    "dob": date(1965, 1, 1) + timedelta(days=rnd.randrange(0, 38 * 365)),
                    "nat": rnd.choice(NATIONS), "inactive": False,
                })

            # --- Assignments (one per seafarer, the first n_assign) ------------
            aid = await next_id(conn, "assignment")
            assignments = []
            showcase_assignment = None
            kinds = []
            for i in range(n_primary):
                r = rnd.random()
                kinds.append("under_way" if r < 0.5 else "upcoming" if r < 0.75
                             else "finished" if r < 0.9 else "cancelled")
            kinds[0] = "upcoming"
            for i, kind in enumerate(kinds):
                s = seafarers[i]
                vessel = rnd.choice(vessels)
                if kind == "under_way":
                    if rnd.random() < 0.15:
                        vessel = crowded
                    start = today - timedelta(days=rnd.randint(1, 150))
                    end = today + timedelta(days=rnd.randint(1, 150))
                elif kind == "upcoming":
                    start = today + timedelta(days=rnd.randint(1, 89))
                    end = start + timedelta(days=rnd.randint(60, 180))
                elif kind == "finished":
                    end = today - timedelta(days=rnd.randint(1, 120))
                    start = end - timedelta(days=rnd.randint(60, 240))
                else:
                    start = today + timedelta(days=rnd.randint(-60, 120))
                    end = start + timedelta(days=rnd.randint(60, 180))
                if i == 0:
                    vessel, start, end = pacific, today + timedelta(days=20), today + timedelta(days=140)
                pos = s["pos"] if rnd.random() > 0.05 or i == 0 else rnd.choice(positions)["id"]
                a = {"id": aid(), "seafarer": s["id"], "vessel": vessel["id"], "pos": pos,
                     "start": start, "end": end, "kind": kind}
                assignments.append(a)
                if i == 0:
                    showcase_assignment = a
                if kind in ("finished", "cancelled") and rnd.random() < 0.1:
                    s["inactive"] = True
            for j in range(n_surplus):  # earlier, finished Assignments
                first = assignments[1 + j]
                end = min(first["start"], today) - timedelta(days=rnd.randint(10, 60))
                assignments.append({
                    "id": aid(), "seafarer": first["seafarer"], "vessel": rnd.choice(vessels)["id"],
                    "pos": first["pos"], "start": end - timedelta(days=rnd.randint(60, 200)),
                    "end": end, "kind": "finished"})
            for s in seafarers[n_primary:]:
                if rnd.random() < 0.03:
                    s["inactive"] = True

            await conn.copy_records_to_table(
                "seafarer", schema_name="public",
                columns=["id", "first_name", "last_name", "date_of_birth", "nationality",
                         "position_id", "inactive_since", "inactive_reason"],
                records=[(s["id"], s["first"], s["last"], s["dob"], s["nat"], s["pos"],
                          now if s["inactive"] else None,
                          "Left the company" if s["inactive"] else None) for s in seafarers])
            await conn.copy_records_to_table(
                "assignment", schema_name="public",
                columns=["id", "seafarer_id", "vessel_id", "position_id", "start_date",
                         "end_date", "cancelled_at", "cancel_reason"],
                records=[(a["id"], a["seafarer"], a["vessel"], a["pos"], a["start"], a["end"],
                          now if a["kind"] == "cancelled" else None,
                          "Vessel schedule changed" if a["kind"] == "cancelled" else None)
                         for a in assignments])

            # --- Documents -----------------------------------------------------
            did = await next_id(conn, "document")
            documents = []  # {"id", "seafarer", "type", "n", "showcase"}
            for i, s in enumerate(seafarers):
                if i == 0:
                    wanted = list(types)  # every type
                else:
                    wanted = [t for t in required[s["pos"]] if rnd.random() < 0.97]
                    if rnd.random() < 0.5:
                        wanted.append(yellow)
                for t in wanted:
                    documents.append({"id": did(), "seafarer": s["id"], "type": t,
                                      "n": 3 if i == 0 else 1, "showcase": i == 0})
            # Spread the remaining Versions: 1 to 3 per Document, exact total.
            remaining = n_versions - sum(d["n"] for d in documents)
            if remaining < 0 or remaining > 2 * sum(1 for d in documents if not d["showcase"]):
                sys.exit(f"Cannot place {n_versions} Versions on {len(documents)} Documents.")
            pool = [d for d in documents if not d["showcase"]]
            while remaining > 0:
                d = rnd.choice(pool)
                if d["n"] < 3:
                    d["n"] += 1
                    remaining -= 1
            await conn.copy_records_to_table(
                "document", schema_name="public", columns=["id", "seafarer_id", "document_type_id"],
                records=[(d["id"], d["seafarer"], d["type"]) for d in documents])

            # --- Versions ------------------------------------------------------
            showcase_plan = {  # type name: (expiry offset or None, review, verified)
                "Passport": (10, "accept", False),
                "Medical Certificate": (60, None, False),
                "Certificate of Competency": (None, "accept", False),
                "Flag Endorsement of CoC": (1000, "accept", False),
                "Seaman's Book": (1500, "accept", True),
                "Basic Safety Training": (900, None, False),
                "Yellow Fever Vaccination": (None, "accept", False),
            }
            vid_ = await next_id(conn, "version")
            versions, reviews, verifications = [], [], []
            rev_id = await next_id(conn, "review")
            ver_id = await next_id(conn, "verification")
            for d in documents:
                t = types[d["type"]]
                maxd = months_to_days(t["max_validity_months"])
                plan = showcase_plan[t["name"]] if d["showcase"] else None
                # Current Version's expiry.
                if not t["expires"]:
                    expiry = None
                elif plan is not None:
                    expiry = None if plan[0] is None else today + timedelta(days=plan[0])
                else:
                    r = rnd.random()
                    if r < 0.05:
                        expiry = today - timedelta(days=rnd.randint(1, 400))
                    elif r < 0.15:
                        expiry = today + timedelta(days=rnd.randint(0, 90))
                    elif r < 0.17:
                        expiry = None  # expiry not stated (ADR-0006)
                    else:
                        expiry = today + timedelta(days=rnd.randint(91, maxd - 31))
                if expiry is None:
                    issue = today - timedelta(days=rnd.randint(30, 1500))
                else:
                    lo = max(maxd // 3, (expiry - today).days + 1)
                    issue = expiry - timedelta(days=rnd.randint(lo, max(lo, maxd)))
                chain = [(issue, expiry)]
                for _ in range(d["n"] - 1):  # older Versions, renewed near expiry
                    prev_issue_cur = chain[-1][0]
                    if t["expires"]:
                        prev_exp = prev_issue_cur + timedelta(days=rnd.randint(0, 30))
                        prev_issue = prev_exp - timedelta(days=rnd.randint(maxd // 2, maxd))
                    else:
                        prev_exp, prev_issue = None, prev_issue_cur - timedelta(days=rnd.randint(200, 2000))
                    chain.append((prev_issue, prev_exp))
                chain.reverse()  # oldest first
                last_upload = None
                for k, (iss, exp) in enumerate(chain):
                    uploaded = datetime.combine(iss, datetime.min.time(), timezone.utc) + timedelta(
                        days=rnd.randint(1, 20), minutes=rnd.randint(0, 1440))
                    if last_upload and uploaded <= last_upload:
                        uploaded = last_upload + timedelta(hours=1)
                    if uploaded > now:
                        uploaded = now - timedelta(minutes=len(chain) - k)
                    last_upload = uploaded
                    v_id = vid_()
                    slug = t["name"].lower().replace("'", "").replace(" ", "-")
                    versions.append((
                        v_id, d["id"], f"nfr/{uuid4()}.pdf", f"{slug}.pdf", "application/pdf",
                        f"{slug[:3].upper()}-{rnd.randint(100000, 999999)}",
                        AUTHORITY.get(t["name"], "Issuing Authority"), iss, exp, ADMIN_1, uploaded))
                    current = k == len(chain) - 1
                    if plan is not None and current:
                        decision, verified = plan[1], plan[2]
                    elif rnd.random() < 0.7:
                        decision = "accept" if rnd.random() < 0.88 else "reject"
                        verified = decision == "accept" and rnd.random() < 0.06
                    else:
                        decision, verified = None, False
                    if decision:
                        reviews.append((
                            rev_id(), v_id, decision,
                            "Matches the original" if decision == "accept" else "Scan unreadable, upload again",
                            ADMIN_2, min(now, uploaded + timedelta(hours=rnd.randint(1, 72)))))
                    if verified:
                        verifications.append((
                            ver_id(), v_id, min(today, (uploaded + timedelta(days=3)).date()),
                            "E-mail to the issuing authority", "confirmed",
                            f"NFR-VER-{v_id}", ADMIN_2))
            await conn.copy_records_to_table(
                "version", schema_name="public",
                columns=["id", "document_id", "file_path", "original_filename", "content_type",
                         "document_number", "issuing_authority", "issue_date", "expiry_date",
                         "uploaded_by", "uploaded_at"], records=versions)
            await conn.copy_records_to_table(
                "review", schema_name="public",
                columns=["id", "version_id", "decision", "comment", "reviewed_by", "reviewed_at"],
                records=reviews)
            await conn.copy_records_to_table(
                "verification", schema_name="public",
                columns=["id", "version_id", "checked_on", "source", "result", "reference",
                         "recorded_by"], records=verifications)

            for table in ("vessel", "seafarer", "assignment", "document", "version", "review",
                          "verification"):
                await conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('public.{table}', 'id'), "
                    f"(SELECT max(id) FROM public.{table}))")
        await conn.execute("ANALYZE")

        # Typical seafarer for the document list: average number of Versions.
        avg = await conn.fetchval("SELECT count(*)::float / (SELECT count(*) FROM public.seafarer) FROM public.version")
        typical = await conn.fetchrow(
            """
            SELECT d.seafarer_id, count(DISTINCT d.id) AS docs, count(v.id) AS versions
              FROM public.document d JOIN public.version v ON v.document_id = d.id
             GROUP BY d.seafarer_id
             ORDER BY abs(count(v.id) - $1), d.seafarer_id LIMIT 1
            """, avg)
        crowded_crew = await conn.fetchval(
            "SELECT count(*) FROM public.assignment WHERE vessel_id = $1 AND cancelled_at IS NULL "
            "AND start_date <= CURRENT_DATE AND end_date >= CURRENT_DATE", crowded["id"])
        info = {
            "volume": {"seafarers": args.seafarers, "versions": args.versions,
                       "assignments": args.assignments},
            "seeded_at": now.isoformat(),
            "seconds": round(time.perf_counter() - t0, 1),
            "admin_id": str(ADMIN_1),
            "accounts": [{"id": str(u), "email": e, "role": r} for u, e, _, r in ACCOUNTS],
            "document_list_seafarer_id": typical["seafarer_id"],
            "document_list_seafarer_docs": typical["docs"],
            "document_list_seafarer_versions": typical["versions"],
            "average_versions_per_seafarer": round(avg, 2),
            "showcase_seafarer_id": seafarers[0]["id"],
            "showcase_seafarer_name": f"{seafarers[0]['first']} {seafarers[0]['last']}",
            "readiness_assignment_id": showcase_assignment["id"],
            "crowded_vessel_id": crowded["id"],
            "crowded_vessel_name": crowded["name"],
            "crowded_vessel_crew_under_way": crowded_crew,
            "vessels": len(vessels),
        }
        return info
    finally:
        await conn.close()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seafarers", type=int, required=True)
    p.add_argument("--versions", type=int, required=True)
    p.add_argument("--assignments", type=int, required=True)
    p.add_argument("--random-seed", type=int, default=20261120)
    p.add_argument("--out", type=Path)
    args = p.parse_args()
    info = asyncio.run(seed(args))
    text = json.dumps(info, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
