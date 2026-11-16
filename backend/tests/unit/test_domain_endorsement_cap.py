"""The Endorsement cap (FR-14, O1/T11): an Endorsement's Effective Expiry is the
earlier of its own and its certificate's Current Version expiry, as plain
functions."""

from datetime import date, timedelta

import pytest

from app.domain import (
    EffectiveExpiry,
    RequiredDocument,
    coverage_class,
    current_version,
    effective_expiry,
    readiness,
    step_to_raise,
)

ONE_DAY = timedelta(days=1)
OWN = date(2027, 6, 30)
TODAY = date(2027, 1, 10)
CERT_TYPE = 5


def _endorsement(expiry: date | None) -> dict:
    return {
        "depends_on_id": CERT_TYPE,
        "certificate_type_name": "Certificate of Competency",
        "current_version": {"id": 1, "expiry_date": expiry},
    }


def _cert(expiry: date | None) -> dict:
    return {"id": 2, "expiry_date": expiry}


# --- effective_expiry ----------------------------------------------------------------------


def test_the_certificate_caps_an_endorsement_that_outlives_it():
    cap = OWN - 30 * ONE_DAY
    assert effective_expiry(_endorsement(OWN), _cert(cap)) == EffectiveExpiry(
        expiry=cap, own_expiry=OWN, capped_by="Certificate of Competency"
    )


def test_an_endorsement_that_runs_out_first_keeps_its_own_date():
    assert effective_expiry(_endorsement(OWN), _cert(OWN + ONE_DAY)) == EffectiveExpiry(
        expiry=OWN, own_expiry=OWN
    )


def test_the_same_date_is_not_a_cap():
    assert effective_expiry(_endorsement(OWN), _cert(OWN)).capped_by is None


def test_an_endorsement_with_no_own_expiry_takes_the_certificates_date():
    assert effective_expiry(_endorsement(None), _cert(OWN)) == EffectiveExpiry(
        expiry=OWN, own_expiry=None, capped_by="Certificate of Competency"
    )


def test_no_certificate_counts_as_expired_with_a_certificate_missing_note():
    found = effective_expiry(_endorsement(OWN), None)
    assert found.certificate_missing
    assert found.missing_certificate == "Certificate of Competency"
    assert found.status(TODAY, 90) == "expired"
    # Expired whatever its own date says.
    assert effective_expiry(_endorsement(None), None).status(TODAY, 90) == "expired"


def test_any_other_document_keeps_its_own_expiry():
    passport = {"depends_on_id": None, "current_version": {"id": 3, "expiry_date": OWN}}
    assert effective_expiry(passport, None) == EffectiveExpiry(expiry=OWN, own_expiry=OWN)


def test_a_document_with_no_current_version_has_no_effective_expiry():
    assert effective_expiry({**_endorsement(OWN), "current_version": None}, _cert(OWN)) is None


def test_an_awaiting_review_certificate_version_counts_and_a_rejected_one_falls_back():
    older = {"id": 10, "uploaded_at": 1, "expiry_date": OWN - 10 * ONE_DAY}
    renewal = {"id": 11, "uploaded_at": 2, "expiry_date": OWN - 60 * ONE_DAY}
    # The renewal awaits review: it is the Current Version, so it caps.
    cert = current_version([older, renewal], [])
    assert effective_expiry(_endorsement(OWN), cert).expiry == renewal["expiry_date"]
    # Rejected: the older Version is current again and caps instead.
    reject = [{"id": 1, "version_id": 11, "decision": "reject"}]
    cert = current_version([older, renewal], reject)
    assert effective_expiry(_endorsement(OWN), cert).expiry == older["expiry_date"]
    # Every Version rejected: no certificate.
    reject_all = reject + [{"id": 2, "version_id": 10, "decision": "reject"}]
    cert = current_version([older, renewal], reject_all)
    assert effective_expiry(_endorsement(OWN), cert).certificate_missing


def test_the_status_follows_the_effective_expiry():
    found = effective_expiry(_endorsement(OWN), _cert(TODAY - ONE_DAY))
    assert found.status(TODAY, 90) == "expired"
    found = effective_expiry(_endorsement(OWN), _cert(TODAY + 30 * ONE_DAY))
    assert found.status(TODAY, 90) == "expiring_soon"


def test_alerts_stay_on_the_endorsements_own_date():
    # Alert Steps are chosen from the Current Version's own expiry date; the
    # cap moves nothing there, so a certificate renewal restarts no steps.
    capped = effective_expiry(_endorsement(OWN), _cert(TODAY + ONE_DAY))
    assert capped.expiry == TODAY + ONE_DAY
    assert step_to_raise(capped.own_expiry, TODAY, [90, 30, 0], set()) is None


# --- coverage and readiness ----------------------------------------------------------------

S = date(2027, 3, 1)
D = date(2027, 6, 30)


@pytest.mark.parametrize(
    "cap, expected",
    [
        (S - ONE_DAY, "runs_out_before_start"),
        (S, "runs_out_during"),
        (D, "runs_out_during"),
        (D + ONE_DAY, "covers_all"),
    ],
)
def test_coverage_uses_the_effective_expiry(cap, expected):
    endorsement = _endorsement(D + 100 * ONE_DAY)
    effective = effective_expiry(endorsement, _cert(cap))
    assert coverage_class(S, D, endorsement["current_version"], effective) == expected


def test_coverage_without_a_certificate_runs_out_before_start():
    endorsement = _endorsement(None)
    effective = effective_expiry(endorsement, None)
    assert coverage_class(S, D, endorsement["current_version"], effective) == "runs_out_before_start"


ASSIGNMENT = {
    "start_date": S,
    "end_date": D,
    "position_id": 1,
    "position_name": "Master",
    "held_position_id": 1,
    "held_position_name": "Master",
}


def _required(effective: EffectiveExpiry | None, own: date | None) -> RequiredDocument:
    return RequiredDocument(
        document_type_id=9,
        name="Flag Endorsement",
        renewable_at_sea=False,
        document_id=7,
        current_version={"id": 1, "expiry_date": own},
        review_state="accepted",
        effective=effective,
    )


def _only_entry(view: dict, bucket: str) -> dict:
    (entry,) = view["buckets"][bucket]
    return entry


def test_readiness_names_the_certificate_to_renew_when_it_caps():
    own = D + 100 * ONE_DAY
    cap = S - ONE_DAY
    view = readiness(ASSIGNMENT, [_required(effective_expiry(_endorsement(own), _cert(cap)), own)], TODAY)
    entry = _only_entry(view, "before_joining")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["suggestion"] == (
        f"Renew Certificate of Competency before joining (endorsement capped at {cap.isoformat()})"
    )
    assert entry["expiry_date"] == own
    assert entry["effective_expiry"] == cap
    assert entry["capped_by"] == "Certificate of Competency"
    assert entry["certificate_missing"] is False


def test_readiness_under_way_names_the_certificate_too():
    own = D + 100 * ONE_DAY
    cap = S + 30 * ONE_DAY
    view = readiness(
        ASSIGNMENT, [_required(effective_expiry(_endorsement(own), _cert(cap)), own)], S + ONE_DAY
    )
    assert _only_entry(view, "before_joining")["suggestion"] == (
        f"Renew Certificate of Competency as soon as possible (endorsement capped at {cap.isoformat()})"
    )


def test_readiness_an_endorsement_capped_at_the_end_date_runs_out_during():
    own = D + 100 * ONE_DAY
    view = readiness(ASSIGNMENT, [_required(effective_expiry(_endorsement(own), _cert(D)), own)], TODAY)
    entry = _only_entry(view, "before_joining")
    assert entry["coverage"] == "runs_out_during"
    assert entry["suggestion"] == (
        f"Renew Certificate of Competency before joining (endorsement capped at {D.isoformat()})"
    )


def test_readiness_without_a_certificate_notes_it_is_missing():
    own = D + 100 * ONE_DAY
    view = readiness(ASSIGNMENT, [_required(effective_expiry(_endorsement(own), None), own)], TODAY)
    entry = _only_entry(view, "before_joining")
    assert entry["coverage"] == "runs_out_before_start"
    assert entry["certificate_missing"] is True
    assert entry["suggestion"] == "Obtain Certificate of Competency before joining (certificate missing)"


def test_readiness_keeps_its_own_advice_when_the_endorsement_runs_out_first():
    own = S - ONE_DAY
    effective = effective_expiry(_endorsement(own), _cert(D))
    view = readiness(ASSIGNMENT, [_required(effective, own)], TODAY)
    assert _only_entry(view, "before_joining")["suggestion"] == (
        f"Renew before joining (runs out {own.isoformat()})"
    )
