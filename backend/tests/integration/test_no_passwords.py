"""Passwords cannot exist (ADR 0004).

A trigger on auth.users keeps encrypted_password empty on every insert and
update, so Supabase refuses any password grant (`invalid_credentials`) and
`updateUser({password})` stores nothing. The migration that adds it also
wiped the passwords already stored.
"""

from uuid import uuid4

import pytest


async def _password_of(owner_db, user_id) -> str | None:
    return await owner_db.fetchval(
        "SELECT encrypted_password FROM auth.users WHERE id = $1", user_id
    )


async def test_an_account_created_with_a_password_has_none(owner_db, make_account):
    # make_account inserts encrypted_password = 'x', as GoTrue would a bcrypt hash.
    account = await make_account()

    assert await _password_of(owner_db, account) == ""


async def test_a_password_inserted_directly_is_not_stored(owner_db):
    user_id = uuid4()
    try:
        await owner_db.execute(
            """
            INSERT INTO auth.users (id, email, encrypted_password, created_at, updated_at)
            VALUES ($1, $2, '$2a$10$abcdefghijklmnopqrstuuabcdefghijklmnopqrstuvwxyz0123', now(), now())
            """,
            user_id,
            f"{user_id.hex[:12]}@example.com",
        )

        assert await _password_of(owner_db, user_id) == ""
    finally:
        await owner_db.execute("DELETE FROM public.users WHERE id = $1", user_id)
        await owner_db.execute("DELETE FROM auth.users WHERE id = $1", user_id)


@pytest.mark.parametrize("password", ["$2a$10$somebcrypthash", None])
async def test_setting_a_password_later_stores_nothing(owner_db, make_account, password):
    # What updateUser({password}) does: GoTrue updates the row's hash.
    account = await make_account()

    await owner_db.execute(
        "UPDATE auth.users SET encrypted_password = $2 WHERE id = $1", account, password
    )

    assert await _password_of(owner_db, account) == ""


async def test_other_updates_to_an_account_still_apply(owner_db, make_account):
    account = await make_account()

    await owner_db.execute(
        "UPDATE auth.users SET last_sign_in_at = '2026-11-16T09:00:00Z' WHERE id = $1", account
    )

    assert await owner_db.fetchval(
        "SELECT last_sign_in_at IS NOT NULL FROM auth.users WHERE id = $1", account
    )
    assert await _password_of(owner_db, account) == ""


async def test_no_account_has_a_password(owner_db):
    # Covers the rows that existed before the migration (here: the seed's).
    assert await owner_db.fetchval(
        "SELECT count(*) FROM auth.users WHERE coalesce(encrypted_password, '') <> ''"
    ) == 0
