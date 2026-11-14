"""The private Storage bucket for document files (ADR 0001, T8).

Files are stored under random paths and reached only through short-lived
signed URLs the API issues after the Scope check. Routers take the client
through `get_storage`, so tests can put an in-memory stand-in in its place
(the Storage API isn't available there).
"""

from typing import Protocol

from supabase import acreate_client

from app.config import settings

BUCKET = "crew-documents"


class StorageUnavailable(Exception):
    pass


class FileStorage(Protocol):
    async def upload(self, path: str, content: bytes, content_type: str) -> None: ...

    async def delete(self, path: str) -> None: ...

    async def signed_url(self, path: str, ttl_seconds: int, download_name: str) -> str: ...


class SupabaseStorage:
    def __init__(self, bucket: str = BUCKET) -> None:
        self.bucket = bucket
        self._client = None

    async def _bucket(self):
        if self._client is None:
            self._client = await acreate_client(
                settings.supabase_url, settings.supabase_service_role_key
            )
        return self._client.storage.from_(self.bucket)

    async def upload(self, path: str, content: bytes, content_type: str) -> None:
        """Store a new object; an existing path is never overwritten."""
        try:
            await (await self._bucket()).upload(
                path, content, file_options={"content-type": content_type, "upsert": "false"}
            )
        except Exception as exc:
            raise StorageUnavailable(str(exc)) from exc

    async def delete(self, path: str) -> None:
        await (await self._bucket()).remove([path])

    async def signed_url(self, path: str, ttl_seconds: int, download_name: str) -> str:
        """A URL valid for `ttl_seconds`. Storage serves the object with the
        content type it was stored with and, through `download`, a
        Content-Disposition carrying `download_name`."""
        try:
            result = await (await self._bucket()).create_signed_url(
                path, ttl_seconds, {"download": download_name}
            )
        except Exception as exc:
            raise StorageUnavailable(str(exc)) from exc
        return result["signedURL"]


_storage = SupabaseStorage()


def get_storage() -> FileStorage:
    return _storage
