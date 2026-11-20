"""NFR-02: run the acceptance-criterion date cases directly against app.domain.

Prints a stable table on stdout (nothing in it depends on the server clock or
time zone), so runs under different TZ values can be diffed byte for byte.
The server's own zone and offset go to stderr. Exit code 1 if any case fails.

    cd backend
    TZ=Etc/GMT+12 uv run python ../scripts/nfr/date_cases.py
"""

import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from app.domain import (  # noqa: E402
    EffectiveExpiry,
    coverage_class,
    expiry_status,
    latest_allowed_expiry,
    step_to_raise,
    today_in,
)

STEPS = (90, 60, 30, 0)
LARGEST = max(STEPS)
D = date.fromisoformat


def status(expiry: str, today: str) -> str:
    return expiry_status(D(expiry), D(today), LARGEST, expires=True)


def remaining(expiry: str, today: str) -> int:
    return (D(expiry) - D(today)).days


def cover(start: str, end: str, expiry: str) -> str:
    current = {"expiry_date": D(expiry)}
    plain = coverage_class(D(start), D(end), current)
    effective = coverage_class(
        D(start), D(end), current, EffectiveExpiry(expiry=D(expiry), own_expiry=D(expiry), expires=True)
    )
    return plain if plain == effective else f"MISMATCH {plain}/{effective}"


def utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


def step(expiry: str, today: str) -> str:
    s = step_to_raise(D(expiry), D(today), STEPS, already_raised=())
    return "none" if s is None else f"{s.step} skipped={list(s.skipped)}"


# (case, expression, expected, actual)
CASES: list[tuple[str, str, object, object]] = [
    # Expiry on the check date and the day after.
    ("expiry day", "expiry_status(2027-05-10, today=2027-05-10)", "expiring_soon", status("2027-05-10", "2027-05-10")),
    ("next day", "expiry_status(2027-05-10, today=2027-05-11)", "expired", status("2027-05-10", "2027-05-11")),
    # Remaining validity equal to the largest alert step (90).
    ("remaining = largest step", "days(2027-08-08 - 2027-05-10)", 90, remaining("2027-08-08", "2027-05-10")),
    ("remaining = largest step", "expiry_status(2027-08-08, today=2027-05-10)", "expiring_soon", status("2027-08-08", "2027-05-10")),
    ("remaining = largest step", "step_to_raise(2027-08-08, today=2027-05-10)", "90 skipped=[]", step("2027-08-08", "2027-05-10")),
    ("remaining = largest step + 1", "expiry_status(2027-08-09, today=2027-05-10)", "unexpired", status("2027-08-09", "2027-05-10")),
    ("remaining = largest step + 1", "step_to_raise(2027-08-09, today=2027-05-10)", "none", step("2027-08-09", "2027-05-10")),
    # Month and year ends.
    ("31 Jan", "expiry_status(2027-01-31, today=2027-01-31)", "expiring_soon", status("2027-01-31", "2027-01-31")),
    ("31 Jan", "expiry_status(2027-01-31, today=2027-02-01)", "expired", status("2027-01-31", "2027-02-01")),
    ("28 Feb (2027)", "expiry_status(2027-02-28, today=2027-02-28)", "expiring_soon", status("2027-02-28", "2027-02-28")),
    ("28 Feb (2027)", "expiry_status(2027-02-28, today=2027-03-01)", "expired", status("2027-02-28", "2027-03-01")),
    ("28 Feb (2028, leap)", "expiry_status(2028-02-28, today=2028-02-29)", "expired", status("2028-02-28", "2028-02-29")),
    ("29 Feb 2028", "expiry_status(2028-02-29, today=2028-02-29)", "expiring_soon", status("2028-02-29", "2028-02-29")),
    ("29 Feb 2028", "expiry_status(2028-02-29, today=2028-03-01)", "expired", status("2028-02-29", "2028-03-01")),
    ("29 Feb 2028", "days(2028-02-29 - 2027-12-01)", 90, remaining("2028-02-29", "2027-12-01")),
    ("29 Feb 2028", "step_to_raise(2028-02-29, today=2027-12-01)", "90 skipped=[]", step("2028-02-29", "2027-12-01")),
    ("29 Feb 2028", "step_to_raise(2028-02-29, today=2028-03-01)", "0 skipped=[90, 60, 30]", step("2028-02-29", "2028-03-01")),
    ("29 Feb 2028", "latest_allowed_expiry(2027-08-31, 6 months)", "2028-02-29", latest_allowed_expiry(D("2027-08-31"), 6).isoformat()),
    ("28 Feb (2027)", "latest_allowed_expiry(2026-08-31, 6 months)", "2027-02-28", latest_allowed_expiry(D("2026-08-31"), 6).isoformat()),
    ("31 Dec", "expiry_status(2027-12-31, today=2027-12-31)", "expiring_soon", status("2027-12-31", "2027-12-31")),
    ("31 Dec", "expiry_status(2027-12-31, today=2028-01-01)", "expired", status("2027-12-31", "2028-01-01")),
    ("31 Dec", "days(2028-01-01 - 2027-12-31)", 1, remaining("2028-01-01", "2027-12-31")),
    # Coverage against an Assignment 2027-01-01 .. 2027-06-30.
    ("expiry on planned end date", "coverage_class(2027-01-01..2027-06-30, expiry=2027-06-30)", "runs_out_during", cover("2027-01-01", "2027-06-30", "2027-06-30")),
    ("expiry day after planned end", "coverage_class(2027-01-01..2027-06-30, expiry=2027-07-01)", "covers_all", cover("2027-01-01", "2027-06-30", "2027-07-01")),
    ("expiry on start date", "coverage_class(2027-01-01..2027-06-30, expiry=2027-01-01)", "runs_out_during", cover("2027-01-01", "2027-06-30", "2027-01-01")),
    ("expiry day before start", "coverage_class(2027-01-01..2027-06-30, expiry=2026-12-31)", "runs_out_before_start", cover("2027-01-01", "2027-06-30", "2026-12-31")),
    ("expiry on planned end (29 Feb)", "coverage_class(2027-12-01..2028-02-29, expiry=2028-02-29)", "runs_out_during", cover("2027-12-01", "2028-02-29", "2028-02-29")),
    # Company time zone: 23:30 UTC with UTC+2 is the next calendar date.
    ("company tz UTC+2", "today_in('Etc/GMT-2', 2027-03-01T23:30Z)", "2027-03-02", today_in("Etc/GMT-2", utc("2027-03-01T23:30")).isoformat()),
    ("company tz UTC", "today_in('UTC', 2027-03-01T23:30Z)", "2027-03-01", today_in("UTC", utc("2027-03-01T23:30")).isoformat()),
    ("company tz UTC-12", "today_in('Etc/GMT+12', 2027-03-01T11:30Z)", "2027-02-28", today_in("Etc/GMT+12", utc("2027-03-01T11:30")).isoformat()),
    ("company tz UTC+2, year end", "today_in('Etc/GMT-2', 2027-12-31T22:00Z)", "2028-01-01", today_in("Etc/GMT-2", utc("2027-12-31T22:00")).isoformat()),
    ("company tz UTC+2, 29 Feb", "today_in('Etc/GMT-2', 2028-02-28T22:30Z)", "2028-02-29", today_in("Etc/GMT-2", utc("2028-02-28T22:30")).isoformat()),
    # Composed: today from the company zone, then the status.
    ("composed UTC+2", "expiry_status(2027-03-01, today_in('Etc/GMT-2', 2027-03-01T23:30Z))", "expired",
     expiry_status(D("2027-03-01"), today_in("Etc/GMT-2", utc("2027-03-01T23:30")), LARGEST, expires=True)),
    ("composed UTC", "expiry_status(2027-03-01, today_in('UTC', 2027-03-01T23:30Z))", "expiring_soon",
     expiry_status(D("2027-03-01"), today_in("UTC", utc("2027-03-01T23:30")), LARGEST, expires=True)),
]


def main() -> int:
    offset = -time.timezone if not time.localtime().tm_isdst else -time.altzone
    print(f"server TZ name={time.tzname} offset={offset:+d}s "
          f"local now={datetime.now().astimezone().isoformat(timespec='seconds')}", file=sys.stderr)
    rows = [(c, e, str(x), str(a), "ok" if str(x) == str(a) else "FAIL") for c, e, x, a in CASES]
    head = ("case", "call", "expected", "actual", "result")
    widths = [max(len(r[i]) for r in [head, *rows]) for i in range(5)]
    line = lambda r: "| " + " | ".join(v.ljust(w) for v, w in zip(r, widths)) + " |"  # noqa: E731
    print(line(head))
    print("|" + "|".join("-" * (w + 2) for w in widths) + "|")
    for r in rows:
        print(line(r))
    failed = sum(r[4] == "FAIL" for r in rows)
    print(f"\n{len(rows)} cases, {len(rows) - failed} ok, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
