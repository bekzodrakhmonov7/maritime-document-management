import pytest
from datetime import date

from app.services.expiry_service import compute_days_remaining, classify_status


class TestComputeDaysRemaining:
    def test_exact_boundary_91(self):
        today = date(2025, 1, 1)
        expiry = date(2025, 4, 2)
        assert compute_days_remaining(expiry, today) == 91

    def test_exact_boundary_90(self):
        today = date(2025, 1, 1)
        expiry = date(2025, 4, 1)
        assert compute_days_remaining(expiry, today) == 90

    def test_exact_boundary_30(self):
        today = date(2025, 1, 1)
        expiry = date(2025, 1, 31)
        assert compute_days_remaining(expiry, today) == 30

    def test_exact_boundary_0(self):
        today = date(2025, 1, 1)
        expiry = date(2025, 1, 1)
        assert compute_days_remaining(expiry, today) == 0

    def test_exact_boundary_minus_1(self):
        today = date(2025, 1, 2)
        expiry = date(2025, 1, 1)
        assert compute_days_remaining(expiry, today) == -1


class TestClassifyStatus:
    def test_91_days_is_verified(self):
        assert classify_status(91) == "verified"

    def test_90_days_is_expiring_soon(self):
        assert classify_status(90) == "expiring_soon"

    def test_30_days_is_expiring_soon(self):
        assert classify_status(30) == "expiring_soon"

    def test_1_day_is_expiring_soon(self):
        assert classify_status(1) == "expiring_soon"

    def test_0_days_is_expired(self):
        assert classify_status(0) == "expired"

    def test_minus_1_days_is_expired(self):
        assert classify_status(-1) == "expired"

    def test_custom_threshold_80_days(self):
        thresholds = {"days_90": 80}
        assert classify_status(81, thresholds) == "verified"
        assert classify_status(80, thresholds) == "expiring_soon"
        assert classify_status(1, thresholds) == "expiring_soon"
        assert classify_status(0, thresholds) == "expired"
