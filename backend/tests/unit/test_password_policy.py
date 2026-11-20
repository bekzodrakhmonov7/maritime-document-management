"""Password rules (SR-02): at least 12 characters, not on the bundled list of
the 3,000 most common passwords that long, compared case-insensitively."""

from app.password_policy import COMMON_PASSWORDS_FILE, MIN_LENGTH, is_common


def _entries() -> list[str]:
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return [line for line in lines if line and not line.startswith("#")]


def test_the_minimum_is_twelve_characters():
    assert MIN_LENGTH == 12


def test_the_list_holds_3000_distinct_passwords_of_at_least_12_characters():
    entries = _entries()
    assert len(entries) == 3000
    assert len(set(entries)) == 3000
    assert all(len(p) >= MIN_LENGTH for p in entries)


def test_the_list_names_its_source_licence_and_date():
    header = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").split("\n", 8)[:8]
    text = "\n".join(header)
    assert "SecLists" in text
    assert "MIT" in text
    assert "Downloaded: 2026-11-20" in text


def test_a_listed_password_is_common_in_any_case():
    assert is_common("qwerty123456")
    assert is_common("QWERTY123456")
    assert is_common("1Qaz2Wsx3Edc")


def test_an_uncommon_password_is_not():
    assert not is_common("harbour-pilot-ladder-7")
    assert not is_common("correct-horse-1")
