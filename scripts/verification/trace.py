"""A4 traceability: criterion part -> tests -> their results -> black-box checks.

Reads <evidence>/A1/junit.xml (and A1b if present), scripts/verification/
criterion_parts.csv and trace_map.csv; writes <evidence>/A4/trace.csv and
gaps.json (parts with no test and no black-box check, and tests named in the
map that the junit file does not contain).

    uv run python scripts/verification/trace.py
"""

import csv
import json
import re
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

import vlib

HERE = Path(__file__).resolve().parent


def junit_results(path: Path) -> dict[str, list[str]]:
    """node id without parametrization -> list of outcomes of its cases."""
    out: dict[str, list[str]] = defaultdict(list)
    if not path.exists():
        return out
    for tc in ET.parse(path).getroot().iter("testcase"):
        cls, name = tc.get("classname", ""), tc.get("name", "")
        file = "tests/" + "/".join(cls.split(".")[1:]) + ".py" if cls.startswith("tests.") else cls
        base = re.sub(r"\[.*\]$", "", name)
        outcome = "passed"
        for tag in ("failure", "error", "skipped"):
            if tc.find(tag) is not None:
                outcome = {"failure": "failed", "error": "error", "skipped": "skipped"}[tag]
        out[f"{file}::{base}"].append(outcome)
    return out


def main() -> None:
    a1 = junit_results(vlib.EVIDENCE / "A1" / "junit.xml")
    a1b = junit_results(vlib.EVIDENCE / "A1b" / "junit.xml")
    parts = list(csv.DictReader(open(HERE / "criterion_parts.csv", encoding="utf-8")))
    tmap = {r["part_id"]: r for r in csv.DictReader(open(HERE / "trace_map.csv", encoding="utf-8"))}
    out_dir = vlib.EVIDENCE / "A4"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, unknown, gaps = [], [], []
    for p in parts:
        m = tmap.get(p["part_id"], {})
        tests = [t.strip() for t in (m.get("test_node_ids") or "").split(";") if t.strip()]
        res = []
        for t in tests:
            if t.startswith("frontend/"):
                res.append(f"{t}=see A2")
                continue
            r1 = a1.get(t)
            if r1 is None:
                unknown.append(t)
                res.append(f"{t}=NOT IN JUNIT")
                continue
            summ = f"{len([x for x in r1 if x == 'passed'])}/{len(r1)} passed"
            if a1b and a1b.get(t) != r1:
                summ += f" (A1b: {a1b.get(t)})"
            res.append(f"{t}={summ}")
        bb = p["blackbox_checks"]
        rows.append({"part_id": p["part_id"], "requirement": p["requirement"], "criterion_part": p["criterion_part"],
                     "tests": ";".join(tests), "test_results": ";".join(res), "test_strength": m.get("strength", "none"),
                     "test_note": m.get("note", ""), "blackbox_checks": bb})
        if not tests and not bb:
            gaps.append(p["part_id"])
    with open(out_dir / "trace.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    no_test = [r["part_id"] for r in rows if r["test_strength"] in ("none", "") or not r["tests"]]
    (out_dir / "gaps.json").write_text(json.dumps({"no_test_and_no_blackbox": gaps, "no_automated_test": no_test,
                                                    "map_ids_not_in_junit": sorted(set(unknown))}, indent=1), encoding="utf-8")
    print(f"parts={len(rows)} no-evidence={len(gaps)} no-automated-test={len(no_test)} unknown-ids={len(set(unknown))}")


if __name__ == "__main__":
    main()
