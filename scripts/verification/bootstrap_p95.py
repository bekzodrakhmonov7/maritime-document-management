"""p95 (nearest rank) with a 95 % percentile-bootstrap confidence interval (10,000 resamples).

    uv run python scripts/verification/bootstrap_p95.py <timings.csv> [out.json]
"""
import csv, json, math, random, sys
from collections import defaultdict

def p95(v):
    s = sorted(v); return s[math.ceil(0.95 * len(s)) - 1]

rows = defaultdict(list)
for r in csv.DictReader(open(sys.argv[1])):
    rows[r["endpoint"]].append(float(r["ms"]))
rnd = random.Random(20261121)
out = {}
for k, v in rows.items():
    boots = sorted(p95([rnd.choice(v) for _ in v]) for _ in range(10000))
    out[k] = {"n": len(v), "p95_ms": round(p95(v), 1), "ci95_low": round(boots[249], 1), "ci95_high": round(boots[9749], 1)}
    print(f"{k:29} n={len(v)} p95 {out[k]['p95_ms']:8.1f}  95% CI [{out[k]['ci95_low']:.1f}, {out[k]['ci95_high']:.1f}] ms")
if len(sys.argv) > 2:
    json.dump(out, open(sys.argv[2], "w"), indent=1)
