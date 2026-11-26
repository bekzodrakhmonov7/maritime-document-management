"""F-21 re-check: in the PDF Status Report every documented entry shows its
review status and verification as text (incl. "Accepted"/"Not verified").
Compares label counts in the PDF text with the CSV of the same report.

    uv run --with pypdf python scripts/verification/fr21_pdf.py
"""

from __future__ import annotations

import csv
import io
import re

import pypdf

import d1 as d1mod
import vlib

REVIEW = ("Not reviewed", "Accepted", "Rejected")


def main() -> None:
    ev = vlib.Evidence("FR21_PDF")
    ids = d1mod.load()
    a1 = d1mod.accounts(ids)["A1"]
    with vlib.client() as c:
        for kind, path in (("vessel V1", f"/api/vessels/{ids['vessels']['V1']}/report"),
                           ("assignment S1", f"/api/assignments/{ids['assignments']['S1']}/report")):
            pdf = c.get(path, params={"format": "pdf"}, headers=a1.h)
            cs = c.get(path, params={"format": "csv"}, headers=a1.h)
            tag = kind.replace(" ", "_")
            (ev.dir / f"{tag}.pdf").write_bytes(pdf.content)
            text = "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(io.BytesIO(pdf.content)).pages)
            (ev.dir / f"{tag}.txt").write_text(text, encoding="utf-8")
            rows = list(csv.DictReader(io.StringIO(cs.content.decode("utf-8-sig"))))
            documented = [r for r in rows if r.get("coverage") != "missing"]  # a Missing entry has no version
            n_review = sum(len(re.findall(re.escape(f"[{w}]"), text)) for w in REVIEW)
            n_notver = len(re.findall(r"\[Not verified\]", text))
            n_ver = len(re.findall(r"\[Verified\]", text))
            lines = [l for l in text.splitlines() if re.search(r"\[[^\]]+\]", l) and not l.startswith("Status Report")]
            documented_lines = [l for l in lines if "[Missing]" not in l]
            bad = [l for l in documented_lines
                   if not any(f"[{w}]" in l for w in REVIEW) or not ("[Verified]" in l or "[Not verified]" in l)]
            ev.row(case=f"{kind}: every documented entry line shows review status and verification", pdf=pdf.status_code,
                   csv_documented=len(documented), entry_lines=len(documented_lines), review_labels=n_review,
                   verified=n_ver, not_verified=n_notver, accepted_present="[Accepted]" in text, lines_without=bad,
                   note="an entry can appear in two sections (e.g. expiry not stated + not yet reviewed)",
                   ok=pdf.status_code == 200 and not bad and len(documented_lines) >= len(documented))
    ev.save()
    for r in ev.rows:
        print(("OK  " if r.get("ok") else "FAIL"), r)


if __name__ == "__main__":
    main()
