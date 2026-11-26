"""NFR-01 / NFR-07: time the dashboard, document list and readiness view.

The dashboard is paged (one queue per request, default "missing", 50 seafarer
groups or Assignments): it is timed as the plain call (its default queue) and
again as each queue's first page (`dashboard_<queue>`, ?queue=<queue>).

Calls the running API (default http://127.0.0.1:8000) with an administrator
token: HS256, signed with SUPABASE_JWT_SECRET from the repo's .env, claims as
`make_token` in backend/tests/conftest.py (session_id = account id, which
seed_volume.py marks as verified).

Per endpoint: one uncounted warm-up request, then --n sequential requests over
one keep-alive connection. Each time runs from sending the request to the last
byte of the body (httpx, time.perf_counter). Every response must be 200 with a
non-empty body. p95 is nearest-rank (ceil(0.95 * n)-th sorted value: the 19th
of 20).

Usage (from the repo root, API running, ids from seed_volume.py's JSON):
    uv run python scripts/nfr/time_views.py --seed-info docs/nfr-evidence/nfr-01/seed.json \
        --csv docs/nfr-evidence/nfr-01/timings.csv --summary docs/nfr-evidence/nfr-01/timings.json
"""

import argparse
import csv
import json
import math
import statistics
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import jwt

ROOT = Path(__file__).resolve().parents[2]


def env_value(key: str) -> str:
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{key}="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit(f"{key} is not in .env")


def token(account_id: str, email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": account_id, "session_id": account_id, "email": email,
               "role": "authenticated", "aud": "authenticated", "aal": "aal2",
               "iat": now, "exp": now + timedelta(hours=2)}
    return jwt.encode(payload, env_value("SUPABASE_JWT_SECRET"), algorithm="HS256")


def nearest_rank(sorted_values: list[float], pct: float) -> float:
    return sorted_values[math.ceil(pct * len(sorted_values)) - 1]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--seed-info", type=Path, required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--n", type=int, default=20)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    p.add_argument("--label", default="")
    p.add_argument("--only", nargs="*", help="endpoint names to time (default: all)")
    p.add_argument("--timeout", type=float, default=60.0, help="seconds per request")
    args = p.parse_args()

    info = json.loads(args.seed_info.read_text(encoding="utf-8"))
    admin = next(a for a in info["accounts"] if a["id"] == info["admin_id"])
    headers = {"Authorization": f"Bearer {token(admin['id'], admin['email'])}"}
    queues = ["missing", "expired", "expiring_soon", "expiry_not_stated",
              "waiting_for_review", "starting_soon", "in_order"]
    endpoints = [
        ("dashboard", "criterion", "/api/dashboard"),
        *((f"dashboard_{q}", "criterion", f"/api/dashboard?queue={q}") for q in queues),
        ("document_list", "criterion", f"/api/seafarers/{info['document_list_seafarer_id']}/documents"),
        ("readiness", "criterion", f"/api/assignments/{info['readiness_assignment_id']}/readiness"),
        ("fleet_totals", "extra", "/api/dashboard/totals"),
        ("seafarer_list", "extra", "/api/seafarers"),
    ]

    raw, summary = [], {"label": args.label, "base_url": args.base_url, "n": args.n,
                        "started_at": datetime.now(timezone.utc).isoformat(), "endpoints": {}}
    if args.only:
        endpoints = [e for e in endpoints if e[0] in args.only]
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=args.timeout) as client:
        for name, kind, path in endpoints:
            def call() -> tuple[float, int, int]:
                t0 = time.perf_counter()
                r = client.get(path)
                body = r.content  # read to the last byte
                ms = (time.perf_counter() - t0) * 1000
                if r.status_code != 200 or not body or body in (b"[]", b"{}"):
                    sys.exit(f"{path}: HTTP {r.status_code}, {len(body)} bytes: {body[:300]!r}")
                return ms, r.status_code, len(body)

            warm_ms, _, _ = call()
            times = []
            for i in range(1, args.n + 1):
                ms, code, size = call()
                times.append(ms)
                raw.append({"endpoint": name, "kind": kind, "path": path, "request": i,
                            "ms": round(ms, 2), "status": code, "bytes": size})
            s = sorted(times)
            summary["endpoints"][name] = {
                "kind": kind, "path": path, "warmup_ms": round(warm_ms, 1),
                "min_ms": round(s[0], 1), "median_ms": round(statistics.median(s), 1),
                "p95_ms": round(nearest_rank(s, 0.95), 1), "max_ms": round(s[-1], 1),
                "bytes": size, "pass_p95_le_2000": nearest_rank(s, 0.95) <= 2000,
            }
            print(f"{name:29} {kind:9} min {s[0]:8.1f}  median {statistics.median(s):8.1f}  "
                  f"p95 {nearest_rank(s, 0.95):8.1f}  max {s[-1]:8.1f} ms  ({size} bytes)  {path}")

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(raw[0]))
        w.writeheader()
        w.writerows(raw)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
