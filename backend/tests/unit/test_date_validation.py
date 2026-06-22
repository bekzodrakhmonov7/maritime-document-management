from datetime import date

import pytest
from pydantic import ValidationError

from app.models.document import DocumentCreate


def test_expiry_equal_to_issue_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DocumentCreate(
            doc_type_id=1,
            seafarer_id=1,
            document_number="DOC123",
            issue_date=date(2024, 1, 1),
            expiry_date=date(2024, 1, 1),
        )
    assert "expiry_date" in str(exc_info.value)


def test_expiry_before_issue_rejected() -> None:
    with pytest.raises(ValidationError) as exc_info:
        DocumentCreate(
            doc_type_id=1,
            seafarer_id=1,
            document_number="DOC123",
            issue_date=date(2024, 6, 1),
            expiry_date=date(2024, 1, 1),
        )
    assert "expiry_date" in str(exc_info.value)


def test_expiry_after_issue_accepted() -> None:
    doc = DocumentCreate(
        doc_type_id=1,
        seafarer_id=1,
        document_number="DOC123",
        issue_date=date(2024, 1, 1),
        expiry_date=date(2024, 12, 31),
    )
    assert doc.issue_date == date(2024, 1, 1)
    assert doc.expiry_date == date(2024, 12, 31)
