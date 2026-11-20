"""The Supabase Auth settings in the repository (ADR-0004, email-code-sign-in 04).

A Sign-in Code is the only way in: 6 digits, valid 10 minutes, at most one
every 60 seconds, e-mailed without a link. These tests read the files the
Supabase CLI reads; `supabase start` and the Mailpit check are by hand.
"""

import re
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
CONFIG = tomllib.loads((REPO / "supabase" / "config.toml").read_text(encoding="utf-8"))
AUTH = CONFIG["auth"]

# The two e-mails a code can come in: Register (confirmation) and Sign in
# (magic_link, for an existing Account).
CODE_TEMPLATES = ["confirmation", "magic_link"]


def test_a_code_is_six_digits_valid_ten_minutes_and_one_a_minute():
    email = AUTH["email"]
    assert email["enable_confirmations"] is True
    assert email["otp_length"] == 6
    assert email["otp_expiry"] == 600
    assert email["max_frequency"] == "60s"


@pytest.mark.parametrize("name", CODE_TEMPLATES)
def test_the_code_e_mails_contain_the_code_and_no_link(name):
    template = AUTH["email"]["template"][name]
    assert template["subject"]
    # Templates are the one path the CLI resolves from the repository root.
    path = REPO / template["content_path"]
    assert path.parent == REPO / "supabase" / "templates"
    html = path.read_text(encoding="utf-8")
    assert "{{ .Token }}" in html
    for link in (".ConfirmationURL", ".TokenHash", ".SiteURL", ".RedirectTo", "href", "http"):
        assert link not in html, f"{path.name} contains {link}"


def test_auth_mail_goes_through_resend_smtp_but_not_locally():
    smtp = AUTH["email"]["smtp"]
    # Off locally, so Mailpit catches the mail; the cutover wizard turns it on.
    assert smtp["enabled"] is False
    assert smtp["host"] == "smtp.resend.com"
    assert smtp["port"] == 465
    assert smtp["user"] == "resend"
    assert smtp["pass"] == "env(SUPABASE_AUTH_SMTP_PASSWORD)"
    # The sender is on the domain the Alerts already use.
    assert smtp["admin_email"] == "env(MAIL_FROM)"


def test_the_hourly_e_mail_limit_fits_a_working_day():
    # Supabase's hosted default with custom SMTP is 30 an hour.
    assert AUTH["rate_limit"]["email_sent"] >= 100


def test_every_other_way_in_stays_off():
    assert AUTH["enable_anonymous_sign_ins"] is False
    assert AUTH["sms"]["enable_signup"] is False
    for provider in ("twilio", "twilio_verify", "messagebird", "textlocal", "vonage"):
        assert AUTH["sms"].get(provider, {}).get("enabled", False) is False
    for name, provider in AUTH.get("external", {}).items():
        assert provider["enabled"] is False, name
    assert AUTH.get("web3", {}).get("solana", {}).get("enabled", False) is False
    assert AUTH.get("passkey", {}).get("enabled", False) is False
    for factor in ("totp", "phone", "web_authn"):
        settings = AUTH["mfa"].get(factor, {})
        assert settings.get("enroll_enabled", False) is False, factor
        assert settings.get("verify_enabled", False) is False, factor


def _secrets(table, path=""):
    for key, value in table.items():
        if isinstance(value, dict):
            yield from _secrets(value, f"{path}{key}.")
        elif re.search(r"pass|secret|token|key", key) and isinstance(value, str):
            yield f"{path}{key}", value


def test_no_secret_value_is_committed():
    for key, value in _secrets(CONFIG):
        assert value == "" or re.fullmatch(r"env\([A-Z0-9_]+\)", value), key


def test_the_cutover_wizard_pushes_the_auth_config_with_a_fallback():
    wizard = (REPO / "scripts" / "hosted-cutover.sh").read_text(encoding="utf-8")
    assert "config push" in wizard
    assert "/v1/projects/" in wizard and "/config/auth" in wizard
    example = (REPO / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"^SUPABASE_AUTH_SMTP_PASSWORD=$", example, re.M)


def test_supabase_auth_also_asks_for_at_least_12_characters():
    # SR-02: the API asks for 12 (app/password_policy.py); Supabase Auth too,
    # so no other way in sets a shorter password.
    assert AUTH["minimum_password_length"] == 12
    wizard = (REPO / "scripts" / "hosted-cutover.sh").read_text(encoding="utf-8")
    assert '"password_min_length": auth["minimum_password_length"]' in wizard
