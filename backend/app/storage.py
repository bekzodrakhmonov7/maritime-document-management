from supabase import acreate_client

from app.config import settings


class StorageClient:
    def __init__(self, bucket: str = "crew-documents") -> None:
        self.bucket = bucket
        self._client = None

    async def _get_client(self):
        if self._client is None:
            self._client = await acreate_client(
                settings.supabase_url, settings.supabase_service_role_key
            )
        return self._client

    async def upload_file(self, bucket: str, path: str, file_bytes: bytes, mime: str) -> str:
        client = await self._get_client()
        await client.storage.from_(bucket).upload(
            path, file_bytes, file_options={"content-type": mime}
        )
        return path

    async def create_signed_url(self, path: str, ttl: int) -> str:
        client = await self._get_client()
        result = await client.storage.from_(self.bucket).create_signed_url(
            path, expires_in=ttl
        )
        return result["signedURL"]

    async def download_file(self, path: str) -> bytes:
        client = await self._get_client()
        return await client.storage.from_(self.bucket).download(path)

    async def delete_file(self, path: str) -> None:
        client = await self._get_client()
        await client.storage.from_(self.bucket).remove([path])
