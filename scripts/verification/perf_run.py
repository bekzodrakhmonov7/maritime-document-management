"""D0-D2 orchestration: reset + seed one volume, then N independent timing runs.

Per run: start the API (one uvicorn worker, CRON_SECRET empty, its log to a
file), wait for /health, check the daily-check endpoint answers 404, measure
CPU load for 60 s (must be < 10 %), run scripts/nfr/time_views.py, stop the API.

    uv run python scripts/verification/perf_run.py --volume d1 --runs 3 [--n 20] [--no-seed] [--tag E1]

Volumes: d1 = 500 seafarers / 5,000 versions / 500 assignments (NFR-01);
         d2 = 5,000 / 50,000 / 5,000 (NFR-07).
Linux (E2): --cpus 2 runs the API under `taskset -c 0,1`.
"""

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path

import httpx

import vlib

ROOT = vlib.ROOT
VOL = {"d1": (500, 5000, 500), "d2": (5000, 50000, 5000)}
WIN = platform.system() == "Windows"


def sh(cmd: list[str], log: Path, cwd: Path = ROOT, env: dict | None = None, timeout: int | None = None) -> int:
    with log.open("a", encoding="utf-8") as f:
        f.write(f"\n$ {' '.join(cmd)}\n")
        f.flush()
        return subprocess.run(cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT, env=env, timeout=timeout,
                              shell=WIN and cmd[0] == "npx").returncode


def cpu_load(seconds: int = 60) -> float:
    if WIN:
        ps = (f"$s = Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 1 -MaxSamples {seconds}; "
              "($s.CounterSamples | Measure-Object -Property CookedValue -Average).Average")
        for _ in range(3):
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
            lines = out.strip().splitlines()
            if lines:
                return round(float(lines[-1].replace(",", ".")), 2)
        return -1.0
    def snap():
        f = [int(x) for x in open("/proc/stat").readline().split()[1:]]
        return sum(f), f[3] + f[4]  # total, idle + iowait
    t0, i0 = snap()
    time.sleep(seconds)
    t1, i1 = snap()
    return round(100 * (1 - (i1 - i0) / (t1 - t0)), 2)


def start_api(log: Path, cpus: int | None) -> subprocess.Popen:
    env = {**os.environ, "CRON_SECRET": ""}
    cmd = ["uv", "run", "uvicorn", "app.main:app", "--port", "8000", "--workers", "1"]
    if cpus and not WIN:
        cmd = ["taskset", "-c", ",".join(str(i) for i in range(cpus))] + cmd
    f = log.open("a", encoding="utf-8")
    p = subprocess.Popen(cmd, cwd=ROOT / "backend", stdout=f, stderr=subprocess.STDOUT, env=env)
    for _ in range(120):
        try:
            if httpx.get("http://127.0.0.1:8000/health", timeout=2).status_code == 200:
                return p
        except httpx.HTTPError:
            pass
        time.sleep(1)
    p.kill()
    raise RuntimeError("API did not start")


def stop_api(p: subprocess.Popen) -> None:
    if WIN:
        subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], capture_output=True)
    else:
        p.terminate()
    try:
        p.wait(20)
    except subprocess.TimeoutExpired:
        p.kill()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--volume", choices=VOL, required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--tag", default="E1")
    ap.add_argument("--cpus", type=int)
    ap.add_argument("--no-seed", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--first-run", type=int, default=1)
    a = ap.parse_args()
    out = vlib.EVIDENCE / "D" / f"{a.tag}-{a.volume}{a.label}"
    out.mkdir(parents=True, exist_ok=True)
    log = out / "console.txt"
    s, v, asg = VOL[a.volume]
    seed = out / "seed.json"
    if not a.no_seed:
        npx = "npx"
        assert sh([npx, "--yes", "supabase@2.122.1", "db", "reset"], log) == 0, "db reset failed"
        t0 = time.time()
        assert sh(["uv", "run", "python", "scripts/nfr/seed_volume.py", "--seafarers", str(s), "--versions", str(v),
                   "--assignments", str(asg), "--random-seed", "20261120", "--out", str(seed)], log) == 0, "seed failed"
        (out / "seed_seconds.txt").write_text(str(round(time.time() - t0, 1)))
        sh(["uv", "run", "python", "scripts/nfr/data_shape.py", "--out", str(out / "shape.json")], log)
    prev = out / "summary.json"
    summary = {"tag": a.tag, "volume": a.volume, "n": a.n, "runs": [], "host": platform.platform(), "cpus_limit": a.cpus}
    for i in range(a.first_run, a.runs + 1):
        rd = out / f"run{i}"
        rd.mkdir(exist_ok=True)
        api = start_api(rd / "api.log", a.cpus)
        try:
            dc = httpx.post("http://127.0.0.1:8000/api/internal/daily-check", headers={"X-Cron-Secret": "local-dev-cron-secret"}, timeout=10)
            load = cpu_load(60)
            info = {"run": i, "daily_check_status": dc.status_code, "cpu_load_pct_60s": load}
            if dc.status_code != 404 or load >= 10:
                info["warning"] = "daily check reachable or CPU load >= 10 %"
            rc = sh(["uv", "run", "python", "scripts/nfr/time_views.py", "--seed-info", str(seed), "--n", str(a.n),
                     "--csv", str(rd / "timings.csv"), "--summary", str(rd / "summary.json"), "--label", f"{a.tag}-{a.volume}-run{i}",
                     "--timeout", "120"], rd / "time_views.txt")
            info["time_views_exit"] = rc
            if rc == 0:
                info["summary"] = json.loads((rd / "summary.json").read_text())
            summary["runs"].append(info)
            print(json.dumps({k: v for k, v in info.items() if k != "summary"}))
        finally:
            stop_api(api)
        time.sleep(5)
    if a.first_run > 1:
        # keep the earlier runs of this folder (read back from their run folders)
        for j in range(1, a.first_run):
            rs = out / f"run{j}" / "summary.json"
            if rs.exists():
                summary["runs"].insert(j - 1, {"run": j, "summary": json.loads(rs.read_text()), "note": "from an earlier invocation"})
    worst = {}
    for r in summary["runs"]:
        for name, e in (r.get("summary") or {}).get("endpoints", {}).items():
            w = worst.setdefault(name, {"kind": e["kind"], "worst_p95_ms": 0, "bytes": set()})
            w["worst_p95_ms"] = max(w["worst_p95_ms"], e["p95_ms"])
            w["bytes"].add(e["bytes"])
    for w in worst.values():
        w["bytes"] = sorted(w["bytes"])
        w["pass"] = w["worst_p95_ms"] <= 2000
    summary["worst"] = worst
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    for name, w in worst.items():
        print(f"{name:28s} {w['kind']:9s} worst p95 {w['worst_p95_ms']:9.1f} ms  bytes {w['bytes']}  {'PASS' if w['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
