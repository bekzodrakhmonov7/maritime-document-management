"""Grouping Reviews and Verifications by Version (NFR-01/NFR-07): a Document's
read gets only its own Versions' checks, oldest first, so the domain functions
answer exactly as they would over every check read with it."""

from datetime import datetime, timezone

from app import domain
from app.services.documents import by_version, rows_of


def _review(id_: int, version_id: int, decision: str) -> dict:
    return {"id": id_, "version_id": version_id, "decision": decision}


def _version(id_: int, minute: int) -> dict:
    return {"id": id_, "uploaded_at": datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc)}


REVIEWS = [
    _review(1, 10, "accept"),
    _review(2, 20, "reject"),
    _review(3, 11, "reject"),
    _review(4, 20, "accept"),
    _review(5, 11, "accept"),
    _review(6, 10, "reject"),
]


def test_by_version_groups_rows_and_keeps_their_order():
    grouped = by_version(REVIEWS)
    assert [r["id"] for r in grouped[10]] == [1, 6]
    assert [r["id"] for r in grouped[11]] == [3, 5]
    assert [r["id"] for r in grouped[20]] == [2, 4]


def test_rows_of_returns_only_these_versions_rows_oldest_first():
    grouped = by_version(REVIEWS)
    assert [r["id"] for r in rows_of(grouped, [_version(11, 1), _version(10, 0)])] == [1, 3, 5, 6]


def test_rows_of_a_version_with_no_rows_is_empty():
    assert rows_of(by_version(REVIEWS), [_version(99, 0)]) == []
    assert rows_of({}, []) == []


def test_domain_answers_the_same_over_the_subset_as_over_every_row():
    versions = [_version(10, 0), _version(11, 1)]
    subset = rows_of(by_version(REVIEWS), versions)
    assert domain.current_version(versions, subset) == domain.current_version(versions, REVIEWS)
    for v in versions:
        assert domain.review_state(v["id"], subset) == domain.review_state(v["id"], REVIEWS)
