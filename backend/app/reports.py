"""Status Reports (FR-21, T12): one report model, rendered to PDF or CSV.

A report is made of readiness sections, one per Assignment, each holding the
Assignment and its readiness view exactly as `domain.readiness` computed it:
the report adds no logic of its own. An assignment report has one section;
a vessel report has one per Assignment under way or starting within the
Planning Horizon, plus counter totals. Both are as of today and carry who
generated them and when.

Only what the readiness view shows goes in: no document numbers, file links,
signed URLs or notes.

- CSV: one flat row per (Assignment, required Document Type) with T12's
  columns, no banner or comment rows; the vessel CSV is the assignment rows
  concatenated.
- PDF (fpdf2, pure Python): the readiness view on paper, with the
  advice-only banner. Its built-in fonts are Latin-1, so other characters
  are written without their accents, or as "?" when there is no such form.
"""

import csv
import io
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.csv_cells import spreadsheet_safe
from app.domain import READINESS_BUCKETS, ReadinessBucket

ReportKind = Literal["assignment", "vessel"]
ReportFormat = Literal["pdf", "csv"]

CSV_COLUMNS = (
    "vessel", "assignment_start", "assignment_end", "state", "seafarer", "position",
    "document_type", "bucket", "coverage", "expiry", "reviewed", "verified",
    "suggestion", "generated_at",
)
COUNTERS = ("before_joining", "renewable_at_sea", "expiry_not_stated", "not_reviewed")
EXPIRY_NOT_STATED = "Expiry not stated — check manually"
COVERAGE_LABELS = {
    "missing": "Missing",
    "runs_out_before_start": "Runs out before start",
    "runs_out_during": "Runs out during",
    "expiry_not_stated": EXPIRY_NOT_STATED,
    "covers_all": "Covers all",
}
REVIEW_LABELS = {"not_reviewed": "Not reviewed", "accepted": "Accepted", "rejected": "Rejected"}
STATE_LABELS = {"upcoming": "upcoming", "under_way": "under way"}
ADVICE_ONLY = (
    "This report only advises: it flags gaps and suggests renewals. It approves and "
    "blocks nothing; whether the seafarer may serve is decided by crewing staff."
)


@dataclass(frozen=True)
class ReportSection:
    """One Assignment's readiness: `assignment` is the readiness view's
    Assignment (names, vessel, dates), `view` what `domain.readiness` returned."""

    assignment: Mapping[str, Any]
    view: Mapping[str, Any]

    @property
    def seafarer(self) -> str:
        return f"{self.assignment['seafarer_first_name']} {self.assignment['seafarer_last_name']}"

    def bucket_title(self, bucket: ReadinessBucket) -> str:
        return {
            "before_joining": self.view["before_joining_label"],
            "renewable_at_sea": "Can be renewed at sea",
            "expiry_not_stated": EXPIRY_NOT_STATED,
            "not_reviewed": "Not reviewed",
            "covers_all": "Covers all",
        }[bucket]

    def entries(self) -> list[tuple[ReadinessBucket, Mapping[str, Any]]]:
        """Each required Document Type once, in the first bucket it is listed
        in: most urgent first. One awaiting review is also in "not reviewed",
        so it lands there only when it needs no other action."""
        seen: set[int] = set()
        found = []
        for bucket in READINESS_BUCKETS:
            for entry in self.view["buckets"][bucket]:
                if entry["document_type_id"] not in seen:
                    seen.add(entry["document_type_id"])
                    found.append((bucket, entry))
        return found


@dataclass(frozen=True)
class StatusReport:
    kind: ReportKind
    vessel_name: str
    vessel_flag: str
    today: date
    # In the company time zone.
    generated_at: datetime
    generated_by: str
    sections: Sequence[ReportSection]

    @property
    def totals(self) -> dict[str, int]:
        """The readiness counters summed over the sections."""
        return {c: sum(s.view["counters"][c] for s in self.sections) for c in COUNTERS}

    @property
    def stamp(self) -> str:
        """When it was generated, to the minute, as the PDF prints it."""
        return self.generated_at.isoformat(sep=" ", timespec="minutes")

    def filename(self, target_id: int, fmt: ReportFormat) -> str:
        return f"status-report-{self.kind}-{target_id}-{self.today.isoformat()}.{fmt}"


# --- CSV ---------------------------------------------------------------------------------


def _date(value: date | None) -> str:
    return "" if value is None else value.isoformat()


def _yes_no(value: bool) -> str:
    return "y" if value else "n"


def csv_rows(report: StatusReport) -> list[dict[str, str]]:
    """One row per (Assignment, required Document Type), keyed by CSV_COLUMNS."""
    generated_at = report.generated_at.isoformat(sep=" ", timespec="seconds")
    rows = []
    for section in report.sections:
        a = section.assignment
        for bucket, entry in section.entries():
            row = {
                "vessel": a["vessel_name"],
                "assignment_start": _date(a["start_date"]),
                "assignment_end": _date(a["end_date"]),
                "state": STATE_LABELS[section.view["state"]],
                "seafarer": section.seafarer,
                "position": a["position_name"],
                "document_type": entry["name"],
                "bucket": section.bucket_title(bucket),
                "coverage": entry["coverage"],
                "expiry": _date(entry["effective_expiry"]),
                "reviewed": _yes_no(entry["review_state"] == "accepted"),
                "verified": _yes_no(entry["verified"]),
                "suggestion": entry["suggestion"] or "",
                "generated_at": generated_at,
            }
            rows.append({c: spreadsheet_safe(row[c]) for c in CSV_COLUMNS})
    return rows


def to_csv(report: StatusReport) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    writer.writerows(csv_rows(report))
    return out.getvalue()


# --- PDF ---------------------------------------------------------------------------------


# Letters with no decomposed form to fall back on.
_FOLDED = str.maketrans({
    "Ł": "L", "ł": "l", "Đ": "D", "đ": "d", "Ħ": "H", "ħ": "h", "ı": "i",
    "Œ": "OE", "œ": "oe", "–": "-", "—": "-", "‘": "'", "’": "'", "“": '"', "”": '"',
})


def _latin1(text: str) -> str:
    """Text the PDF's built-in fonts can write."""
    out = []
    for ch in text.translate(_FOLDED):
        try:
            ch.encode("latin-1")
            out.append(ch)
        except UnicodeEncodeError:
            plain = "".join(
                c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
            )
            try:
                out.append(plain.encode("latin-1").decode("latin-1") or "?")
            except UnicodeEncodeError:
                out.append("?")
    return "".join(out)


def _expiry_note(entry: Mapping[str, Any]) -> str | None:
    """The expiry as the readiness view shows it, with the Endorsement cap.

    Shown with or without a suggestion: some suggestions carry no date
    ("Renew before joining, not renewable at sea"), and FR-19/FR-21 show the
    expiry date separately for every document."""
    if entry["certificate_missing"]:
        return "Certificate missing: counts as expired"
    if entry["capped_by"] and entry["effective_expiry"]:
        own = _date(entry["expiry_date"]) or "none"
        return (
            f"Valid until {_date(entry['effective_expiry'])} "
            f"(capped by {entry['capped_by']}; own expiry {own})"
        )
    if entry["expiry_date"]:
        return f"Valid through {_date(entry['expiry_date'])}"
    return None


class _Pdf(FPDF):
    def __init__(self, report: StatusReport) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.report = report
        self.set_auto_page_break(auto=True, margin=15)
        self.set_margins(15, 15, 15)
        self.set_title("Status Report")
        self.set_creator("Crew Document Management")

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(110)
        self.cell(0, 5, _latin1(
            f"Status Report as of {self.report.today.isoformat()} - generated {self.report.stamp} "
            f"by {self.report.generated_by} - page {self.page_no()}/{{nb}}"
        ), align="C")
        self.set_text_color(0)

    def line_of(self, text: str, size: float = 10, style: str = "", h: float = 5) -> None:
        self.set_font("Helvetica", style, size)
        self.multi_cell(0, h, _latin1(text), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def boxed(self, text: str) -> None:
        self.set_font("Helvetica", "", 9)
        self.set_fill_color(235, 238, 243)
        self.multi_cell(0, 5, _latin1(text), border=1, fill=True, padding=2,
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(2)

    def counters(self, labels: Sequence[tuple[str, int]]) -> None:
        self.set_font("Helvetica", "B", 10)
        width = self.epw / len(labels)
        for label, value in labels:
            self.cell(width, 7, _latin1(f"{label}: {value}"), border=1, align="C")
        self.ln(9)

    def section(self, section: ReportSection, *, heading_size: float) -> None:
        a, view = section.assignment, section.view
        self.line_of(f"Readiness: {section.seafarer}", size=heading_size, style="B", h=7)
        self.line_of(
            f"{a['position_name']} on {a['vessel_name']} ({a['vessel_flag']}), "
            f"{_date(a['start_date'])} to {_date(a['end_date'])} - "
            f"{STATE_LABELS[view['state']].capitalize()}"
        )
        self.ln(1)
        if view["position_notice"]:
            self.boxed(view["position_notice"])
        if self.report.kind == "assignment":
            self.boxed(ADVICE_ONLY)
        c = view["counters"]
        self.counters([
            (view["before_joining_label"], c["before_joining"]),
            ("Can be renewed at sea", c["renewable_at_sea"]),
            ("Expiry not stated", c["expiry_not_stated"]),
            ("Not reviewed", c["not_reviewed"]),
        ])
        under_way = view["state"] == "under_way"
        titles = {
            "before_joining": "Act now: sort out as soon as possible" if under_way else "Before joining",
            "renewable_at_sea": "Can be renewed at sea",
            "expiry_not_stated": EXPIRY_NOT_STATED,
            "not_reviewed": "Uploaded, not yet reviewed",
            "covers_all": "Covers the whole assignment",
        }
        for bucket in READINESS_BUCKETS:
            entries = view["buckets"][bucket]
            self.line_of(f"{titles[bucket]} ({len(entries)})", size=11, style="B", h=6)
            if not entries:
                self.set_x(self.l_margin + 4)
                self.line_of("None.", size=9)
            for entry in entries:
                self.entry(entry)
            self.ln(2)

    def entry(self, entry: Mapping[str, Any]) -> None:
        # A documented entry always shows Review and Verification (F-21): no
        # badge never means "fine". A missing one has neither, as on the web.
        badges = [COVERAGE_LABELS[entry["coverage"]]]
        if entry["review_state"] is not None:
            badges += [
                REVIEW_LABELS[entry["review_state"]],
                "Verified" if entry["verified"] else "Not verified",
            ]
        self.set_x(self.l_margin + 4)
        self.set_font("Helvetica", "B", 10)
        self.cell(self.get_string_width(_latin1(entry["name"])) + 2, 5, _latin1(entry["name"]))
        self.set_font("Helvetica", "", 9)
        self.multi_cell(0, 5, _latin1("[" + "] [".join(badges) + "]"),
                        new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        for note in (entry["suggestion"], _expiry_note(entry)):
            if note:
                self.set_x(self.l_margin + 8)
                self.multi_cell(0, 5, _latin1(note), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def to_pdf(report: StatusReport) -> bytes:
    pdf = _Pdf(report)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.line_of("Status Report", size=16, style="B", h=8)
    pdf.line_of(
        f"As of {report.today.isoformat()}. Generated {report.stamp} by {report.generated_by}.", size=9
    )
    pdf.ln(2)
    if report.kind == "assignment":
        for section in report.sections:
            pdf.section(section, heading_size=13)
    else:
        pdf.line_of(f"Vessel {report.vessel_name} ({report.vessel_flag})", size=14, style="B", h=7)
        pdf.line_of(
            f"{len(report.sections)} Assignment(s) under way or starting within the Planning Horizon."
        )
        pdf.ln(1)
        pdf.boxed(ADVICE_ONLY)
        t = report.totals
        pdf.counters([
            ("Before joining / Act now", t["before_joining"]),
            ("Can be renewed at sea", t["renewable_at_sea"]),
            ("Expiry not stated", t["expiry_not_stated"]),
            ("Not reviewed", t["not_reviewed"]),
        ])
        if not report.sections:
            pdf.line_of("No Assignment is under way or starting within the Planning Horizon.")
        for section in report.sections:
            pdf.ln(2)
            pdf.section(section, heading_size=12)
    return bytes(pdf.output())
