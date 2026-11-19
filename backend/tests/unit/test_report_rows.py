"""The Status Report's CSV shape (FR-21, T12): one flat row per (Assignment,
required Document Type), no banner or comment rows, and the vessel CSV is the
assignment rows concatenated. Built from readiness, never anything new."""

import csv
import io
from datetime import date, datetime, timezone

import re
import zlib

from app.domain import EffectiveExpiry, RequiredDocument, readiness
from app.reports import CSV_COLUMNS, ReportSection, StatusReport, csv_rows, to_csv

TODAY = date(2027, 2, 1)
GENERATED_AT = datetime(2027, 2, 1, 9, 30, tzinfo=timezone.utc)


def _assignment(seafarer="Anna", start=date(2027, 3, 1), end=date(2027, 6, 30), position=1) -> dict:
    return {
        "id": 1,
        "seafarer_first_name": seafarer,
        "seafarer_last_name": "Petrova",
        "vessel_name": "Alpha",
        "vessel_flag": "LR",
        "position_id": position,
        "position_name": "Master",
        "held_position_id": 1,
        "held_position_name": "Master",
        "start_date": start,
        "end_date": end,
    }


def _doc(name, type_id, expiry=None, *, missing=False, renewable=False, review="accepted", verified=False):
    return RequiredDocument(
        document_type_id=type_id,
        name=name,
        renewable_at_sea=renewable,
        document_id=None if missing else 70 + type_id,
        current_version=None if missing else {"id": 1, "expiry_date": expiry, "document_number": "X-1"},
        review_state=None if missing else review,
        verified=verified,
    )


def _section(assignment: dict, *docs: RequiredDocument) -> ReportSection:
    return ReportSection(assignment=assignment, view=readiness(assignment, docs, TODAY))


def _report(*sections: ReportSection, kind="assignment") -> StatusReport:
    return StatusReport(
        kind=kind,
        vessel_name="Alpha",
        vessel_flag="LR",
        today=TODAY,
        generated_at=GENERATED_AT,
        generated_by="Olga Officer (olga@example.com)",
        sections=sections,
    )


ANNA = _section(
    _assignment(),
    _doc("Passport", 1, date(2030, 1, 1), verified=True),
    _doc("CoC", 2, missing=True),
    _doc("Medical", 3, date(2027, 4, 15), renewable=True, review="not_reviewed"),
    _doc("Visa", 4, date(2027, 2, 20)),
)


def test_the_columns_are_t12s_list():
    assert CSV_COLUMNS == (
        "vessel", "assignment_start", "assignment_end", "state", "seafarer", "position",
        "document_type", "bucket", "coverage", "expiry", "reviewed", "verified",
        "suggestion", "generated_at",
    )


def test_one_row_per_required_document_type_most_urgent_first():
    rows = csv_rows(_report(ANNA))
    assert [r["document_type"] for r in rows] == ["CoC", "Visa", "Medical", "Passport"]
    assert all(tuple(r) == CSV_COLUMNS for r in rows)


def test_a_row_carries_the_readiness_entry_and_the_assignment():
    coc, visa, medical, passport = csv_rows(_report(ANNA))
    assert coc == {
        "vessel": "Alpha",
        "assignment_start": "2027-03-01",
        "assignment_end": "2027-06-30",
        "state": "upcoming",
        "seafarer": "Anna Petrova",
        "position": "Master",
        "document_type": "CoC",
        "bucket": "Before joining",
        "coverage": "missing",
        "expiry": "",
        "reviewed": "n",
        "verified": "n",
        "suggestion": "Obtain before joining",
        "generated_at": "2027-02-01 09:30:00+00:00",
    }
    assert (visa["bucket"], visa["coverage"], visa["expiry"]) == (
        "Before joining", "runs_out_before_start", "2027-02-20"
    )
    # Awaiting review shows in its action bucket; "reviewed" tells the overlap.
    assert (medical["bucket"], medical["reviewed"], medical["suggestion"]) == (
        "Can be renewed at sea", "n", "Can be renewed at sea, by 2027-04-15"
    )
    assert (passport["bucket"], passport["reviewed"], passport["verified"], passport["suggestion"]) == (
        "Covers all", "y", "y", ""
    )


def test_a_document_only_awaiting_review_is_in_the_not_reviewed_bucket():
    section = _section(_assignment(), _doc("Passport", 1, date(2030, 1, 1), review="not_reviewed"))
    [row] = csv_rows(_report(section))
    assert (row["bucket"], row["coverage"], row["reviewed"]) == ("Not reviewed", "covers_all", "n")


def test_under_way_the_first_bucket_is_act_now():
    section = _section(_assignment(start=date(2027, 1, 1)), _doc("CoC", 2, missing=True))
    [row] = csv_rows(_report(section))
    assert (row["state"], row["bucket"]) == ("under way", "Act now")


def test_the_vessel_csv_is_the_assignment_rows_concatenated():
    boris = _section(_assignment("Boris", start=date(2027, 2, 10)), _doc("Passport", 1, date(2030, 1, 1)))
    vessel = _report(ANNA, boris, kind="vessel")
    assert csv_rows(vessel) == csv_rows(_report(ANNA)) + csv_rows(_report(boris))


def test_the_file_has_a_header_and_the_rows_only():
    text = to_csv(_report(ANNA))
    lines = list(csv.reader(io.StringIO(text)))
    assert lines[0] == list(CSV_COLUMNS)
    assert len(lines) == 1 + 4
    # No banner, advice or comment row, and no document numbers.
    assert "advises" not in text and "X-1" not in text


def test_a_name_a_spreadsheet_would_run_as_a_formula_is_quoted():
    section = _section(
        {**_assignment(), "seafarer_first_name": "=HYPERLINK(1)"}, _doc("Passport", 1, date(2030, 1, 1))
    )
    [row] = csv_rows(_report(section))
    assert row["seafarer"].startswith("'=")


# --- The PDF: rendered from the same model --------------------------------------------------


def test_both_kinds_render_to_a_pdf_whatever_the_names():
    from app.reports import to_pdf

    lukasz = _section(
        {**_assignment(), "seafarer_first_name": "Łukasz", "seafarer_last_name": "Šimić 李"},
        _doc("Passport", 1, date(2030, 1, 1)),
    )
    for report in (_report(ANNA), _report(ANNA, lukasz, kind="vessel"), _report(kind="vessel")):
        assert to_pdf(report).startswith(b"%PDF-")


def test_the_vessel_totals_sum_the_sections_counters():
    boris = _section(_assignment("Boris"), _doc("CoC", 2, missing=True))
    assert _report(ANNA, boris, kind="vessel").totals == {
        "before_joining": 3, "renewable_at_sea": 1, "expiry_not_stated": 0, "not_reviewed": 1,
    }


def test_the_pdf_writes_names_its_fonts_lack_without_accents():
    from app.reports import _latin1

    assert _latin1("Łukasz Šimić Müller 李") == "Lukasz Simic Müller ?"


# --- Expiry Not Stated (ADR-0006) ------------------------------------------------------------

UNSTATED = RequiredDocument(
    document_type_id=5,
    name="Survival Craft",
    renewable_at_sea=False,
    document_id=75,
    current_version={"id": 1, "issue_date": date(2025, 4, 2), "expiry_date": None},
    review_state="accepted",
    effective=EffectiveExpiry(expiry=None, own_expiry=None, expires=True),
)


def _pdf_text(pdf: bytes) -> str:
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", pdf, re.S)
    return b"".join(zlib.decompress(s) for s in streams).decode("latin-1")


def test_expiry_not_stated_has_its_own_csv_bucket_and_coverage():
    [row] = csv_rows(_report(_section(_assignment(), UNSTATED)))
    assert (row["bucket"], row["coverage"], row["expiry"], row["suggestion"]) == (
        "Expiry not stated — check manually",
        "expiry_not_stated",
        "",
        "Issued 2025-04-02: expiry not stated, check manually",
    )


def test_expiry_not_stated_is_counted_and_titled_in_both_pdfs():
    from app.reports import to_pdf

    section = _section(_assignment(), UNSTATED)
    vessel = _report(section, _section(_assignment("Boris"), UNSTATED), kind="vessel")
    assert vessel.totals["expiry_not_stated"] == 2
    for report, counter in ((_report(section), "1"), (vessel, "2")):
        text = _pdf_text(to_pdf(report))
        # The PDF escapes parentheses in its text.
        assert r"Expiry not stated - check manually \(1\)" in text
        assert f"Expiry not stated: {counter}" in text
        assert "[Expiry not stated]" in text
