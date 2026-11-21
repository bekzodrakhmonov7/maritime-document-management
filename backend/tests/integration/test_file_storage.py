"""The real Storage client against the local Supabase Storage (F-15): a missing
object is told apart from Storage that can't be reached."""

from uuid import uuid4

import httpx
import pytest

from app.config import settings
from app.storage import FileMissing, StorageUnavailable, SupabaseStorage


def _storage_reachable() -> bool:
    try:
        return httpx.get(f"{settings.supabase_url}/storage/v1/version", timeout=2).status_code == 200
    except httpx.HTTPError:
        return False


needs_storage = pytest.mark.skipif(
    not _storage_reachable(), reason="Supabase Storage is not reachable at SUPABASE_URL"
)


@needs_storage
async def test_signing_a_url_for_a_missing_object_raises_file_missing():
    with pytest.raises(FileMissing):
        await SupabaseStorage().signed_url(f"f15-test/{uuid4().hex}.pdf", 60, "x.pdf")


async def test_signing_a_url_with_storage_unreachable_raises_storage_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "supabase_url", "http://127.0.0.1:9")
    with pytest.raises(StorageUnavailable):
        await SupabaseStorage().signed_url(f"f15-test/{uuid4().hex}.pdf", 60, "x.pdf")
