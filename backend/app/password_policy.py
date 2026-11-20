"""Password rules for a new password (SR-02, ASVS 6.2.1, 6.2.4).

At least 12 characters, and not one of the 3,000 most common passwords that
long (`data/common_passwords.txt`, compared case-insensitively). The breach
check is `app.pwned_passwords`. Signing in accepts any length, so Accounts
made under the old minimum of 8 can still sign in.
"""

from functools import cache
from pathlib import Path

MIN_LENGTH = 12
# bcrypt reads at most 72 bytes; Supabase Auth refuses longer passwords.
MAX_LENGTH = 72

COMMON_PASSWORDS_FILE = Path(__file__).resolve().parent / "data" / "common_passwords.txt"


@cache
def _common() -> frozenset[str]:
    lines = COMMON_PASSWORDS_FILE.read_text(encoding="utf-8").splitlines()
    return frozenset(line for line in lines if line and not line.startswith("#"))


def is_common(password: str) -> bool:
    return password.lower() in _common()
