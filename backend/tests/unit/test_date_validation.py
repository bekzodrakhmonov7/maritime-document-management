from datetime import date

import pytest
from pydantic import ValidationError

from app.models.document import VersionDetails


def _details(**dates) -> VersionDetails:
    return VersionDetails(document_number="DOC123", issuing_authority="Authority", **dates)


def test_expiry_equal_to_issue_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _details(issue_date=date(2024, 1, 1), expiry_date=date(2024, 1, 1))
    assert "expiry_date" in str(exc_info.value)


def test_expiry_before_issue_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        _details(issue_date=date(2024, 6, 1), expiry_date=date(2024, 1, 1))
    assert "expiry_date" in str(exc_info.value)


def test_expiry_after_issue_accepted() -> None:
    details = _details(issue_date=date(2024, 1, 1), expiry_date=date(2025, 1, 1))
    assert details.expiry_date == date(2025, 1, 1)


def test_no_expiry_date_is_allowed_by_the_model() -> None:
    # Whether the type requires one is the Document Type's rule (service).
    assert _details(issue_date=date(2024, 1, 1), expiry_date="").expiry_date is None


def test_blank_details_are_rejected() -> None:
    with pytest.raises(ValidationError):
        VersionDetails(document_number="  ", issuing_authority="A", issue_date=date(2024, 1, 1))
