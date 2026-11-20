"""The date of birth is checked against the company's today, never the server's (NFR-02)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.models.seafarer import SeafarerWrite


def _body(date_of_birth: date | None) -> SeafarerWrite:
    return SeafarerWrite(
        first_name="Anna", last_name="Petrova", date_of_birth=date_of_birth, position_id=1
    )


def test_born_on_the_company_today_is_accepted() -> None:
    today = date(2026, 1, 2)
    assert _body(today).born_by(today).date_of_birth == today


def test_born_after_the_company_today_is_refused() -> None:
    # E.g. the server is still on 2 January while the company is on 1 January.
    with pytest.raises(ValidationError) as exc_info:
        _body(date(2026, 1, 2)).born_by(date(2026, 1, 1))
    [error] = exc_info.value.errors()
    assert error["loc"] == ("date_of_birth",)
    assert "must be a date in the past" in error["msg"]


def test_born_before_1900_is_refused_without_the_company_date() -> None:
    with pytest.raises(ValidationError):
        _body(date(1899, 12, 31))


def test_the_parse_alone_leaves_the_upper_bound_to_the_company_date() -> None:
    # The server's clock decides nothing: only `born_by` knows today.
    assert _body(date(2999, 1, 1)).date_of_birth == date(2999, 1, 1)


def test_no_date_of_birth_is_allowed() -> None:
    assert _body(None).born_by(date(2026, 1, 1)).date_of_birth is None
