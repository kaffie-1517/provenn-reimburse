"""Object storage for invoice PDFs. S3 API, so MinIO, AWS S3 and R2 all work."""

import asyncio
from functools import lru_cache
from typing import Protocol

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings


class NotFound(Exception):
    pass


class Storage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None: ...
    async def get(self, key: str) -> bytes: ...


class S3Storage:
    def __init__(self) -> None:
        s = get_settings()
        self.bucket = s.s3_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=s.s3_endpoint_url or None,
            region_name=s.s3_region,
            # None → boto3's default chain (env vars, instance role, ...).
            aws_access_key_id=s.s3_access_key or None,
            aws_secret_access_key=s.s3_secret_key or None,
            config=BotoConfig(signature_version="s3v4", retries={"max_attempts": 3}),
        )

    async def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    async def get(self, key: str) -> bytes:
        def _get() -> bytes:
            try:
                return self._client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            except ClientError as e:
                if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                    raise NotFound(key) from e
                raise

        return await asyncio.to_thread(_get)


class MemoryStorage:
    """In-process store for tests and local experiments."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, data: bytes, content_type: str = "application/pdf") -> None:
        self.objects[key] = bytes(data)

    async def get(self, key: str) -> bytes:
        try:
            return self.objects[key]
        except KeyError as e:
            raise NotFound(key) from e


@lru_cache
def get_storage() -> Storage:
    return S3Storage()


def raw_key(invoice_id) -> str:
    return f"invoices/{invoice_id}/raw.pdf"


def version_key(invoice_id, version: int) -> str:
    return f"invoices/{invoice_id}/v{version}.pdf"
